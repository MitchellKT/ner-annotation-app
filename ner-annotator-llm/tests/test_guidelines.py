import json

import pytest

from ner_annotator_llm.guidelines import (
    ENTITIES_PATH,
    ENTITY_GUIDELINES,
    GENERAL_GUIDELINES,
    EntityType,
    entity_guidelines_block,
    entity_types_block,
    guidelines_for,
    load_entity_guidelines,
)


def test_general_guidelines_are_loaded():
    assert "sentence" in GENERAL_GUIDELINES.lower()
    assert len(GENERAL_GUIDELINES) > 500


def test_registry_and_enum_come_from_the_same_file():
    on_disk = [k for k in json.loads(ENTITIES_PATH.read_text(encoding="utf-8")) if k[0] != "$"]
    assert list(ENTITY_GUIDELINES) == on_disk
    assert [m.value for m in EntityType] == on_disk
    assert EntityType("PER").value == "PER"


def test_every_entry_has_a_description_and_guidelines():
    for key, entry in ENTITY_GUIDELINES.items():
        assert entry.type == key
        assert entry.description.strip()
        assert len(entry.guidelines) > 100, key


def test_lookup_by_label_or_enum_member():
    assert guidelines_for("PER") is guidelines_for(EntityType.PER)
    with pytest.raises(KeyError, match="unknown entity type"):
        guidelines_for("NOT_A_TYPE")


def test_types_block_lists_key_and_description():
    block = entity_types_block()
    for entry in ENTITY_GUIDELINES.values():
        assert f"{entry.type} — {entry.description}" in block


def test_guidelines_block_embeds_every_type_and_its_rules():
    block = entity_guidelines_block()
    for entry in ENTITY_GUIDELINES.values():
        assert f"# {entry.type} — {entry.description}" in block
        assert entry.guidelines in block


def test_guidelines_block_can_be_narrowed_to_a_subset():
    block = entity_guidelines_block(["PER"])
    assert "# PER —" in block
    assert "# LOC —" not in block


def test_lines_are_joined_and_comments_ignored(tmp_path):
    path = tmp_path / "entities.json"
    path.write_text(json.dumps({
        "$comment": ["ignored"],
        "THING": {"description": "A thing.", "guidelines": ["first", "second"]},
    }), encoding="utf-8")
    loaded = load_entity_guidelines(path)
    assert list(loaded) == ["THING"]
    assert loaded["THING"].guidelines == "first\nsecond"


@pytest.mark.parametrize(
    "entry",
    [
        {"description": "no guidelines"},
        {"guidelines": "no description"},
        {"description": "bad type", "guidelines": 7},
        "not an object",
    ],
)
def test_malformed_entries_raise(tmp_path, entry):
    path = tmp_path / "entities.json"
    path.write_text(json.dumps({"THING": entry}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_entity_guidelines(path)


def test_empty_file_raises(tmp_path):
    path = tmp_path / "entities.json"
    path.write_text(json.dumps({"$comment": "nothing here"}), encoding="utf-8")
    with pytest.raises(ValueError, match="no entity types"):
        load_entity_guidelines(path)
