"""The shape the LLM answers in — mentions quoted as *text*, not offsets.

An LLM cannot reliably count characters, so it is never asked for ``start`` /
``end``. Instead every mention is returned as two verbatim quotations:

* ``mention``  — the mention's surface form, exactly as it appears in the text;
* ``sentence`` — the surrounding sentence, which anchors the mention to one
  place in the document (``Obama`` may occur five times; the sentence says
  which occurrence is meant).

A **non-continuous** mention is written as its fragments joined by
``[…]`` — e.g. ``"Annie[…]Washington"`` for the mention *Annie Washington* in
*"Annie and George Washington visited Mount Vernon."*.

:mod:`.grounding` turns this into the annotation schema
(:class:`~.grounding.Entity` with character-level fragments).
"""

from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

# What the model is told to put between the fragments of a non-continuous
# mention. The parser below is deliberately more permissive than this.
FRAGMENT_SEPARATOR = "[…]"

# "[…]", "[...]", "[ .. ]" — the bracketed form the prompt asks for.
_BRACKETED_SEPARATOR_RE = re.compile(r"\s*\[\s*(?:…|\.\s*\.\s*\.?\s*)\]\s*")
# "Annie … Washington" — the same intent without the brackets, accepted as a
# fallback so a slightly off-format answer is still usable.
_BARE_SEPARATOR_RE = re.compile(r"\s*(?:…|\.{3,})\s*")


def split_fragments(mention: str) -> List[str]:
    """Split a mention string into its fragment surface forms.

    ``"Annie[…]Washington"`` -> ``["Annie", "Washington"]``; a continuous
    mention yields a single-item list. Blank pieces are dropped, so a stray
    leading/trailing separator is harmless.
    """
    parts = _BRACKETED_SEPARATOR_RE.split(mention)
    if len(parts) == 1:
        parts = _BARE_SEPARATOR_RE.split(mention)
    return [p.strip() for p in parts if p.strip()]


class MentionCandidate(BaseModel):
    """One predicted mention, quoted rather than offset."""

    model_config = ConfigDict(extra="ignore")

    mention: str = Field(
        description=(
            "The mention exactly as it appears in the text, copied character for "
            "character. For a non-continuous mention, join the fragments with "
            "'[…]', e.g. 'Annie[…]Washington'."
        )
    )
    sentence: str = Field(
        description=(
            "The full sentence containing the mention, copied verbatim from the "
            "text. It is what pins the mention to one position in the document, "
            "so it must be reproduced exactly and must contain the mention."
        )
    )
    relative: bool = Field(
        default=False,
        description=(
            "True when the mention refers to the entity only through a relation "
            "to someone/something else ('father of Abraham', \"John's secretary\") "
            "instead of naming it."
        ),
    )
    implicit: bool = Field(
        default=False,
        description=(
            "True when the mention names the entity directly but in a "
            "background, non-subject role — the sentence is not about it "
            "('Maxim' in 'I went to the theatre with Maxim's brother')."
        ),
    )

    @field_validator("mention", "sentence", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return "" if value is None else str(value).strip()


class EntityCandidate(BaseModel):
    """A predicted entity: one real-world referent and all mentions of it."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(
        default="",
        description=(
            "Short label for the entity, used only to keep the clustering "
            "readable (e.g. 'Barack Obama'). Not part of the stored annotation."
        )
    )
    type: str = Field(default="PER", description="Entity type, e.g. 'PER'.")
    mentions: List[MentionCandidate] = Field(
        default_factory=list,
        description=(
            "Every mention of this entity, in the order they appear in the text. "
            "Two mentions of the same referent always belong to the same entity; "
            "two different referents are never merged, even when they share a name."
        ),
    )
