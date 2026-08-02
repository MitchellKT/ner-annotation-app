"""LLM-assisted annotation: a DSPy signature plus grounding to character offsets.

The LLM quotes text rather than counting characters: it returns a roster of
labelled entities and then the sentences that mention them, each sentence
quoted once and each mention tagged with its entity's label (fragments of a
split mention joined by ``[…]``). :mod:`.grounding` turns that into character
offsets. One signature annotates every entity type in
``guidelines/entities.json``.

The pieces split by dependency: :mod:`.schema`, :mod:`.guidelines` and
:mod:`.grounding` are plain pydantic/stdlib and always importable, while
:mod:`.signatures` needs DSPy and is therefore imported lazily — ``from
ner_annotator_llm import EntityAnnotator`` raises only if DSPy is genuinely
missing.
"""

from __future__ import annotations

from typing import Any

from .examples import (
    examples_from_jsonl,
    examples_from_records,
    sentence_spans,
    to_annotation,
    to_example,
)
from .grounding import (
    Entity,
    Fragment,
    Mention,
    Problem,
    Resolution,
    entities_from_json,
    entities_to_json,
    resolve_entities,
    unicode_safe,
)
from .guidelines import (
    ENTITY_GUIDELINES,
    GENERAL_GUIDELINES,
    EntityGuideline,
    EntityType,
    entity_guidelines_block,
    entity_types_block,
    guidelines_for,
)
from .schema import (
    FRAGMENT_SEPARATOR,
    Annotation,
    EntityCandidate,
    MentionCandidate,
    SentenceMentions,
    split_fragments,
)

__all__ = [
    "AnnotateEntities",
    "Annotation",
    "ENTITY_GUIDELINES",
    "Entity",
    "EntityAnnotator",
    "EntityCandidate",
    "EntityGuideline",
    "EntityType",
    "FRAGMENT_SEPARATOR",
    "Fragment",
    "GENERAL_GUIDELINES",
    "Mention",
    "MentionCandidate",
    "Problem",
    "Resolution",
    "SentenceMentions",
    "entities_from_json",
    "entities_to_json",
    "entity_guidelines_block",
    "entity_types_block",
    "examples_from_jsonl",
    "examples_from_records",
    "guidelines_for",
    "resolve_entities",
    "sentence_spans",
    "split_fragments",
    "to_annotation",
    "to_example",
    "unicode_safe",
]

_LAZY = {"AnnotateEntities", "EntityAnnotator"}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from . import signatures

        return getattr(signatures, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
