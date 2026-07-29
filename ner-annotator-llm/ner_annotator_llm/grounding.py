"""Turn quoted LLM output into character-level annotations.

The LLM returns mentions as text, grouped by the sentence they occur in (see
:mod:`.schema`); the annotation format wants ``{"start", "end"}`` code-point
offsets over the document. This module bridges the two:

1. the group's **sentence** is located in the document, which gives a window —
   once for every mention in the group;
2. each mention's **fragments** are located inside that window, in order, which
   gives one :class:`Fragment` each;
3. offsets are mapped back to the *original* text.

Matching is done on a normalised copy of the text (whitespace collapsed, case
folded, curly quotes/dashes flattened, bidi and zero-width marks dropped) with a
per-character index map back to the original, so a model that retypes
``"He said “hi”"`` as ``"He said "hi""`` — or reflows a line break into a space —
still lands on the right characters. Nothing that fails to match is invented:
unresolvable mentions are dropped and reported in :class:`Resolution.problems`.

The :class:`Entity` / :class:`Mention` / :class:`Fragment` types here are plain
dataclasses that serialise to the annotation schema via
:func:`entities_to_json`; nothing in this package imports the surrounding
application, so it can be copied out and used on its own.
"""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, List, Optional, Sequence, Tuple

from pydantic import ValidationError

from .schema import EntityCandidate, MentionCandidate, SentenceMentions, split_fragments

# Characters that carry no textual content but are common in RTL/copy-pasted
# text; dropping them keeps a model's clean retyping matchable.
_INVISIBLE = {
    "​", "‌", "‍", "‎", "‏",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩", "﻿",
}

# Single-character punctuation variants flattened to their ASCII counterpart.
_PUNCT_FOLD = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "«": '"', "»": '"', "′": "'", "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
}

# A fuzzy sentence match needs an anchor at least this long, and this much of
# the sentence, before its neighbourhood is trusted as a window.
_MIN_ANCHOR = 12
_MIN_ANCHOR_RATIO = 0.4
# Slack added around a fuzzily located sentence, in characters.
_WINDOW_SLACK = 40

# ``Problem.reason`` values.
SENTENCE_NOT_FOUND = "sentence-not-found"
MENTION_OUTSIDE_SENTENCE = "mention-outside-sentence"
MENTION_NOT_FOUND = "mention-not-found"
EMPTY_MENTION = "empty-mention"
DUPLICATE_MENTION = "duplicate-mention"
INVALID_CANDIDATE = "invalid-candidate"


@dataclass(frozen=True)
class Fragment:
    """One contiguous span, ``end`` exclusive, in code points over the text."""

    start: int
    end: int


@dataclass
class Mention:
    """One reference to an entity: one fragment, or several for a split mention.

    ``relative`` marks a mention that identifies its entity only through a
    relation to something else ("John's secretary"); ``implicit`` marks one that
    names the entity in a background role ("Maxim" in "with Maxim's brother").
    The two are independent.
    """

    fragments: List[Fragment]
    relative: bool = False
    implicit: bool = False

    def __post_init__(self) -> None:
        if not self.fragments:
            raise ValueError("mention must have at least one fragment")
        self.fragments = merge_fragments(self.fragments)

    def to_json(self) -> dict:
        # Continuous mentions keep the plain {"start","end"} shape; only split
        # ones use {"fragments": [...]}, and the flags are written only when
        # set, so ordinary annotations stay on the minimal schema.
        if len(self.fragments) == 1:
            out: dict = {"start": self.fragments[0].start, "end": self.fragments[0].end}
        else:
            out = {"fragments": [{"start": f.start, "end": f.end} for f in self.fragments]}
        if self.relative:
            out["relative"] = True
        if self.implicit:
            out["implicit"] = True
        return out


@dataclass
class Entity:
    """One referent and every mention of it."""

    type: str
    mentions: List[Mention]

    def to_json(self) -> dict:
        return {"type": self.type, "mentions": [m.to_json() for m in self.mentions]}


