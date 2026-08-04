"""Hand-annotated documents -> the format the model answers in, and few-shot demos.

This is the inverse of :mod:`.grounding`: it takes an annotation in the
character-level schema — the thing an annotator produced, or a gold corpus —
and rewrites it as the named, per-sentence output the signature asks for::

    {"type": "PER", "mentions": [{"start": 0, "end": 5}]}
        ->  Annotation(entities=[EntityCandidate(name="Annie", type=PER)],
                       sentences=[SentenceMentions(sentence="Annie waved.",
                           mentions=[MentionCandidate(entity="Annie", text="Annie")])])

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
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .grounding import Entity, Mention, entities_from_json
from .schema import (
    FRAGMENT_SEPARATOR,
    Annotation,
    EntityCandidate,
    MentionCandidate,
    SentenceMentions,
)

Span = Tuple[int, int]

# A sentence ends at terminator punctuation followed by whitespace, or at a line
# break. That is the whole rule: no abbreviation list, no quote handling, so
# "Dr. Smith" and '"Stop." she said.' split early. It only decides how much
# context a demo quotes, and a mention that straddles a split keeps every
# sentence it touches (see _covering_span).
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def sentence_spans(text: str) -> List[Span]:
    """Split ``text`` into sentence spans, ``[start, end)`` over code points.

    Whitespace is trimmed off each span, so ``text[start:end]`` is the sentence
    as it would be quoted.
    """
    spans: List[Span] = []
    start = 0
    for boundary in _BOUNDARY.finditer(text):
        span = _trim(text, start, boundary.start())
        if span is not None:
            spans.append(span)
        start = boundary.end()
    span = _trim(text, start, len(text))
    if span is not None:
        spans.append(span)
    return spans


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


def to_annotation(text: str, entities: Iterable[Union[Entity, dict]]) -> Annotation:
    """Rewrite a character-level annotation as the model's output format.

    ``entities`` are :class:`~.grounding.Entity` objects or their JSON form.
    Each is named after its longest mention, and every mention of every entity
    is filed under the sentence it falls in, ordered by position — the
    roster-plus-sentences shape :class:`~.schema.Annotation` describes.

    Names identify entities, so two entities that would share one are told apart
    with a numeric suffix ("Washington", "Washington (2)") the way the model is
    asked to tell them apart. A type with no file in ``guidelines/entities/``
    cannot be represented, and raises.
    """
    parsed = list(entities)
    if parsed and isinstance(parsed[0], dict):
        parsed = entities_from_json(parsed)  # type: ignore[arg-type]

    kept = [entity for entity in parsed if entity.mentions]
    names = _unique_names([_entity_name(text, entity) for entity in kept])
    roster = [
        EntityCandidate(name=name, type=entity.type) for name, entity in zip(names, kept)
    ]
    return Annotation(
        entities=roster,
        sentences=_group_by_sentence(text, sentence_spans(text), list(zip(names, kept))),
    )


def _unique_names(names: Sequence[str]) -> List[str]:
    """Disambiguate repeated names with a numeric suffix, keeping order."""
    seen: Dict[str, int] = {}
    out: List[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return out


def _group_by_sentence(
    text: str,
    spans: Sequence[Span],
    named: Sequence[Tuple[str, Entity]],
) -> List[SentenceMentions]:
    """Every mention of every entity, bucketed into the sentence it falls in."""
    grouped: Dict[Span, List[Tuple[int, MentionCandidate]]] = {}
    for name, entity in named:
        for mention in entity.mentions:
            window = _covering_span(spans, mention)
            grouped.setdefault(window, []).append(
                (
                    mention.fragments[0].start,
                    MentionCandidate(
                        entity=name,
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
    reasoning: Optional[str] = None,
) -> Any:
    """One annotated document as a :class:`dspy.Example`, ready to use as a demo.

    The document is the only input, since the guidelines live in the
    instructions. Pass ``reasoning`` to demonstrate the chain of thought too.
    """
    import dspy  # imported here so the conversion works without DSPy installed

    annotation = to_annotation(text, entities)
    fields: Dict[str, Any] = {
        "document": text,
        "entities": annotation.entities,
        "sentences": annotation.sentences,
    }
    if reasoning is not None:
        fields["reasoning"] = reasoning
    return dspy.Example(**fields).with_inputs("document")


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
