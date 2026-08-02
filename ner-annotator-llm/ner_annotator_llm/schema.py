"""The shape the LLM answers in — quoted text and entity labels, not offsets.

An LLM cannot reliably count characters, so it is never asked for ``start`` /
``end``. It answers in two parts instead: a **roster** of the distinct entities
in the document, each with a short unique label, and then the **sentences**,
each quoted once and carrying every mention in it, tagged with the label of the
entity it refers to::

    Annotation(
        entities=[EntityCandidate(label="e1", type=PER, name="Barack Obama"),
                  EntityCandidate(label="e2", type=PER, name="Michelle Obama"),
                  EntityCandidate(label="e3", type=LOC, name="Chicago")],
        sentences=[SentenceMentions(
            sentence="Obama said that he and his wife had left Chicago.",
            mentions=[MentionCandidate(label="e1", text="Obama"),
                      MentionCandidate(label="e1", text="he"),
                      MentionCandidate(label="e1", text="his", implicit=True),
                      MentionCandidate(label="e2", text="his wife", relative=True),
                      MentionCandidate(label="e3", text="Chicago")]),
        ],
    )

Every sentence is quoted **once for the whole document** rather than once per
entity that occurs in it, which is where the answer's cost is: on a paragraph
with several entities per sentence this is around half the output of quoting
per entity, and the model walks the text once instead of re-reading it per
entity. The sentence still does the disambiguating work — it says *which*
occurrence of "Obama" is meant when the document has five.

The price is referential integrity: a mention's ``label`` has to exist in the
roster. :mod:`.grounding` resolves labels leniently and reports what it cannot
match rather than guessing.

A **non-continuous** mention is written as its fragments joined by ``[…]`` —
e.g. ``"Annie[…]Washington"`` for the mention *Annie Washington* in *"Annie and
George Washington visited Mount Vernon."*.
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


def _stripped(value: object) -> str:
    return "" if value is None else str(value).strip()


class EntityCandidate(BaseModel):
    """One entry in the roster: a distinct referent, its label and its type."""

    model_config = ConfigDict(extra="ignore")

    label: str = Field(
        description=(
            "Short unique identifier for this entity, e.g. 'e1', 'e2'. Every "
            "mention of it carries this exact string, so keep it short and do "
            "not reuse one label for two entities."
        )
    )
    type: EntityType = Field(description="Which of the listed entity types this entity is.")
    name: str = Field(
        default="",
        description=(
            "Readable label for the referent, e.g. 'Barack Obama' — how a person "
            "would name it. Not part of the stored annotation."
        ),
    )

    @field_validator("label", "name", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _stripped(value)


class MentionCandidate(BaseModel):
    """One mention: the text as it appears, and which entity it refers to."""

    model_config = ConfigDict(extra="ignore")

    label: str = Field(
        description="The label of the entity this mention refers to, from the entity list."
    )
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

    @field_validator("label", "text", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _stripped(value)


class SentenceMentions(BaseModel):
    """One sentence and every mention of any entity inside it."""

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
            "Every mention in that sentence, of any entity, in the order they "
            "appear — including repeats of the same wording and mentions nested "
            "in one another. Do not deduplicate: three references means three "
            "entries, and they are matched left to right."
        ),
    )

    @field_validator("sentence", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _stripped(value)


class Annotation(BaseModel):
    """The whole answer: the roster plus the per-sentence mentions.

    The signature returns these as two output fields, in this order — the
    entities are settled before the sentences that refer to them. This model is
    what carries them together through grounding and back.
    """

    model_config = ConfigDict(extra="ignore")

    entities: List[EntityCandidate] = Field(default_factory=list)
    sentences: List[SentenceMentions] = Field(default_factory=list)