def merge_fragments(fragments: Sequence[Fragment]) -> List[Fragment]:
    """Sort fragments and coalesce overlapping/adjacent ones."""
    ordered = sorted(fragments, key=lambda f: (f.start, f.end))
    merged = [ordered[0]]
    for f in ordered[1:]:
        last = merged[-1]
        if f.start <= last.end:
            merged[-1] = Fragment(start=last.start, end=max(last.end, f.end))
        else:
            merged.append(f)
    return merged


def entities_to_json(entities: Iterable[Entity]) -> List[dict]:
    """Serialise entities to the annotation schema."""
    return [e.to_json() for e in entities]


@dataclass(frozen=True)
class Problem:
    """One mention the grounding could not take at face value.

    ``dropped`` distinguishes a lost mention from a recovered one: a mention
    whose sentence was not found is still resolved by searching the whole
    document, but the ambiguity is worth surfacing.
    """

    entity_index: int
    name: str
    mention: str
    sentence: str
    reason: str
    dropped: bool
    # Extra context where there is any — currently the validation error that
    # made a whole candidate unusable.
    detail: str = ""


@dataclass
class Resolution:
    entities: List[Entity] = field(default_factory=list)
    problems: List[Problem] = field(default_factory=list)

    def to_json(self) -> List[dict]:
        """The entities in the annotation schema, ready to store."""
        return entities_to_json(self.entities)

    @property
    def n_mentions(self) -> int:
        return sum(len(e.mentions) for e in self.entities)

    @property
    def n_dropped(self) -> int:
        return sum(1 for p in self.problems if p.dropped)


class _Normalized:
    """A normalised view of a string plus a map back to the original offsets.

    ``starts[i]`` / ``ends[i]`` are the original code-point bounds of the source
    characters that produced normalised character ``i`` (a collapsed run of
    whitespace maps to the whole run).
    """

    __slots__ = ("text", "starts", "ends")

    def __init__(self, source: str) -> None:
        chars: List[str] = []
        starts: List[int] = []
        ends: List[int] = []
        i, n = 0, len(source)
        while i < n:
            ch = source[i]
            if ch.isspace():
                j = i
                while j < n and source[j].isspace():
                    j += 1
                chars.append(" ")
                starts.append(i)
                ends.append(j)
                i = j
                continue
            i += 1
            if ch in _INVISIBLE:
                continue
            folded = _PUNCT_FOLD.get(ch, ch)
            lowered = folded.lower()
            # Keep the map one-to-one: a few characters lengthen when lowered
            # (e.g. "İ"), and those are left as-is rather than desynchronising.
            if len(lowered) == 1:
                folded = lowered
            chars.append(folded)
            starts.append(i - 1)
            ends.append(i)
        self.text = "".join(chars)
        self.starts = starts
        self.ends = ends

    def to_source(self, start: int, end: int) -> Tuple[int, int]:
        """Map a normalised half-open span back to original offsets."""
        return self.starts[start], self.ends[end - 1]


def _iter_occurrences(hay: str, needle: str, lo: int, hi: int) -> Iterator[Tuple[int, int]]:
    if not needle:
        return
    i = hay.find(needle, lo, hi)
    while i != -1:
        yield i, i + len(needle)
        i = hay.find(needle, i + 1, hi)


def _word_aligned(hay: str, start: int, end: int) -> bool:
    """True when the span does not cut a word in half ("Ann" inside "Annie")."""
    left = start == 0 or not (hay[start - 1].isalnum() and hay[start].isalnum())
    right = end == len(hay) or not (hay[end - 1].isalnum() and hay[end].isalnum())
    return left and right


def _overlaps(span: Tuple[int, int], taken: Sequence[Tuple[int, int]]) -> bool:
    return any(span[0] < t_end and t_start < span[1] for t_start, t_end in taken)


