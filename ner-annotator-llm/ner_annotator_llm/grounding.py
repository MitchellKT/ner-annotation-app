"""Turn quoted LLM output into character-level annotations.

The LLM returns a roster of named entities plus the sentences that mention
them (see :mod:`.schema`); the annotation format wants ``{"start", "end"}``
code-point offsets over the document, grouped per entity. This module bridges
the two:

1. each quoted **sentence** is located in the document, which gives a window —
   once for every mention inside it;
2. each mention's **fragments** are located inside that window, in order, which
   gives one :class:`Fragment` each;
3. offsets are mapped back to the *original* text, and the mention is filed
   under the entity it **names**.

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

from .schema import Annotation, MentionCandidate, SentenceMentions, split_fragments

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
UNKNOWN_ENTITY = "unknown-entity"
DUPLICATE_NAME = "duplicate-name"
UNUSED_ENTITY = "unused-entity"

# How close a mention's entity name has to be to a declared one to count as the
# same (difflib ratio), when it matches neither exactly nor as a shortened form.
_NAME_SIMILARITY = 0.8


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


def _fragment_from_json(value: Any) -> Fragment:
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise ValueError("fragment pair must be [start, end]")
        start, end = value
    else:
        start, end = value["start"], value["end"]
    if int(end) <= int(start) or int(start) < 0:
        raise ValueError(f"invalid fragment ({start}, {end})")
    return Fragment(start=int(start), end=int(end))


def entities_from_json(entities: Iterable[dict]) -> List[Entity]:
    """Parse entities in the annotation schema — the inverse of :func:`entities_to_json`.

    Tolerant in the same ways the annotator's own loader is: a continuous
    mention may arrive as ``{"start", "end"}`` or as a ``[start, end]`` pair,
    and a split one as ``{"fragments": [...]}``.
    """
    out: List[Entity] = []
    for entity in entities:
        mentions: List[Mention] = []
        for mention in entity.get("mentions", []):
            if isinstance(mention, dict) and "fragments" in mention:
                fragments = [_fragment_from_json(f) for f in mention["fragments"]]
            else:
                fragments = [_fragment_from_json(mention)]
            flags = mention if isinstance(mention, dict) else {}
            mentions.append(
                Mention(
                    fragments=fragments,
                    relative=bool(flags.get("relative", False)),
                    implicit=bool(flags.get("implicit", False)),
                )
            )
        out.append(Entity(type=str(entity["type"]), mentions=mentions))
    return out


@dataclass(frozen=True)
class Problem:
    """Something the grounding could not take at face value.

    ``dropped`` distinguishes a lost mention from a recovered one: a mention
    whose sentence was not found is still resolved by searching the whole
    document, but the ambiguity is worth surfacing. The remaining fields are
    whatever context that particular problem has — the entity it named, the
    quoted mention and sentence, and ``detail`` for anything else (a validation
    error, the entity a near-miss was matched to).
    """

    reason: str
    dropped: bool
    name: str = ""
    mention: str = ""
    sentence: str = ""
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
    cursor: int,
) -> List[Tuple[int, int]]:
    """Occurrences of ``needle`` in ``hay[lo:hi]``, best candidates first.

    Ranked by, in order: whole-word matches over mid-word ones; positions at or
    after ``cursor``, which is where the previous mention of this group started
    — mentions are reported in document order, so "Alice … then Alice" walks
    forward instead of piling onto the first occurrence; spans that are not an
    exact copy of one already used, which keeps two same-named entities in one
    sentence off the same span; and finally position, so the earliest candidate
    wins. All are preferences, not filters — a nested mention ("Washington"
    inside "George Washington", "America" inside "Bank of America") overlaps
    something already taken and still resolves there.
    """
    used = set(taken)
    spans = list(_iter_occurrences(hay, needle, lo, hi))
    spans.sort(key=lambda s: (not _word_aligned(hay, *s), s[0] < cursor, s in used, s[0]))
    return spans


def _place_fragments(
    hay: str,
    parts: Sequence[str],
    lo: int,
    hi: int,
    taken: Sequence[Tuple[int, int]],
    cursor: int = 0,
) -> Optional[List[Tuple[int, int]]]:
    """Locate every fragment inside ``hay[lo:hi]``, left to right.

    Backtracks, so an early fragment matching in a spot that leaves no room for
    the rest does not sink the whole mention. ``cursor`` orders the candidates
    for the mention's *first* fragment; the rest simply follow their
    predecessor.
    """
    if not parts:
        return None
    for span in _candidate_spans(hay, parts[0], lo, hi, taken, cursor):
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
        cursor = lo
        placements: List[Optional[List[Tuple[int, int]]]] = []
        for p in parts:
            spans = _place_fragments(doc.text, p, lo, hi, trial, cursor) if p else None
            placements.append(spans)
            if spans is not None:
                trial.extend(spans)
                # The next mention starts at or after this one — but not at the
                # same place, or a repeated word would resolve twice over.
                cursor = spans[0][0] + 1
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


class _Roster:
    """The declared entities, and the lookup from a mention's ``entity`` to one.

    Names are resolved leniently — different case or punctuation, a shortened
    form ("Obama" for "Barack Obama") where it is unambiguous, or a near miss —
    but never invented: a name that matches nothing is reported, because without
    a roster entry there is no type to give the entity.
    """

    def __init__(self, resolution: "Resolution") -> None:
        self.order: List[str] = []
        self.type: dict = {}
        self.mentions: dict = {}
        self.seen: dict = {}
        self._by_key: dict = {}
        self._resolution = resolution

    def declare(self, candidate: Any) -> None:
        name = candidate.name
        if name in self.type:
            self._resolution.problems.append(
                Problem(
                    reason=DUPLICATE_NAME,
                    dropped=True,
                    name=name,
                    detail="two entities declared under one name",
                )
            )
            return
        self.order.append(name)
        self.type[name] = candidate.type.value
        self.mentions[name] = []
        self.seen[name] = set()
        key = _name_key(name)
        if key and key not in self._by_key:
            self._by_key[key] = name

    def resolve(self, name: str) -> Optional[str]:
        """The declared entity a mention's ``entity`` refers to, if any."""
        if name in self.type:
            return name
        key = _name_key(name)
        if not key:
            return None
        if key in self._by_key:
            return self._by_key[key]
        # "Obama" for "Barack Obama" — but only while it stays unambiguous.
        contained = [k for k in self._by_key if key in k or k in key]
        if len(contained) == 1:
            return self._by_key[contained[0]]
        close = difflib.get_close_matches(key, self._by_key, n=1, cutoff=_NAME_SIMILARITY)
        return self._by_key[close[0]] if close else None


