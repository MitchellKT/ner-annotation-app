"""LLM-assisted annotation: a DSPy signature plus grounding to character offsets.

This package is **self-contained**: it imports nothing from the rest of the
application, so the directory can be copied into another project as-is. Its only
third-party dependencies are pydantic (schema) and DSPy (signature only).

The pieces split by dependency: :mod:`.schema`, :mod:`.guidelines` and
:mod:`.grounding` are plain pydantic/stdlib and always importable, while
:mod:`.signatures` needs DSPy and is therefore imported lazily — ``from
ner_annotator.llm import EntityAnnotator`` raises only if DSPy is genuinely
missing.
"""

from __future__ import annotations

from typing import Any

from .grounding import (
    Entity,
    Fragment,
    Mention,
    Problem,
    Resolution,
    entities_to_json,
    resolve_entities,
    unicode_safe,
)
from .guidelines import GUIDELINES, PERSON_GUIDELINES, guidelines_for
from .schema import FRAGMENT_SEPARATOR, EntityCandidate, MentionCandidate, split_fragments

__all__ = [
    "AnnotateEntities",
    "Entity",
    "EntityAnnotator",
    "EntityCandidate",
    "FRAGMENT_SEPARATOR",
    "Fragment",
    "GUIDELINES",
    "Mention",
    "MentionCandidate",
    "PERSON_GUIDELINES",
    "Problem",
    "Resolution",
    "entities_to_json",
    "guidelines_for",
    "resolve_entities",
    "split_fragments",
    "unicode_safe",
]

_LAZY = {"AnnotateEntities", "EntityAnnotator"}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from . import signatures

        return getattr(signatures, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
