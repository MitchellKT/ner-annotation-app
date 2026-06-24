import json

import pytest

from ner_annotator.models import Doc, Mention
from ner_annotator.store import Store


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def test_loads_predictions_and_tuple_mentions(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(
        inp,
        [
            {"doc_id": "d1", "text": "Alice met Bob.", "entities": [
                {"type": "PER", "mentions": [{"start": 0, "end": 5}]},
                {"type": "PER", "mentions": [[10, 13]]},  # tuple form
            ]},
            {"doc_id": "d2", "text": "no entities here"},
        ],
    )
    store = Store(inp, out)
    assert store.order == ["d1", "d2"]
    d1 = store.get_doc("d1")
    assert d1["entities"][0]["mentions"][0] == {"start": 0, "end": 5}
    assert d1["entities"][1]["mentions"][0] == {"start": 10, "end": 13}  # tuple parsed
    assert d1["prediction"] == d1["entities"]
    assert store.get_doc("d2")["entities"] == []


def test_sanitize_clamps_and_drops_and_dedupes(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "hello", "entities": [
        {"type": "PER", "mentions": [{"start": 0, "end": 99}, {"start": 0, "end": 99}]},  # clamp+dedupe
    ]}])
    store = Store(inp, out)
    ms = store.get_doc("d1")["entities"][0]["mentions"]
    assert ms == [{"start": 0, "end": 5}]  # clamped to len("hello"), deduped


def test_save_round_trip_and_prune_empty(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "Alice met Bob."}])
    store = Store(inp, out)
    summary = store.save_doc(
        "d1",
        [
            {"type": "PER", "mentions": [{"start": 0, "end": 5}]},
            {"type": "ORG", "mentions": []},  # pruned
        ],
        status="done",
    )
    assert summary["n_entities"] == 1
    assert summary["status"] == "done"

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[0])
    assert rec == {"doc_id": "d1", "text": "Alice met Bob.",
                   "entities": [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]}


def test_resume_from_output_and_state(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "Alice met Bob.", "entities": [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}]},
    ]}])
    store = Store(inp, out)
    store.save_doc("d1", [{"type": "LOC", "mentions": [{"start": 10, "end": 13}]}], status="done")

    # Re-open: annotation + status must resume, prediction snapshot is the original input.
    store2 = Store(inp, out)
    d1 = store2.get_doc("d1")
    assert d1["entities"] == [{"type": "LOC", "mentions": [{"start": 10, "end": 13}]}]
    assert d1["prediction"] == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]
    assert d1["status"] == "done"


def test_unicode_offsets_are_code_points(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    # "😀 Bob" -> code points: 😀=0, space=1, B=2,o=3,b=4
    write_jsonl(inp, [{"doc_id": "d1", "text": "😀 Bob", "entities": [
        {"type": "PER", "mentions": [{"start": 2, "end": 5}]},
    ]}])
    store = Store(inp, out)
    text = store.get_doc("d1")["text"]
    m = store.get_doc("d1")["entities"][0]["mentions"][0]
    assert text[m["start"]:m["end"]] == "Bob"


def test_bad_lines_recorded_as_warnings(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    inp.write_text('{"doc_id":"d1","text":"ok"}\nNOT JSON\n', encoding="utf-8")
    store = Store(inp, out)
    assert store.order == ["d1"]
    assert any("NOT JSON" in w or ":2:" in w for w in store.warnings)


def test_config_defaults_and_custom_types(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "hello"}])

    assert Store(inp, out).config()["types"] == ["PER", "LOC", "ORG", "TIME"]
    custom = Store(inp, out, types=["PER", "LOC", "ORG", "MISC", "EVENT"])
    assert custom.config()["types"] == ["PER", "LOC", "ORG", "MISC", "EVENT"]
    assert custom.types == ["PER", "LOC", "ORG", "MISC", "EVENT"]


def test_mention_rejects_bad_order():
    with pytest.raises(Exception):
        Mention.model_validate({"start": 5, "end": 5})
    with pytest.raises(Exception):
        Doc.model_validate({"doc_id": "d", "text": "x", "entities": [
            {"type": "PER", "mentions": [[3, 1]]},
        ]})