def _name_key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def resolve_entities(text: str, annotation: Any) -> Resolution:
    """Convert a quoted, named-entity prediction into offset-based entities.

    ``text`` is the document exactly as it was shown to the model.
    ``annotation`` is an :class:`~.schema.Annotation` or anything that parses as
    one — ``{"entities": [...], "sentences": [...]}`` straight from an LM
    response, say. One that does not parse is reported rather than raising.

    Entities come back in roster order, each carrying the mentions filed under
    its name, in document order. Declared entities that no mention referenced
    are dropped, and so are mentions naming an entity that matches nothing.
    """
    resolution = Resolution()
    try:
        parsed = (
            annotation
            if isinstance(annotation, Annotation)
            else Annotation.model_validate(annotation)
        )
    except ValidationError as exc:
        resolution.problems.append(
            Problem(reason=INVALID_CANDIDATE, dropped=True, detail=_first_error(exc))
        )
        return resolution

    doc = _Normalized(text)
    roster = _Roster(resolution)
    for candidate in parsed.entities:
        roster.declare(candidate)

    taken: List[Tuple[int, int]] = []
    for group in parsed.sentences:
        for raw, mention, reason in _resolve_group(doc, group, taken):
            name = roster.resolve(raw.entity) if mention is not None else None
            if mention is not None and name is None:
                mention, reason = None, UNKNOWN_ENTITY
            elif mention is not None and _mention_key(mention) in roster.seen[name]:
                mention, reason = None, DUPLICATE_MENTION
            if mention is not None:
                roster.seen[name].add(_mention_key(mention))
                roster.mentions[name].append(mention)
            if reason is not None:
                resolution.problems.append(
                    Problem(
                        reason=reason,
                        dropped=mention is None,
                        name=raw.entity,
                        mention=raw.text,
                        sentence=group.sentence,
                        detail=(
                            f"matched to {name!r}"
                            if name is not None and name != raw.entity
                            else ""
                        ),
                    )
                )

    for name in roster.order:
        mentions = roster.mentions[name]
        # An entity with nothing to point at is not annotation, it is noise —
        # but a declared-and-never-mentioned entity is worth saying out loud.
        if not mentions:
            resolution.problems.append(Problem(reason=UNUSED_ENTITY, dropped=True, name=name))
            continue
        mentions.sort(key=lambda m: (m.fragments[0].start, m.fragments[-1].end))
        resolution.entities.append(Entity(type=roster.type[name], mentions=mentions))

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
