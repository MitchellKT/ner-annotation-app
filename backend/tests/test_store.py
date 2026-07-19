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


def test_entity_uid_round_trip(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "Alice met Bob.", "entities": [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}], "uid": "Q123"},
    ]}])
    store = Store(inp, out)
    assert store.get_doc("d1")["entities"][0]["uid"] == "Q123"

    # Save one entity with a uid and one without; only the former serializes it.
    store.save_doc("d1", [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}], "uid": "Q42"},
        {"type": "PER", "mentions": [{"start": 10, "end": 13}]},
    ], status="done")
    rec = json.loads(out.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["entities"][0]["uid"] == "Q42"
    assert "uid" not in rec["entities"][1]

    # Blank / whitespace uid is treated as unset.
    store.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 5}], "uid": "  "}],
                   status="done")
    rec = json.loads(out.read_text(encoding="utf-8").strip().splitlines()[0])
    assert "uid" not in rec["entities"][0]

    # Resume keeps the uid.
    store.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 5}], "uid": "Q42"}],
                   status="done")
    assert Store(inp, out).get_doc("d1")["entities"][0]["uid"] == "Q42"


def test_entity_tags_round_trip_and_normalize(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "Alice met Bob.", "entities": [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}], "tags": ["fictional", "lead"]},
    ]}])
    store = Store(inp, out)
    assert store.get_doc("d1")["entities"][0]["tags"] == ["fictional", "lead"]

    # Blank/whitespace tags are dropped, exact duplicates collapse, order kept,
    # case is preserved (so "NATO" and "nato" stay distinct), any script is ok.
    store.save_doc("d1", [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}],
         "tags": ["  לוחם  ", "", "NATO", "nato", "לוחם", "   "]},
        {"type": "PER", "mentions": [{"start": 10, "end": 13}]},  # untagged
    ], status="done")
    rec = json.loads(out.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["entities"][0]["tags"] == ["לוחם", "NATO", "nato"]
    # Untagged entities keep the original shape — no empty "tags" key.
    assert "tags" not in rec["entities"][1]

    # Resume keeps the tags.
    assert Store(inp, out).get_doc("d1")["entities"][0]["tags"] == ["לוחם", "NATO", "nato"]


def test_tag_bank_is_shared_across_users_and_persists(tmp_path):
    from ner_annotator.workspace import Workspace

    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "Alice met Bob.", "entities": [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}], "tags": ["from-input"]},
    ]}])
    ws = Workspace(inp, out)
    # Tags already present in the corpus seed the bank.
    assert ws.tags() == ["from-input"]

    # A tag one annotator applies becomes visible to the others.
    ws.get_user("Alice").save_doc(
        "d1",
        [{"type": "PER", "mentions": [{"start": 0, "end": 5}], "tags": ["by-alice"]}],
        status="done",
    )
    assert ws.tags() == ["by-alice", "from-input"]

    # Explicitly created tags survive even though no entity uses them.
    assert ws.add_tag("  unused-tag  ") == "unused-tag"
    with pytest.raises(ValueError):
        ws.add_tag("   ")

    # A restart reloads the bank, including Alice's tag (she hasn't logged in
    # yet, so her store is only created lazily — the bank is seeded from files).
    ws2 = Workspace(inp, out)
    assert ws2.tags() == ["by-alice", "from-input", "unused-tag"]


