import pytest

from ner_annotator_llm.guidelines import (
    ENTITIES_DIR,
    ENTITY_GUIDELINES,
    GENERAL_GUIDELINES,
    EntityType,
    entity_guidelines_block,
    guidelines_for,
    load_entity_guidelines,
)


def test_general_guidelines_are_loaded():
    assert "## Part 1 — the entity list" in GENERAL_GUIDELINES


def test_the_type_set_is_the_set_of_files():
    on_disk = sorted(path.stem for path in ENTITIES_DIR.glob("*.md"))
    assert list(ENTITY_GUIDELINES) == on_disk
    assert [m.value for m in EntityType] == on_disk
    assert EntityType("PER").value == "PER"


def test_every_file_gives_a_description_and_rules():
    for key, entry in ENTITY_GUIDELINES.items():
        assert entry.type == key
        assert entry.description.strip()
        assert entry.guidelines.startswith(f"# {key} —")
        assert len(entry.guidelines) > 100, key


def test_lookup_by_label_or_enum_member():
    assert guidelines_for("PER") is guidelines_for(EntityType.PER)
    with pytest.raises(KeyError):
        guidelines_for("NOT_A_TYPE")


def test_the_block_indexes_every_type_then_gives_its_file():
    block = entity_guidelines_block()
    for entry in ENTITY_GUIDELINES.values():
        assert f"{entry.type} — {entry.description}" in block
        assert entry.guidelines in block


def test_the_block_can_be_narrowed_to_a_subset():
    block = entity_guidelines_block(["PER"])
    assert "# PER —" in block
    assert "# LOC —" not in block


def test_a_new_file_becomes_a_new_type(tmp_path):
    (tmp_path / "THING.md").write_text("# THING — A thing.\n\n- Some rules.\n", encoding="utf-8")
    loaded = load_entity_guidelines(tmp_path)
    assert list(loaded) == ["THING"]
    assert loaded["THING"].description == "A thing."
    assert "Some rules." in loaded["THING"].guidelines