def _candidate_spans(
    hay: str,
    needle: str,
    lo: int,
    hi: int,
    taken: Sequence[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Occurrences of ``needle`` in ``hay[lo:hi]``, best candidates first.

    Whole-word matches beat mid-word ones, and spans not already used by an
    earlier mention beat ones that are — so repeated surface forms ("Alice …
    then Alice") get handed out left to right instead of piling onto the first
    occurrence. Both are preferences, not filters: a genuinely nested mention
    ("Washington" inside "George Washington") still resolves.
    """
    spans = list(_iter_occurrences(hay, needle, lo, hi))
    spans.sort(key=lambda s: (not _word_aligned(hay, *s), _overlaps(s, taken), s[0]))
    return spans


def _place_fragments(
    hay: str,
    parts: Sequence[str],
    lo: int,
    hi: int,
    taken: Sequence[Tuple[int, int]],
) -> Optional[List[Tuple[int, int]]]:
    """Locate every fragment inside ``hay[lo:hi]``, left to right.

    Backtracks, so an early fragment matching in a spot that leaves no room for
    the rest does not sink the whole mention.
    """
    if not parts:
        return None
    for span in _candidate_spans(hay, parts[0], lo, hi, taken):
        if len(parts) == 1:
            return [span]
        rest = _place_fragments(hay, parts[1:], span[1], hi, taken)
        if rest is not None:
            return [span] + rest
    return None


def _sentence_windows(doc: _Normalized, sentence: str) -> Tuple[List[Tuple[int, int]], bool]:
    """Where in the document the quoted sentence is.

    Returns ``(windows, found)``. Every exact occurrence of the sentence is a
    window; failing that a fuzzy neighbourhood is tried. When the sentence
    cannot be placed at all the window is the whole document and ``found`` is
    False — the mentions are still worth resolving, just flagged.
    """
    whole = [(0, len(doc.text))]
    needle = _Normalized(sentence).text.strip()
    if not needle:
        return whole, False
    windows = list(_iter_occurrences(doc.text, needle, 0, len(doc.text)))
    if windows:
        return windows, True
    fuzzy = _fuzzy_window(doc.text, needle)
    if fuzzy is not None:
        return [fuzzy], True
    return whole, False


def _fuzzy_window(hay: str, needle: str) -> Optional[Tuple[int, int]]:
    """Neighbourhood of a sentence the model retyped imperfectly.

    Anchors on the longest shared block; if that block is a substantial part of
    the sentence, the window is where the rest of the sentence would lie.
    """
    matcher = difflib.SequenceMatcher(a=hay, b=needle, autojunk=False)
    block = matcher.find_longest_match(0, len(hay), 0, len(needle))
    if block.size < max(_MIN_ANCHOR, _MIN_ANCHOR_RATIO * len(needle)):
        return None
    start = max(0, block.a - block.b - _WINDOW_SLACK)
    end = min(len(hay), block.a - block.b + len(needle) + _WINDOW_SLACK)
    return start, end


def _fragment_parts(mention: MentionCandidate) -> Optional[List[str]]:
    """The mention's fragments, normalised for matching. ``None`` if empty."""
    parts = [_Normalized(p).text.strip() for p in split_fragments(mention.text)]
    return parts if parts and all(parts) else None


def _build_mention(
    doc: _Normalized,
    spans: Sequence[Tuple[int, int]],
    candidate: MentionCandidate,
) -> Mention:
    fragments = [Fragment(*doc.to_source(*span)) for span in spans]
    return Mention(
        fragments=fragments,
        relative=candidate.relative,
        implicit=candidate.implicit,
    )


def _resolve_group(
    doc: _Normalized,
    group: SentenceMentions,
    taken: List[Tuple[int, int]],
) -> List[Tuple[MentionCandidate, Optional[Mention], Optional[str]]]:
    """Ground every mention the model reported inside one quoted sentence.

    The sentence is located once for the whole group. When it occurs more than
    once in the document, the occurrence that accounts for the most of the
    group's mentions wins, and ties go to the one whose spans are not already
    spoken for — so a sentence that repeats verbatim hands out its occurrences
    in order instead of resolving every group onto the first copy. Within the
    chosen window the mentions are placed in order, each remembering what the
    previous ones used, so repeated wording ("Obama … Obama") walks forward
    rather than piling onto the first occurrence.

    Returns one ``(candidate, mention | None, reason | None)`` per input mention,
    in the order given.
    """
    parts = [_fragment_parts(m) for m in group.mentions]
    windows, found = _sentence_windows(doc, group.sentence)

    best: List[Optional[List[Tuple[int, int]]]] = []
    best_score = ()
    for lo, hi in windows:
        trial = list(taken)
        placements: List[Optional[List[Tuple[int, int]]]] = []
        for p in parts:
            spans = _place_fragments(doc.text, p, lo, hi, trial) if p else None
            placements.append(spans)
            if spans is not None:
                trial.extend(spans)
        resolved = [s for s in placements if s is not None]
        reused = sum(1 for s in resolved if any(_overlaps(span, taken) for span in s))
        score = (len(resolved), -reused)
        if not best_score or score > best_score:
            best, best_score = placements, score
        if score == (len(parts), 0):
            break

    results: List[Tuple[MentionCandidate, Optional[Mention], Optional[str]]] = []
    for candidate, p, spans in zip(group.mentions, parts, best):
        if p is None:
            results.append((candidate, None, EMPTY_MENTION))
            continue
        reason: Optional[str] = None if found else SENTENCE_NOT_FOUND
        if spans is None:
            # Quoted with the wrong sentence, or not in the text at all. A
            # document-wide retry keeps the real ones, flagged; note that this
            # is per mention, so one stray mention cannot drag the rest of the
            # group out of the sentence it was found in.
            spans = _place_fragments(doc.text, p, 0, len(doc.text), taken) if found else None
            reason = MENTION_OUTSIDE_SENTENCE if spans is not None else MENTION_NOT_FOUND
        if spans is None:
            results.append((candidate, None, reason))
            continue
        taken.extend(spans)
        results.append((candidate, _build_mention(doc, spans, candidate), reason))
    return results


def _mention_key(mention: Mention) -> Tuple[Tuple[int, int], ...]:
    return tuple((f.start, f.end) for f in mention.fragments)


def resolve_entities(text: str, candidates: Iterable[Any]) -> Resolution:
    """Convert predicted (quoted) entities into offset-based entities.

    ``text`` is the document exactly as it was shown to the model. Candidates
    are :class:`~.schema.EntityCandidate` instances or anything that parses as
    one (a plain dict from a raw LM response, say); one that does not parse —
    an unknown entity type, a missing field — is reported and skipped rather
    than raising.
    """
    doc = _Normalized(text)
    resolution = Resolution()
    taken: List[Tuple[int, int]] = []

    for index, value in enumerate(candidates):
        try:
            candidate = (
                value
                if isinstance(value, EntityCandidate)
                else EntityCandidate.model_validate(value)
            )
        except ValidationError as exc:
            resolution.problems.append(
                Problem(
                    entity_index=index,
                    name=str(value.get("name", "")) if isinstance(value, dict) else "",
                    mention="",
                    sentence="",
                    reason=INVALID_CANDIDATE,
                    dropped=True,
                    detail=_first_error(exc),
                )
            )
            continue

        mentions: List[Mention] = []
        seen: set = set()
        for group in candidate.sentences:
            for raw, mention, reason in _resolve_group(doc, group, taken):
                if mention is not None and _mention_key(mention) in seen:
                    mention, reason = None, DUPLICATE_MENTION
                if mention is not None:
                    seen.add(_mention_key(mention))
                    mentions.append(mention)
                if reason is not None:
                    resolution.problems.append(
                        Problem(
                            entity_index=index,
                            name=candidate.name,
                            mention=raw.text,
                            sentence=group.sentence,
                            reason=reason,
                            dropped=mention is None,
                        )
                    )
        # An entity with nothing left to point at is not annotation, it is noise.
        if mentions:
            resolution.entities.append(Entity(type=candidate.type.value, mentions=mentions))

    return resolution


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]


def unicode_safe(text: str) -> str:
    """NFC-normalise a document before sending it to the model.

    Offsets are code points, so the text handed to the LLM and the text the
    offsets are computed against must be the same string; normalise once, up
    front, and use the result for both.
    """
    return unicodedata.normalize("NFC", text)
