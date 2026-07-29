"""The guidelines the prompt is built from, and the entity types they define.

Two files under ``guidelines/`` are the single source of truth, and they are
meant to be edited:

``general.md``     how to report annotations — clustering, quoting, grouping
                   mentions by sentence, fragments, the two flags. Type-agnostic.
``entities.json``  one entry per entity type, keyed by the label written to the
                   annotation, each with a one-line ``description`` and its full
                   ``guidelines``.

Adding a type to ``entities.json`` is all it takes: it joins :data:`EntityType`,
the prompt, and the accepted output — no code change. Nothing here imports the
signature, so the registry can be read (and rendered) without DSPy installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional

GUIDELINES_DIR = Path(__file__).parent / "guidelines"
GENERAL_PATH = GUIDELINES_DIR / "general.md"
ENTITIES_PATH = GUIDELINES_DIR / "entities.json"


@dataclass(frozen=True)
class EntityGuideline:
    """One entity type: its label, its one-line gloss, and its full rules."""

    type: str
    description: str
    guidelines: str


def _as_text(value: object, where: str) -> str:
    # A long guideline body is painful as one JSON string, so a list of lines is
    # accepted too and joined back together.
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and all(isinstance(line, str) for line in value):
        return "\n".join(value).strip()
    raise ValueError(f"{where} must be a string or a list of strings")


def load_entity_guidelines(path: Path = ENTITIES_PATH) -> Dict[str, EntityGuideline]:
    """Read ``entities.json``. Keys starting with ``$`` are comments."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, EntityGuideline] = {}
    for key, entry in raw.items():
        if key.startswith("$"):
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"{path.name}: entry {key!r} must be an object")
        description = _as_text(entry.get("description", ""), f"{key}.description")
        guidelines = _as_text(entry.get("guidelines", ""), f"{key}.guidelines")
        if not description or not guidelines:
            raise ValueError(f"{path.name}: entry {key!r} needs a description and guidelines")
        out[key] = EntityGuideline(type=key, description=description, guidelines=guidelines)
    if not out:
        raise ValueError(f"{path.name}: no entity types defined")
    return out


GENERAL_GUIDELINES: str = GENERAL_PATH.read_text(encoding="utf-8").strip()
ENTITY_GUIDELINES: Dict[str, EntityGuideline] = load_entity_guidelines()

# The label set as an enum, so a predicted type is validated against the file
# (and offered to the model as a closed list) instead of taken on faith.
# ``EntityType.PER.value == "PER"``.
EntityType = Enum(  # type: ignore[misc]
    "EntityType",
    {key: key for key in ENTITY_GUIDELINES},
    type=str,
    module=__name__,
)
EntityType.__doc__ = "Entity types defined in guidelines/entities.json."


def guidelines_for(entity_type: object) -> EntityGuideline:
    """Look a type up by label or :data:`EntityType` member."""
    key = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
    try:
        return ENTITY_GUIDELINES[key]
    except KeyError:
        known = ", ".join(ENTITY_GUIDELINES)
        raise KeyError(f"unknown entity type {key!r}; known types: {known}") from None


def _selected(types: Optional[Iterable[object]]) -> List[EntityGuideline]:
    if types is None:
        return list(ENTITY_GUIDELINES.values())
    return [guidelines_for(t) for t in types]


def entity_types_block(types: Optional[Iterable[object]] = None) -> str:
    """The one-line index of types: ``PER — An individual human being...``."""
    return "\n".join(f"{g.type} — {g.description}" for g in _selected(types))


def entity_guidelines_block(types: Optional[Iterable[object]] = None) -> str:
    """The full per-type rules, prefixed by the index, as one prompt block.

    This is what fills the signature's ``entity_guidelines`` input: every type's
    key and description up front, so an entity can be classified at a glance,
    then the rules for each.
    """
    sections = [
        "Annotate entities of these types, and no others:",
        entity_types_block(types),
    ]
    for g in _selected(types):
        sections.append(f"# {g.type} — {g.description}\n\n{g.guidelines}")
    return "\n\n".join(sections)
