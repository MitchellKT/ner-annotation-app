"""The guidelines the prompt is built from, and the entity types they define.

Everything the prompt says lives under ``guidelines/`` as markdown, and it is
meant to be edited:

``general.md``   how to report annotations — clustering, quoting, grouping
                 mentions by sentence, fragments, the two flags. Type-agnostic.
``entities/``    one file per entity type, named after it: ``PER.md``,
                 ``LOC.md``, … Its first line is a ``# TYPE — one-line
                 description`` heading; the rest is that type's rules.

Dropping a file into ``entities/`` is all it takes: it joins :data:`EntityType`,
the prompt, and the accepted output — no code change. Nothing here imports the
signature, so the guidelines can be read (and rendered) without DSPy installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional

GUIDELINES_DIR = Path(__file__).parent / "guidelines"
GENERAL_PATH = GUIDELINES_DIR / "general.md"
ENTITIES_DIR = GUIDELINES_DIR / "entities"


@dataclass(frozen=True)
class EntityGuideline:
    """One entity type: its label, its one-line gloss, and its full rules."""

    type: str
    description: str
    guidelines: str


def load_entity_guidelines(directory: Path = ENTITIES_DIR) -> Dict[str, EntityGuideline]:
    """Read ``entities/*.md``, one entity type per file, in filename order."""
    out: Dict[str, EntityGuideline] = {}
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        heading = text.splitlines()[0]
        # "# PER — An individual human being." -> the part after the dash.
        description = heading.split("—", 1)[-1].strip().lstrip("#").strip()
        out[path.stem] = EntityGuideline(
            type=path.stem, description=description, guidelines=text
        )
    return out


GENERAL_GUIDELINES: str = GENERAL_PATH.read_text(encoding="utf-8").strip()
ENTITY_GUIDELINES: Dict[str, EntityGuideline] = load_entity_guidelines()

# The type set as an enum, so a predicted type is validated against the files
# (and offered to the model as a closed list). ``EntityType.PER.value == "PER"``.
EntityType = Enum(  # type: ignore[misc]
    "EntityType",
    {key: key for key in ENTITY_GUIDELINES},
    type=str,
    module=__name__,
)
EntityType.__doc__ = "Entity types defined by the files in guidelines/entities/."


def guidelines_for(entity_type: object) -> EntityGuideline:
    """Look a type up by label or :data:`EntityType` member."""
    key = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
    return ENTITY_GUIDELINES[key]


def entity_guidelines_block(types: Optional[Iterable[object]] = None) -> str:
    """Every type's rules as one block, prefixed by an index of the type set.

    This goes into the signature's instructions: the keys and their one-line
    descriptions up front, so an entity can be classified at a glance, then the
    file for each.
    """
    selected: List[EntityGuideline] = (
        list(ENTITY_GUIDELINES.values())
        if types is None
        else [guidelines_for(t) for t in types]
    )
    index = "\n".join(f"{g.type} — {g.description}" for g in selected)
    return "\n\n".join(
        ["# Entity types\n\nAnnotate entities of these types, and no others:", index]
        + [g.guidelines for g in selected]
    )
