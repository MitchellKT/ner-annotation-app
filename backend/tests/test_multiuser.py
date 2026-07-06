"""Multi-user server: sessions, uploads, per-user isolation, resume-after-restart."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from ner_annotator import session as session_mod
from ner_annotator.main import create_app
from ner_annotator.workspace import WorkspaceManager, WorkspaceError, validate_jsonl


def jsonl_bytes(records) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8")


SAMPLE = [
    {"doc_id": "d1", "text": "Alice met Bob.", "entities": [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}]},
    ]},
    {"doc_id": "d2", "text": "Nothing here."},
]


@pytest.fixture
def manager(tmp_path):
    return WorkspaceManager(tmp_path, default_types=["PER", "LOC"])


@pytest.fixture
def client(manager, monkeypatch):
    # Stable secret so signed cookies verify within the test process.
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    app = create_app(manager, static_dir=None)
    return TestClient(app)


# --------------------------------------------------------------- slug / cookie
def test_slugify_normalizes_names():
    assert session_mod.slugify("Mitchell Keren") == "mitchell-keren"
    assert session_mod.slugify("  Álvaro!! ") == "alvaro"
    assert session_mod.slugify("***") == ""


def test_validate_jsonl_counts_and_warns():
    text = jsonl_bytes(SAMPLE).decode() + "not json\n"
    n, warnings = validate_jsonl(text)
    assert n == 2
    assert any("line 3" in w for w in warnings)


# ------------------------------------------------------------------- sessions
def test_whoami_requires_session(client):
    assert client.get("/api/session").status_code == 401


def test_identify_sets_cookie_and_whoami(client):
    r = client.post("/api/session", json={"name": "Dr. Smith"})
    assert r.status_code == 200
    assert r.json()["slug"] == "dr-smith"
    assert r.json()["has_workspace"] is False
    who = client.get("/api/session")
    assert who.status_code == 200
    assert who.json()["name"] == "Dr. Smith"


def test_identify_rejects_empty_name(client):
    assert client.post("/api/session", json={"name": "  !! "}).status_code == 400


def test_sign_out_clears_session(client):
    client.post("/api/session", json={"name": "Ann"})
    client.delete("/api/session")
    assert client.get("/api/session").status_code == 401


def test_annotation_routes_need_session(client):
    assert client.get("/api/docs").status_code == 401
    assert client.get("/api/config").status_code == 401


def test_identified_without_upload_gets_409(client):
    client.post("/api/session", json={"name": "Ann"})
    assert client.get("/api/docs").status_code == 409
    assert client.get("/api/config").status_code == 409


# -------------------------------------------------------------------- uploads
def test_upload_then_annotate(client):
    client.post("/api/session", json={"name": "Ann"})
    r = client.post(
        "/api/workspace",
        files={"file": ("mine.jsonl", jsonl_bytes(SAMPLE), "application/x-ndjson")},
        data={"types": "PER,LOC,ORG"},
    )
    assert r.status_code == 200
    assert r.json()["n_docs"] == 2
    assert r.json()["types"] == ["PER", "LOC", "ORG"]

    assert client.get("/api/config").json()["types"] == ["PER", "LOC", "ORG"]
    docs = client.get("/api/docs").json()
    assert [d["doc_id"] for d in docs] == ["d1", "d2"]

    # Save an annotation and read it back.
    save = client.put(
        "/api/docs/d1",
        json={"entities": [{"type": "LOC", "mentions": [{"start": 0, "end": 5}]}], "status": "done"},
    )
    assert save.status_code == 200
    assert save.json()["status"] == "done"


def test_upload_rejects_empty_and_bad(client):
    client.post("/api/session", json={"name": "Ann"})
    r = client.post(
        "/api/workspace",
        files={"file": ("bad.jsonl", b"this is not json\n", "application/x-ndjson")},
    )
    assert r.status_code == 422
    assert "no valid documents" in r.json()["detail"]


def test_download_output_reflects_saves(client):
    client.post("/api/session", json={"name": "Ann"})
    client.post(
        "/api/workspace",
        files={"file": ("mine.jsonl", jsonl_bytes(SAMPLE), "application/x-ndjson")},
    )
    client.put(
        "/api/docs/d1",
        json={"entities": [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}], "status": "done"},
    )
    r = client.get("/api/workspace/output")
    assert r.status_code == 200
    lines = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert {rec["doc_id"] for rec in lines} == {"d1", "d2"}


# ----------------------------------------------------------------- isolation
def test_users_are_isolated(manager, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    app = create_app(manager, static_dir=None)
    ann = TestClient(app)
    bob = TestClient(app)

    ann.post("/api/session", json={"name": "Ann"})
    ann.post("/api/workspace", files={"file": ("a.jsonl", jsonl_bytes(SAMPLE), "application/x-ndjson")})

    bob.post("/api/session", json={"name": "Bob"})
    other = [{"doc_id": "z9", "text": "Bob's private doc."}]
    bob.post("/api/workspace", files={"file": ("b.jsonl", jsonl_bytes(other), "application/x-ndjson")})

    ann_docs = {d["doc_id"] for d in ann.get("/api/docs").json()}
    bob_docs = {d["doc_id"] for d in bob.get("/api/docs").json()}
    assert ann_docs == {"d1", "d2"}
    assert bob_docs == {"z9"}
    # Ann cannot fetch Bob's doc.
    assert ann.get("/api/docs/z9").status_code == 404


def test_replace_file_archives_old(client, manager):
    client.post("/api/session", json={"name": "Ann"})
    client.post("/api/workspace", files={"file": ("v1.jsonl", jsonl_bytes(SAMPLE), "application/x-ndjson")})
    new = [{"doc_id": "n1", "text": "New file."}]
    client.post("/api/workspace", files={"file": ("v2.jsonl", jsonl_bytes(new), "application/x-ndjson")})

    docs = {d["doc_id"] for d in client.get("/api/docs").json()}
    assert docs == {"n1"}
    archive = manager.users_dir / "ann" / "archive"
    assert archive.exists() and any(archive.iterdir())


def test_resume_after_restart(manager, tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    app = create_app(manager, static_dir=None)
    c = TestClient(app)
    c.post("/api/session", json={"name": "Ann"})
    c.post("/api/workspace", files={"file": ("m.jsonl", jsonl_bytes(SAMPLE), "application/x-ndjson")})
    c.put("/api/docs/d1", json={"entities": [], "status": "done"})

    # Simulate a pod restart: brand-new manager/app over the same data dir.
    manager2 = WorkspaceManager(tmp_path, default_types=["PER", "LOC"])
    app2 = create_app(manager2, static_dir=None)
    c2 = TestClient(app2)
    # Cookie is signed with the same secret, so the session carries over.
    c2.cookies = c.cookies
    who = c2.get("/api/session")
    assert who.status_code == 200 and who.json()["has_workspace"] is True
    d1 = next(d for d in c2.get("/api/docs").json() if d["doc_id"] == "d1")
    assert d1["status"] == "done"