def test_discontinuous_mentions_round_trip(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    text = "Annie and George Washington visited."
    write_jsonl(inp, [{"doc_id": "d1", "text": text, "entities": [
        # "Annie … Washington" as one non-continuous mention.
        {"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]}]},
        {"type": "PER", "mentions": [{"start": 10, "end": 27}]},
    ]}])
    store = Store(inp, out)
    d1 = store.get_doc("d1")
    assert d1["entities"][0]["mentions"][0] == {
        "fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]
    }
    # Continuous mentions keep the plain {start,end} shape.
    assert d1["entities"][1]["mentions"][0] == {"start": 10, "end": 27}

    store.save_doc("d1", d1["entities"], status="done")
    rec = json.loads(out.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["entities"] == d1["entities"]
    # Resume parses the fragments form back.
    assert Store(inp, out).get_doc("d1")["entities"] == d1["entities"]


def test_fragments_are_sorted_merged_and_clamped(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "hello world", "entities": [
        # out of order + overlapping -> merged into one continuous fragment
        {"type": "PER", "mentions": [{"fragments": [[3, 5], [0, 4]]}]},
        # second fragment fully out of range -> dropped, mention becomes continuous
        {"type": "LOC", "mentions": [{"fragments": [{"start": 6, "end": 11}, {"start": 50, "end": 60}]}]},
    ]}])
    store = Store(inp, out)
    ents = store.get_doc("d1")["entities"]
    assert ents[0]["mentions"][0] == {"start": 0, "end": 5}
    assert ents[1]["mentions"][0] == {"start": 6, "end": 11}
    assert any("dropped out-of-range fragment" in w for w in store.warnings)


def test_metadata_groups_sources_by_type_with_counts(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [
        {"doc_id": "d1", "text": "a", "type": "news", "category": "print", "source": "cnn.com"},
        {"doc_id": "d2", "text": "b", "type": "news", "category": "print", "source": "cnn.com"},
        {"doc_id": "d3", "text": "c", "type": "news", "category": "wire", "source": "bbc.com"},
        {"doc_id": "d4", "text": "d", "type": "article", "category": "blog", "source": "medium.com"},
        {"doc_id": "d5", "text": "e"},  # no metadata -> unspecified/unspecified/unspecified
    ])
    md = Store(inp, out).metadata()
    assert md["sourcesByType"] == {
        "news": ["bbc.com", "cnn.com"],
        "article": ["medium.com"],
        "unspecified": ["unspecified"],
    }
    # Sources are grouped under their category, one level below the type.
    assert md["categoriesByType"] == {
        "news": {"print": ["cnn.com"], "wire": ["bbc.com"]},
        "article": {"blog": ["medium.com"]},
        "unspecified": {"unspecified": ["unspecified"]},
    }
    assert md["counts"]["news"] == {"cnn.com": 2, "bbc.com": 1}
    assert md["selection"] is None


def test_selection_filters_summaries_and_persists(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [
        {"doc_id": "d1", "text": "a", "type": "news", "source": "cnn.com"},
        {"doc_id": "d2", "text": "b", "type": "news", "source": "bbc.com"},
        {"doc_id": "d3", "text": "c", "type": "article", "source": "medium.com"},
    ])
    store = Store(inp, out)
    assert [s["doc_id"] for s in store.summaries()] == ["d1", "d2", "d3"]  # no selection = all

    # Selecting one source (plus an unknown pair that gets dropped) filters docs.
    saved = store.set_selection({"news": ["cnn.com", "nope.com"], "sports": ["x"]})
    assert saved == {"news": ["cnn.com"]}
    summ = store.summaries()
    assert [s["doc_id"] for s in summ] == ["d1"]
    assert summ[0]["type"] == "news" and summ[0]["source"] == "cnn.com"

    # A fresh Store reloads the persisted selection from the prefs sidecar.
    store2 = Store(inp, out)
    assert store2.selection == {"news": ["cnn.com"]}
    assert [s["doc_id"] for s in store2.summaries()] == ["d1"]


def test_get_doc_includes_metadata(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [
        {"doc_id": "d1", "text": "hi", "type": "News", "category": " Print ", "source": " CNN "}
    ])
    doc = Store(inp, out).get_doc("d1")
    assert doc["type"] == "News"
    assert doc["category"] == "Print"  # trimmed
    assert doc["source"] == "CNN"  # trimmed


def test_workspace_isolates_users_and_resumes(tmp_path):
    from ner_annotator.workspace import Workspace

    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [
        {"doc_id": "d1", "text": "Alice met Bob.", "type": "news", "source": "cnn.com"},
        {"doc_id": "d2", "text": "Another doc.", "type": "article", "source": "medium.com"},
    ])
    ws = Workspace(inp, out, types=["PER", "LOC"])
    assert ws.n_docs == 2
    assert ws.metadata()["sourcesByType"] == {"news": ["cnn.com"], "article": ["medium.com"]}

    alice = ws.get_user("Alice")
    bob = ws.get_user("Bob")
    assert alice is not bob
    # Same username resolves to the same store instance.
    assert ws.get_user("Alice") is alice

    alice.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}], status="done")
    bob.save_doc("d1", [{"type": "LOC", "mentions": [{"start": 10, "end": 13}]}], status="in_progress")

    # Per-user files exist and are distinct; users don't see each other's work.
    assert alice.get_doc("d1")["entities"] == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]
    assert bob.get_doc("d1")["entities"] == [{"type": "LOC", "mentions": [{"start": 10, "end": 13}]}]

    # A brand-new Workspace (app restart) resumes each user's annotations.
    ws2 = Workspace(inp, out, types=["PER", "LOC"])
    assert ws2.get_user("Alice").get_doc("d1")["status"] == "done"
    assert ws2.get_user("Bob").get_doc("d1")["status"] == "in_progress"
    assert "Alice" in ws2.known_users() and "Bob" in ws2.known_users()


