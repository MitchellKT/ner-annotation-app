"""Turn quoted LLM output into character-level annotations.

The LLM returns mentions as text (see :mod:`ner_annotator.llm.schema`); the
store wants ``{"start", "end"}`` code-point offsets over the document. This
module bridges the two:

1. the mention's **sentence** is located in the document, which gives a window;
2. the mention's **fragments** are located inside that window, in order, which
   gives one :class:`~ner_annotator.models.Fragment` each;
3. offsets are mapped back to the *original* text.

Matching is done on a normalised copy of the text (whitespace collapsed, case
folded, curly quotes/dashes flattened, bidi and zero-width marks dropped) with a
per-character index map back to the original, so a model that retypes
``"He said “hi”"`` as ``"He said "hi""`` — or reflows a line break into a space —
still lands on the right characters. Nothing that fails to match is invented:
unresolvable mentions are dropped and reported in :class:`Resolution.problems`.
"""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from ..models import Entity, Fragment, Mention
from .schema import EntityCandidate, MentionCandidate, split_fragments

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


@dataclass
class Resolution:
    entities: List[Entity] = field(default_factory=list)
    problems: List[Problem] = field(default_factory=list)

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


def _search_plan(doc: _Normalized, sentence: str) -> List[Tuple[Tuple[int, int], Optional[str]]]:
    """Where to look for the mention, best window first.

    Each attempt pairs a window with the ``Problem.reason`` to report if that is
    the window the mention is found in (``None`` = clean hit). Every exact
    occurrence of the sentence is a window; failing that a fuzzy neighbourhood
    is tried. The whole document is always the last resort — a mention that is
    real but quoted with the wrong sentence is worth keeping, flagged.
    """
    whole = (0, len(doc.text))
    needle = _Normalized(sentence).text.strip()
    if not needle:
        return [(whole, SENTENCE_NOT_FOUND)]
    windows = list(_iter_occurrences(doc.text, needle, 0, len(doc.text)))
    if not windows:
        fuzzy = _fuzzy_window(doc.text, needle)
        windows = [fuzzy] if fuzzy is not None else []
    if not windows:
        return [(whole, SENTENCE_NOT_FOUND)]
    return [(w, None) for w in windows] + [(whole, MENTION_OUTSIDE_SENTENCE)]


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


def _resolve_mention(
    doc: _Normalized,
    candidate: MentionCandidate,
    taken: List[Tuple[int, int]],
) -> Tuple[Optional[Mention], Optional[str]]:
    """Ground one mention. Returns ``(mention, problem_reason)``."""
    parts = split_fragments(candidate.mention)
    if not parts:
        return None, EMPTY_MENTION
    normalized_parts = [_Normalized(p).text.strip() for p in parts]
    if not all(normalized_parts):
        return None, EMPTY_MENTION

    for (lo, hi), reason in _search_plan(doc, candidate.sentence):
        placed = _place_fragments(doc.text, normalized_parts, lo, hi, taken)
        if placed is None:
            continue
        taken.extend(placed)
        fragments = [Fragment(start=s, end=e) for s, e in (doc.to_source(*p) for p in placed)]
        mention = Mention(
            fragments=fragments,
            relative=candidate.relative,
            implicit=candidate.implicit,
        )
        return mention, reason
    return None, MENTION_NOT_FOUND


def _mention_key(mention: Mention) -> Tuple[Tuple[int, int], ...]:
    return tuple((f.start, f.end) for f in mention.fragments)


def resolve_entities(
    text: str,
    candidates: Iterable[EntityCandidate],
    *,
    default_type: str = "PER",
) -> Resolution:
    """Convert predicted (quoted) entities into on-schema entities.

    ``text`` is the document exactly as it was shown to the model. Mentions are
    resolved in the order given, and each resolved span is remembered so that
    repeated surface forms map to successive occurrences.
    """
    doc = _Normalized(text)
    resolution = Resolution()
    taken: List[Tuple[int, int]] = []

    for index, candidate in enumerate(candidates):
        mentions: List[Mention] = []
        seen: set = set()
        for raw in candidate.mentions:
            mention, reason = _resolve_mention(doc, raw, taken)
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
                        mention=raw.mention,
                        sentence=raw.sentence,
                        reason=reason,
                        dropped=mention is None,
                    )
                )
        # An entity with nothing left to point at is not annotation, it is noise.
        if mentions:
            resolution.entities.append(
                Entity(type=candidate.type or default_type, mentions=mentions)
            )

    return resolution


def unicode_safe(text: str) -> str:
    """NFC-normalise a document before sending it to the model.

    Offsets are code points, so the text handed to the LLM and the text the
    offsets are computed against must be the same string; normalise once, up
    front, and use the result for both.
    """
    return unicodedata.normalize("NFC", text)
