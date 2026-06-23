"""Pydantic models for the on-disk JSONL schema.

The required record shape (input and output) is::

    {"doc_id": "...", "text": "...", "entities": [
        {"type": "PER", "mentions": [{"start": 10, "end": 15}]}
    ]}

``end`` is *exclusive* (``text[start:end]``). The loader is tolerant: a mention
may also be given as a ``[start, end]`` pair, and ``type`` is accepted as a free
string so model/LLM predictions with non-canonical labels still import (the UI
flags anything outside the canonical set).
"""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Canonical entity types. ``type`` is stored as a plain string (not a Literal) so
# that importing predictions never hard-fails on an unexpected label.
CANONICAL_TYPES = ("PER", "LOC", "ORG", "TIME")


class Mention(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: int
    end: int

    @model_validator(mode="before")
    @classmethod
    def _coerce_pair(cls, value: Any) -> Any:
        # Accept [start, end] / (start, end) in addition to {"start","end"}.
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError("mention pair must have exactly 2 items [start, end]")
            return {"start": value[0], "end": value[1]}
        return value

    @model_validator(mode="after")
    def _check_order(self) -> "Mention":
        if self.end <= self.start:
            raise ValueError(f"mention end ({self.end}) must be > start ({self.start})")
        if self.start < 0:
            raise ValueError(f"mention start ({self.start}) must be >= 0")
        return self


class Entity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    mentions: List[Mention]

    @field_validator("type", mode="before")
    @classmethod
    def _stringify_type(cls, value: Any) -> Any:
        return str(value) if value is not None else value


class Doc(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: str
    text: str
    entities: List[Entity] = []

    @field_validator("doc_id", mode="before")
    @classmethod
    def _stringify_id(cls, value: Any) -> Any:
        return str(value) if value is not None else value
