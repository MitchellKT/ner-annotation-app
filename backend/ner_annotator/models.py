"""Pydantic models for the on-disk JSONL schema.

The required record shape (input and output) is::

    {"doc_id": "...", "text": "...", "entities": [
        {"type": "PER", "mentions": [{"start": 10, "end": 15}]}
    ]}

``end`` is *exclusive* (``text[start:end]``). A mention is one or more
non-overlapping *fragments*, which makes non-continuous mentions expressible
(e.g. "Annie … Washington" in "Annie and George Washington")::

    {"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5},
                                                {"start": 17, "end": 27}]}]}

An entity may also carry ``uid`` (an external identifier) and ``tags`` (free-form
labels shared between annotators via the workspace tag bank)::

    {"type": "PER", "mentions": [{"start": 0, "end": 5}], "tags": ["fictional"]}

A document may carry ``comments`` — document-level notes shared between
annotators, each stamped with its author and the time it was written::

    {"doc_id": "...", "text": "...", "entities": [],
     "comments": [{"author": "Alice", "text": "unsure about the last sentence",
                   "created_at": "2026-07-21T09:12:04Z"}]}

The loader is tolerant: a continuous mention may be given as ``{"start","end"}``
or a ``[start, end]`` pair (fragments accept the pair form too), and ``type`` is
accepted as a free string so model/LLM predictions with non-canonical labels
still import (the UI flags anything outside the canonical set). On output a
single-fragment mention is written back as plain ``{"start","end"}``, so files
without non-continuous mentions keep the original schema.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Canonical entity types. ``type`` is stored as a plain string (not a Literal) so
# that importing predictions never hard-fails on an unexpected label.
CANONICAL_TYPES = ("PER", "LOC", "ORG", "TIME")

# Author recorded for a comment that arrives without one (e.g. hand-written
# input), so every comment can be attributed to *something* in the UI.
UNKNOWN_AUTHOR = "unknown"


def utc_now_iso() -> str:
    """Second-resolution UTC timestamp, e.g. ``2026-07-21T09:12:04Z``."""
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


class Fragment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: int
    end: int

    @model_validator(mode="before")
    @classmethod
    def _coerce_pair(cls, value: Any) -> Any:
        # Accept [start, end] / (start, end) in addition to {"start","end"}.
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError("fragment pair must have exactly 2 items [start, end]")
            return {"start": value[0], "end": value[1]}
        return value

    @model_validator(mode="after")
    def _check_order(self) -> "Fragment":
        if self.end <= self.start:
            raise ValueError(f"fragment end ({self.end}) must be > start ({self.start})")
        if self.start < 0:
            raise ValueError(f"fragment start ({self.start}) must be >= 0")
        return self


class Mention(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fragments: List[Fragment]
    # A *relative* mention refers to its entity only through a relation to some
    # other entity (e.g. "father of Abraham", "John's secretary") rather than
    # naming it directly. Defaults to False; omitted from the output when False,
    # so files without relative mentions keep the original schema.
    relative: bool = False
    # An *implicit* mention names its entity directly but in a non-subject,
    # background role — the entity is not what the sentence is about (e.g.
    # "Maxim" in "I went to the theatre with Maxim's brother"). Like ``relative``
    # it is a purely descriptive flag, defaults to False, and is omitted from the
    # output when False, so files without implicit mentions keep the schema. The
    # two flags are independent: a mention may be neither, either, or both.
    implicit: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_forms(cls, value: Any) -> Any:
        # Accept the continuous forms — {"start","end"} or [start, end] — as a
        # single-fragment mention, plus the explicit {"fragments": [...]} form.
        # The mention-level ``relative`` / ``implicit`` flags ride along on the
        # continuous {"start","end","relative","implicit"} form, so lift them out
        # before wrapping the span as the sole fragment (Fragment ignores the
        # extra keys otherwise).
        if isinstance(value, (list, tuple)):
            return {"fragments": [value]}
        if isinstance(value, dict) and "fragments" not in value:
            return {
                "fragments": [value],
                "relative": value.get("relative", False),
                "implicit": value.get("implicit", False),
            }
        return value

    @model_validator(mode="after")
    def _normalize(self) -> "Mention":
        if not self.fragments:
            raise ValueError("mention must have at least one fragment")
        self.fragments = merge_fragments(self.fragments)
        return self


def merge_fragments(fragments: List[Fragment]) -> List[Fragment]:
    """Sort fragments and coalesce overlapping/adjacent ones."""
    ordered = sorted(fragments, key=lambda f: (f.start, f.end))
    merged: List[Fragment] = [ordered[0]]
    for f in ordered[1:]:
        last = merged[-1]
        if f.start <= last.end:
            merged[-1] = Fragment(start=last.start, end=max(last.end, f.end))
        else:
            merged.append(f)
    return merged


class Entity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    mentions: List[Mention]
    # Optional external unique identifier for the entity (e.g. a Wikidata QID
    # or knowledge-base key). Omitted from the output when not set.
    uid: Optional[str] = None
    # Free-form labels drawn from the workspace-wide tag bank. Tags are taken
    # verbatim (any script — Hebrew, Arabic, emoji — is fine); only surrounding
    # whitespace is trimmed. Omitted from the output when empty.
    tags: List[str] = []

    @field_validator("type", mode="before")
    @classmethod
    def _stringify_type(cls, value: Any) -> Any:
        return str(value) if value is not None else value

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> Any:
        if value is None:
            return []
        # A bare string is accepted as a one-tag list.
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise ValueError("tags must be a list of strings")
        out: List[str] = []
        seen = set()
        for tag in value:
            name = str(tag).strip()
            # Blank tags are meaningless; exact duplicates collapse. Case is
            # preserved and significant, so "NATO" and "nato" stay distinct.
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
        return out

    @field_validator("uid", mode="before")
    @classmethod
    def _normalize_uid(cls, value: Any) -> Any:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class Comment(BaseModel):
    """One document-level note, shared with every annotator.

    ``author`` is the username of whoever wrote it and ``created_at`` an
    ISO-8601 UTC timestamp; both are filled in when missing so a hand-written
    ``{"text": "..."}`` still loads.
    """

    model_config = ConfigDict(extra="ignore")

    author: str = ""
    text: str
    created_at: str = ""

    @field_validator("author", "text", "created_at", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> Any:
        # Comment bodies are free-form in any script; only the outer whitespace
        # goes, so internal line breaks and indentation survive the round-trip.
        return "" if value is None else str(value).strip()

    @model_validator(mode="after")
    def _fill_defaults(self) -> "Comment":
        if not self.text:
            raise ValueError("comment text must be non-empty")
        if not self.author:
            self.author = UNKNOWN_AUTHOR
        if not self.created_at:
            self.created_at = utc_now_iso()
        return self


class Doc(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: str
    text: str
    entities: List[Entity] = []
    # Document-level annotator notes. Unlike entities these are *not* per-user:
    # the workspace keeps one shared thread per document and every annotator's
    # output carries it. Omitted from the output when empty.
    comments: List[Comment] = []
    # Optional document metadata forming a three-level hierarchy: ``type`` is the
    # kind of text (e.g. "news"), ``category`` groups sources within a type
    # (e.g. "print press"), and ``source`` is where it came from (e.g. a site).
    # All are free strings; missing values are surfaced as "unspecified" by the
    # store.
    type: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None

    @field_validator("doc_id", mode="before")
    @classmethod
    def _stringify_id(cls, value: Any) -> Any:
        return str(value) if value is not None else value

    @field_validator("type", "category", "source", mode="before")
    @classmethod
    def _normalize_meta(cls, value: Any) -> Any:
        if value is None:
            return None
        value = str(value).strip()
        return value or None
