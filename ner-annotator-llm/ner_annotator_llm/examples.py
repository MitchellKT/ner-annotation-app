"""Hand-annotated documents -> the format the model answers in, and few-shot demos.

This is the inverse of :mod:`.grounding`: it takes an annotation in the
character-level schema — the thing an annotator produced, or a gold corpus —
and rewrites it as the quoted, sentence-grouped output the signature asks for::

    {"type": "PER", "mentions": [{"start": 0, "end": 5}]}
        ->  EntityCandidate(type=PER, sentences=[SentenceMentions(
                sentence="Annie waved.", mentions=[MentionCandidate(text="Annie")])])

Two uses. As a **check**: running the result back through
:func:`~.grounding.resolve_entities` must reproduce the original offsets, which
is what the round-trip tests assert. And as **few-shot demos**: real annotations
become the examples the model is shown, so the format it is asked to imitate is
demonstrated by the corpus itself rather than described twice.

    from ner_annotator_llm import EntityAnnotator, examples_from_jsonl

    EntityAnnotator(demos=examples_from_jsonl("gold.jsonl")[:3])

Only the demo helpers need DSPy, and they import it when called, so the
conversion itself stays usable without it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .grounding import Entity, Mention, entities_from_json
from .guidelines import ENTITY_GUIDELINES
from .schema import FRAGMENT_SEPARATOR, EntityCandidate, MentionCandidate, SentenceMentions

Span = Tuple[int, int]

# Sentence-final punctuation, plus any closing quote/bracket that trails it.
_TERMINATORS = ".!?…׃؟۔。"
_CLOSERS = "\"'”’)]»›"

# Words whose trailing dot does not end a sentence. Kept small on purpose: a
# missed abbreviation only makes a quoted sentence shorter, and a mention that
# straddles the split keeps both halves (see _covering_span).
_ABBREVIATIONS = frozenset(
    """mr mrs ms dr prof st jr sr inc ltd co corp vs etc al fig no approx
    e.g i.e u.s u.k""".split()
)


def sentence_spans(text: str) -> List[Span]:
    """Split ``text`` into sentence spans, ``[start, end)`` over code points.

    A deliberately small heuristic — terminator punctuation followed by
    whitespace, or a line break — because it only decides *how much context* a
    demo quotes. Whitespace is trimmed off each span, so ``text[start:end]`` is
    the sentence as it would be quoted.
    """
    spans: List[Span] = []
    start = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\n":
            end = index
            while index < length and text[index].isspace():
                index += 1
        elif char in _TERMINATORS:
            stop = index + 1
            while stop < length and text[stop] in _TERMINATORS:
                stop += 1
            while stop < length and text[stop] in _CLOSERS:
                stop += 1
            if stop < length and not text[stop].isspace():
                index = stop
                continue
            if char == "." and _is_abbreviation(text, index):
                index = stop
                continue
            if _continues_lowercase(text, stop):
                index = stop
                continue
            end = stop
            index = stop
            while index < length and text[index].isspace():
                index += 1
        else:
            index += 1
            continue
        span = _trim(text, start, end)
        if span is not None:
            spans.append(span)
        start = index
    span = _trim(text, start, length)
    if span is not None:
        spans.append(span)
    return spans


def _is_abbreviation(text: str, dot: int) -> bool:
    word = ""
    cursor = dot - 1
    while cursor >= 0 and not text[cursor].isspace():
        word = text[cursor] + word
        cursor -= 1
    word = word.strip("(\"'“‘").lower().rstrip(".")
    # A lone initial ("J. Smith") is never a sentence end either.
    return word in _ABBREVIATIONS or len(word) == 1


def _continues_lowercase(text: str, stop: int) -> bool:
    """True when what follows reads as a continuation, not a new sentence.

    A lowercase word after the punctuation means the "sentence end" was really
    an abbreviation or a quoted fragment (``"Stop." she said.``). Scripts
    without case — Hebrew, Arabic, CJK — are unaffected, since ``islower`` is
    False for their letters.
    """
    while stop < len(text) and text[stop].isspace():
        stop += 1
    return stop < len(text) and text[stop].islower()


def _trim(text: str, start: int, end: int) -> Optional[Span]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def _covering_span(spans: Sequence[Span], mention: Mention) -> Span:
    """The sentence span to quote for ``mention``.

    Every sentence the mention touches, merged — so a mention split across a
    sentence boundary (or across one the heuristic invented) is still contained
    by the text that gets quoted.
    """
    start = mention.fragments[0].start
    end = mention.fragments[-1].end
    touched = [s for s in spans if s[0] < end and start < s[1]]
    if not touched:
        return start, end
    return min(s[0] for s in touched), max(s[1] for s in touched)


def _mention_text(text: str, mention: Mention) -> str:
    return FRAGMENT_SEPARATOR.join(text[f.start : f.end] for f in mention.fragments)


def _entity_name(text: str, entity: Entity) -> str:
    # The longest surface form is almost always the most recognisable one
    # ("Barack Obama" over "he"); ties go to the earliest mention.
    best = max(
        entity.mentions,
        key=lambda m: (sum(f.end - f.start for f in m.fragments), -m.fragments[0].start),
    )
    return _mention_text(text, best)


def to_candidates(
    text: str,
    entities: Iterable[Union[Entity, dict]],
    *,
    skip_unknown_types: bool = False,
) -> List[EntityCandidate]:
    """Rewrite a character-level annotation as the model's output format.

    ``entities`` are :class:`~.grounding.Entity` objects or their JSON form.
    Mentions are grouped by the sentence they fall in and ordered by position,
    which is exactly the shape :class:`~.schema.EntityCandidate` asks for.

    An entity whose ``type`` is not in ``guidelines/entities.json`` cannot be
    represented — the model is only offered the registered labels — so it raises
    by default, or is dropped when ``skip_unknown_types`` is set.
    """
    parsed = list(entities)
    if parsed and isinstance(parsed[0], dict):
        parsed = entities_from_json(parsed)  # type: ignore[arg-type]
    spans = sentence_spans(text)

    candidates: List[EntityCandidate] = []
    for entity in parsed:
        if entity.type not in ENTITY_GUIDELINES:
            if skip_unknown_types:
                continue
            known = ", ".join(ENTITY_GUIDELINES)
            raise ValueError(
                f"entity type {entity.type!r} is not in the guidelines registry "
                f"(known types: {known}); add it to entities.json or pass "
                f"skip_unknown_types=True"
            )
        if not entity.mentions:
            continue
        candidates.append(
            EntityCandidate(
                name=_entity_name(text, entity),
                type=entity.type,
                sentences=_group_by_sentence(text, spans, entity),
            )
        )
    return candidates


def _group_by_sentence(text: str, spans: Sequence[Span], entity: Entity) -> List[SentenceMentions]:
    grouped: Dict[Span, List[Tuple[int, MentionCandidate]]] = {}
    for mention in entity.mentions:
        window = _covering_span(spans, mention)
        grouped.setdefault(window, []).append(
            (
                mention.fragments[0].start,
                MentionCandidate(
                    text=_mention_text(text, mention),
                    relative=mention.relative,
                    implicit=mention.implicit,
                ),
            )
        )

    # Windows can overlap when one mention straddles a sentence boundary and
    # another does not; those are one sentence as far as the answer goes.
    merged: List[Tuple[Span, List[Tuple[int, MentionCandidate]]]] = []
    for window in sorted(grouped):
        if merged and window[0] < merged[-1][0][1]:
            previous, mentions = merged[-1]
            merged[-1] = (
                (previous[0], max(previous[1], window[1])),
                mentions + grouped[window],
            )
        else:
            merged.append((window, list(grouped[window])))

    return [
        SentenceMentions(
            sentence=text[window[0] : window[1]],
            mentions=[m for _, m in sorted(mentions, key=lambda pair: pair[0])],
        )
        for window, mentions in merged
    ]


def to_example(
    text: str,
    entities: Iterable[Union[Entity, dict]],
    *,
    include_guidelines: bool = False,
    reasoning: Optional[str] = None,
    skip_unknown_types: bool = False,
) -> Any:
    """One annotated document as a :class:`dspy.Example`, ready to use as a demo.

    The guidelines are left out by default: they are already in the prompt in
    full, and repeating them per demo would cost more than the demo itself.
    DSPy renders such a demo as an example "though some input or output fields
    are not supplied", which is exactly what it is. Pass
    ``include_guidelines=True`` for a complete one, and ``reasoning`` to
    demonstrate the chain of thought as well.
    """
    import dspy  # imported here so the conversion works without DSPy installed

    from .guidelines import GENERAL_GUIDELINES, entity_guidelines_block

    fields: Dict[str, Any] = {
        "document": text,
        "entities": to_candidates(text, entities, skip_unknown_types=skip_unknown_types),
    }
    inputs = ["document"]
    if include_guidelines:
        fields["general_guidelines"] = GENERAL_GUIDELINES
        fields["entity_guidelines"] = entity_guidelines_block()
        inputs = ["general_guidelines", "entity_guidelines", "document"]
    if reasoning is not None:
        fields["reasoning"] = reasoning
    return dspy.Example(**fields).with_inputs(*inputs)


def examples_from_records(records: Iterable[dict], **kwargs: Any) -> List[Any]:
    """Demos from annotated records — anything with ``text`` and ``entities``.

    Records without entities are skipped: an empty demo teaches the model to
    return nothing. Any other keys (``doc_id``, metadata, comments) are ignored,
    so the annotator's own output files can be passed straight in.
    """
    out = []
    for record in records:
        if not record.get("entities"):
            continue
        out.append(to_example(record["text"], record["entities"], **kwargs))
    return out


def examples_from_jsonl(path: Union[str, Path], **kwargs: Any) -> List[Any]:
    """Demos from a ``.jsonl`` corpus, one annotated document per line."""
    with Path(path).open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    return examples_from_records(records, **kwargs)
