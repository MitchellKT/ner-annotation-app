"""Turn quoted LLM output into character-level annotations.

The LLM returns a roster of named entities plus the sentences that mention them
(see :mod:`.schema`); the annotation format wants ``{"start", "end"}``
code-point offsets over the document. This module bridges the two, and the whole
of it is one idea applied twice: **look for the exact text, and fall back to a
fuzzy match when it is not there.**

1. the quoted **sentence** is located in the document — exactly, else fuzzily —
   which gives a window;
2. each mention's **fragments** are located inside that window the same way,
   left to right;
3. the mention is filed under the entity it names, matched against the roster
   exactly, else fuzzily.

What does not match is dropped and listed in :attr:`Resolution.unresolved`;
nothing is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Any, Iterable, List, Optional, Tuple

from .schema import Annotation, MentionCandidate, split_fragments

Span = Tuple[int, int]

# A fuzzy match has to share a run this long with what it is matching — as a
# fraction of it, and at least a few characters. Scattered letters in common are
# not a match: better a dropped mention than one placed at random.
_MIN_ANCHOR = 0.5
_MIN_ANCHOR_CHARS = 3
# How close a mention's entity name has to be to a declared one to be the same.
_MIN_NAME_SIMILARITY = 0.6


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


def entities_to_json(entities: Iterable[Entity]) -> List[dict]:
    """Serialise entities to the annotation schema."""
    return [e.to_json() for e in entities]


def entities_from_json(entities: Iterable[dict]) -> List[Entity]:
    """Parse entities in the annotation schema — the inverse of :func:`entities_to_json`."""
    return [
        Entity(
            type=entity["type"],
            mentions=[
                Mention(
                    fragments=[
                        Fragment(f["start"], f["end"])
                        for f in mention.get("fragments", [mention])
                    ],
                    relative=mention.get("relative", False),
                    implicit=mention.get("implicit", False),
                )
                for mention in entity["mentions"]
            ],
        )
        for entity in entities
    ]


@dataclass
class Resolution:
    """The grounded entities, plus the mentions that could not be placed."""

    entities: List[Entity] = field(default_factory=list)
    unresolved: List[MentionCandidate] = field(default_factory=list)

    def to_json(self) -> List[dict]:
        """The entities in the annotation schema, ready to store."""
        return entities_to_json(self.entities)

    @property
    def n_mentions(self) -> int:
        return sum(len(e.mentions) for e in self.entities)


def _find_exact(text: str, needle: str, lo: int, hi: int) -> Optional[Span]:
    """First occurrence of ``needle`` in ``text[lo:hi]``, whole words preferred.

    The word-boundary pass matters more than it looks: mentions are often
    pronouns, and a plain search puts "he" inside "The".
    """
    left = r"\b" if needle[:1].isalnum() else ""
    right = r"\b" if needle[-1:].isalnum() else ""
    match = re.compile(left + re.escape(needle) + right).search(text, lo, hi)
    if match:
        return match.span()
    index = text.find(needle, lo, hi)
    return (index, index + len(needle)) if index != -1 else None


def _find_fuzzy(text: str, needle: str, lo: int, hi: int) -> Optional[Span]:
    """Where ``needle`` approximately sits in ``text[lo:hi]``.

    Spans from the first matching block to the last, so a mention the model
    retyped with different spacing or punctuation still covers the right
    characters. Anchored on a substantial shared run, so an answer the document
    simply does not contain is refused rather than placed somewhere plausible.
    """
    matcher = SequenceMatcher(None, text[lo:hi], needle, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size]
    if not blocks or max(b.size for b in blocks) < max(
        _MIN_ANCHOR_CHARS, _MIN_ANCHOR * len(needle)
    ):
        return None
    return lo + blocks[0].a, lo + blocks[-1].a + blocks[-1].size


def _locate(text: str, needle: str, lo: int, hi: int) -> Optional[Span]:
    """Exact match if there is one, fuzzy match otherwise."""
    return _find_exact(text, needle, lo, hi) or _find_fuzzy(text, needle, lo, hi)


def _place(text: str, mention: str, lo: int, hi: int, cursor: int) -> Optional[List[Span]]:
    """Locate a mention's fragments inside ``text[lo:hi]``, in order.

    Each fragment is looked for from ``cursor`` onwards — mentions are reported
    in document order, so "Alice … then Alice" walks forward — then anywhere in
    the window, which is what lets a nested mention ("Obama" inside "Barack
    Obama") land where it belongs.
    """
    spans: List[Span] = []
    for part in split_fragments(mention):
        span = _find_exact(text, part, cursor, hi) or _locate(text, part, lo, hi)
        if span is None:
            return None
        spans.append(span)
        cursor = span[1]
    return spans or None


def resolve_entities(text: str, annotation: Any) -> Resolution:
    """Convert a quoted, named-entity prediction into offset-based entities.

    ``text`` is the document exactly as it was shown to the model.
    ``annotation`` is an :class:`~.schema.Annotation` or anything that parses as
    one — ``{"entities": [...], "sentences": [...]}`` straight from an LM
    response, say.

    Entities come back in roster order, each carrying its mentions in document
    order. Entities nobody mentioned are dropped, and so are mentions that name
    no known entity or quote text the document does not contain.
    """
    parsed = (
        annotation if isinstance(annotation, Annotation) else Annotation.model_validate(annotation)
    )
    types = {e.name: e.type.value for e in parsed.entities}
    mentions: dict = {name: [] for name in types}
    resolution = Resolution()

    for group in parsed.sentences:
        lo, hi = _locate(text, group.sentence, 0, len(text)) or (0, len(text))
        cursor = lo
        for candidate in group.mentions:
            name = _match_name(candidate.entity, types)
            spans = _place(text, candidate.text, lo, hi, cursor)
            if name is None or spans is None:
                resolution.unresolved.append(candidate)
                continue
            # The next mention starts at or after this one — but not at the same
            # place, or a repeated word would resolve twice over.
            cursor = spans[0][0] + 1
            mentions[name].append(
                Mention(
                    fragments=[Fragment(*span) for span in spans],
                    relative=candidate.relative,
                    implicit=candidate.implicit,
                )
            )

    for name, found in mentions.items():
        if found:
            found.sort(key=lambda m: m.fragments[0].start)
            resolution.entities.append(Entity(type=types[name], mentions=found))
    return resolution


def _match_name(name: str, known: dict) -> Optional[str]:
    """The declared entity a mention names — exactly, else the closest one."""
    if name in known:
        return name
    close = get_close_matches(name, known, n=1, cutoff=_MIN_NAME_SIMILARITY)
    return close[0] if close else None
