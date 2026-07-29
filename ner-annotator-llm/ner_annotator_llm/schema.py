"""The shape the LLM answers in — mentions quoted as *text*, not offsets.

An LLM cannot reliably count characters, so it is never asked for ``start`` /
``end``. It quotes instead, and mentions are **grouped by sentence**::

    EntityCandidate(
        name="Barack Obama",
        type=EntityType.PER,
        sentences=[SentenceMentions(
            sentence="Obama said that he and his wife had left Chicago.",
            mentions=[MentionCandidate(text="Obama"),
                      MentionCandidate(text="he"),
                      MentionCandidate(text="his")],
        )],
    )

One quoted sentence carries every mention of that entity inside it, in order of
appearance. That is the layout a model is most likely to be exhaustive in: the
expensive quotation is written once, so listing four mentions of an entity in
one sentence costs four short strings instead of four repetitions of the
sentence. The sentence still does the disambiguating work — it says *which*
occurrence of "Obama" is meant when the document has five.

A **non-continuous** mention is written as its fragments joined by ``[…]`` —
e.g. ``"Annie[…]Washington"`` for the mention *Annie Washington* in *"Annie and
George Washington visited Mount Vernon."*.

:mod:`.grounding` turns this into the annotation schema
(:class:`~.grounding.Entity` with character-level fragments).
"""

from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .guidelines import EntityType

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

    text: str = Field(
        description=(
            "The mention exactly as it appears in the text, copied character for "
            "character. For a non-continuous mention, join the fragments with "
            "'[…]', e.g. 'Annie[…]Washington'."
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

    @field_validator("text", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return "" if value is None else str(value).strip()


class SentenceMentions(BaseModel):
    """Every mention of one entity inside one sentence."""

    model_config = ConfigDict(extra="ignore")

    sentence: str = Field(
        description=(
            "The full sentence, copied verbatim from the text. It locates the "
            "mentions below, so it must be reproduced exactly; when the same "
            "wording occurs twice in the document, quote the occurrence meant."
        )
    )
    mentions: List[MentionCandidate] = Field(
        default_factory=list,
        description=(
            "Every mention of this entity in that sentence, in the order they "
            "appear — including repeats of the same wording and mentions nested "
            "in one another. Do not deduplicate: three references means three "
            "entries, and they are matched left to right."
        ),
    )

    @field_validator("sentence", mode="before")
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
        ),
    )
    type: EntityType = Field(
        description="Which of the listed entity types this entity belongs to."
    )
    sentences: List[SentenceMentions] = Field(
        default_factory=list,
        description=(
            "One entry per sentence that contains mentions of this entity, in "
            "document order. Two mentions of the same referent always belong to "
            "the same entity; two different referents are never merged, even "
            "when they share a name."
        ),
    )