def test_workspace_slug_collisions_stay_distinct(tmp_path):
    from ner_annotator.workspace import Workspace

    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "x"}])
    ws = Workspace(inp, out)
    # Two names that slugify to the same base must not share files.
    a = ws.get_user("Jane Doe")
    b = ws.get_user("jane/doe")
    assert a.output_path != b.output_path

    a.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 1}]}], status="done")
    assert b.get_doc("d1")["entities"] == []


def test_doc_sink_mirrors_saves_and_backfills(tmp_path):
    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [
        {"doc_id": "d1", "text": "Alice met Bob."},
        {"doc_id": "d2", "text": "Another doc."},
    ])
    batches = []
    store = Store(inp, out, doc_sink=batches.append)

    # Loading alone publishes nothing — only saves and an explicit sync do.
    assert batches == []

    store.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}], status="done")
    # A save mirrors just that doc, in the output schema plus its status.
    assert batches == [[{
        "doc_id": "d1",
        "text": "Alice met Bob.",
        "entities": [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}],
        "status": "done",
    }]]

    # The mirrored record matches the .jsonl line it accompanies.
    line = json.loads(out.read_text(encoding="utf-8").strip().splitlines()[0])
    assert {k: v for k, v in batches[0][0].items() if k != "status"} == line

    # sync_all backfills every doc, annotated or not.
    batches.clear()
    store.sync_all()
    assert [r["doc_id"] for r in batches[0]] == ["d1", "d2"]
    assert batches[0][1]["status"] == "unreviewed"


def test_workspace_mirrors_per_annotator(tmp_path):
    from ner_annotator.workspace import Workspace

    class FakeExporter:
        def __init__(self):
            self.calls = []

        def export(self, annotator, records):
            self.calls.append((annotator, [r["doc_id"] for r in records]))
            return True

    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "Alice met Bob."}])

    exporter = FakeExporter()
    ws = Workspace(inp, out, exporter=exporter)
    # The read-only corpus store is never mirrored; only user stores are.
    assert exporter.calls == []

    alice = ws.get_user("Alice")
    # Opening a user backfills their existing output.
    assert exporter.calls == [("Alice", ["d1"])]

    exporter.calls.clear()
    alice.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}], status="done")
    ws.get_user("Bob").save_doc("d1", [{"type": "LOC", "mentions": [{"start": 10, "end": 13}]}],
                                status="in_progress")
    # Each annotator's records are tagged with their own name.
    assert exporter.calls == [("Alice", ["d1"]), ("Bob", ["d1"]), ("Bob", ["d1"])]


def test_workspace_without_exporter_does_not_mirror(tmp_path):
    from ner_annotator.workspace import Workspace

    inp = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    write_jsonl(inp, [{"doc_id": "d1", "text": "x"}])
    ws = Workspace(inp, out)
    store = ws.get_user("Alice")
    assert store._doc_sink is None
    # Saving still works exactly as before.
    store.save_doc("d1", [{"type": "PER", "mentions": [{"start": 0, "end": 1}]}], status="done")
    assert json.loads(out.with_name(out.name + ".users").joinpath("Alice.jsonl").read_text(
        encoding="utf-8").strip())["entities"][0]["type"] == "PER"


def test_mention_rejects_bad_order():
    with pytest.raises(Exception):
        Mention.model_validate({"start": 5, "end": 5})
    with pytest.raises(Exception):
        Doc.model_validate({"doc_id": "d", "text": "x", "entities": [
            {"type": "PER", "mentions": [[3, 1]]},
        ]})
