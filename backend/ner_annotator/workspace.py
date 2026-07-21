"""Multi-user workspace: one shared corpus, per-annotator annotation state.

A :class:`~ner_annotator.store.Store` already owns everything one annotator
needs — the loaded documents, their annotations, per-doc status and the source
selection — persisted to a set of sidecar files derived from an output path.

The :class:`Workspace` layers multi-user support on top: every annotator gets
their own ``Store`` whose files live under a per-workspace ``.users`` directory,
keyed by a filesystem-safe *slug* of the username. Because each annotator's
files are independent, reopening the app as the same user resumes exactly that
user's annotations and selection.

Documents (text, predictions, metadata) are identical for everyone, so a single
read-only ``corpus`` store answers corpus-wide questions (entity types, load
warnings, the type→sources map for the selection screen) without needing a user.

Two things are deliberately *shared* between annotators rather than per-user:
entity :class:`TagBank` tags, so a tag any annotator creates or uses is offered
to all of them, and the document-level :class:`CommentBook`, so a note one
annotator leaves on a document is read by everyone working on it.

If a :class:`~ner_annotator.mongo.MongoExporter` is supplied, every user store
also mirrors its saves into MongoDB, tagged with that annotator's name.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

from .models import Comment
from .store import Store, comment_to_json

if TYPE_CHECKING:  # pragma: no cover - pymongo is an optional dependency
    from .mongo import MongoExporter

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")


class TagBank:
    """The shared vocabulary of entity tags, persisted as a small JSON sidecar.

    Tags are free-form strings in any script — only surrounding whitespace is
    trimmed, and comparison is exact, so "NATO"/"nato" are two different tags.
    The bank is the union of tags explicitly created through the UI and every
    tag already present in the corpus or in any annotator's output, so it
    survives a deleted sidecar and picks up tags from imported annotations.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._tags: set = set()
        self._load()

    @staticmethod
    def normalize(name: str) -> str:
        return str(name or "").strip()

    def tags(self) -> List[str]:
        with self._lock:
            return sorted(self._tags)

    def add(self, name: str) -> str:
        """Add one tag and return its normalized form (empty if it was blank)."""
        tag = self.normalize(name)
        if tag:
            self.add_many([tag])
        return tag

    def add_many(self, names: Iterable[str]) -> None:
        incoming = {t for t in (self.normalize(n) for n in names) if t}
        with self._lock:
            new = incoming - self._tags
            if not new:
                return  # nothing changed; don't rewrite the file
            self._tags |= new
            self._save()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a missing/corrupt bank starts empty
            return
        tags = data.get("tags", [])
        if isinstance(tags, list):
            self._tags = {t for t in (self.normalize(x) for x in tags) if t}

    def _save(self) -> None:
        Store._atomic_write(
            self.path,
            json.dumps({"tags": sorted(self._tags)}, ensure_ascii=False, indent=0),
        )


class CommentBook:
    """Document-level annotator comments, shared by everyone, in a JSON sidecar.

    Notes are keyed by ``doc_id`` and kept in the order they were written; each
    carries its author's username and an ISO-8601 UTC timestamp. Like the tag
    bank the book is append-only and self-healing: comments found in the corpus
    or in any annotator's output are merged back in, so a deleted sidecar loses
    nothing that the ``.jsonl`` files still carry.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._by_doc: Dict[str, List[dict]] = {}
        self._load()

    @staticmethod
    def _key(comment: dict) -> tuple:
        # Identity of a comment: nobody writes the same text twice in the same
        # second under the same name, so this is enough to merge duplicates.
        return (comment["author"], comment["created_at"], comment["text"])

    def for_doc(self, doc_id: str) -> List[dict]:
        with self._lock:
            return [dict(c) for c in self._by_doc.get(doc_id, ())]

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return {doc_id: len(cs) for doc_id, cs in self._by_doc.items()}

    def add(self, doc_id: str, author: str, text: str) -> dict:
        """Append one comment and return it in its stored form."""
        comment = comment_to_json(Comment(author=author, text=text))
        with self._lock:
            thread = self._by_doc.setdefault(doc_id, [])
            thread.append(comment)
            self._sort(thread)
            self._save()
        return dict(comment)

    def merge(self, incoming: Dict[str, List[dict]]) -> None:
        """Fold comments read from the ``.jsonl`` files in, ignoring duplicates."""
        with self._lock:
            changed = False
            for doc_id, comments in incoming.items():
                changed |= self._absorb(doc_id, comments)
            if changed:
                self._save()

    def _absorb(self, doc_id: str, comments: List[dict]) -> bool:
        """Add every comment not already in ``doc_id``'s thread. Caller saves."""
        thread = self._by_doc.setdefault(doc_id, [])
        known = {self._key(c) for c in thread}
        changed = False
        for raw in comments:
            try:
                comment = comment_to_json(Comment.model_validate(raw))
            except Exception:  # noqa: BLE001 - skip malformed comments
                continue
            if self._key(comment) in known:
                continue
            known.add(self._key(comment))
            thread.append(comment)
            changed = True
        if changed:
            self._sort(thread)
        return changed

    @staticmethod
    def _sort(thread: List[dict]) -> None:
        # Timestamps are ISO-8601 UTC, so lexicographic order is chronological.
        # Comments merged from several files thus interleave correctly.
        thread.sort(key=lambda c: c["created_at"])

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a missing/corrupt book starts empty
            return
        comments = data.get("comments", {})
        if not isinstance(comments, dict):
            return
        # Straight into the map (not via ``merge``) so opening the app doesn't
        # rewrite the file it just read.
        for doc_id, thread in comments.items():
            if isinstance(thread, list):
                self._absorb(str(doc_id), thread)

    def _save(self) -> None:
        Store._atomic_write(
            self.path,
            json.dumps(
                {"comments": {k: v for k, v in self._by_doc.items() if v}},
                ensure_ascii=False,
                indent=0,
            ),
        )


def slugify(username: str) -> str:
    """Filesystem-safe slug for a username (collisions resolved by the registry)."""
    slug = _SLUG_RE.sub("-", username.strip()).strip("-_")
    return slug[:64] or "user"


class Workspace:
    def __init__(
        self,
        input_path,
        output_path,
        types: Optional[List[str]] = None,
        exporter: Optional["MongoExporter"] = None,
    ) -> None:
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.types = list(types) if types else None
        # Optional mirror of every user's output; None disables MongoDB export.
        self.exporter = exporter
        # Per-user files live alongside the output, under "<output>.users/".
        self.users_root = self.output_path.with_name(self.output_path.name + ".users")
        self._registry_path = self.users_root / "users.json"

        self._lock = threading.RLock()
        self._users: Dict[str, Store] = {}
        # raw username -> slug, so the same user always maps to the same files.
        self._registry: Dict[str, str] = self._load_registry()
        # Shared across annotators; every store feeds the tags it sees into it.
        self.tag_bank = TagBank(self.users_root / "tags.json")
        # Likewise shared: one comment thread per document, read by every store.
        self.comment_book = CommentBook(self.users_root / "comments.json")

        # Read-only corpus view. It is never saved (``save_doc`` is never called),
        # so no file is written for this store — its output path is nominal.
        self.corpus = Store(
            self.input_path,
            self.users_root / "__corpus__.jsonl",
            types=types,
            tag_sink=self.tag_bank.add_many,
            comment_source=self.comment_book.for_doc,
            comment_sink=self.comment_book.merge,
        )
        # Tags and comments from annotators who haven't logged in yet this
        # session: their stores are created lazily, so seed from their outputs.
        self._seed_shared_state_from_user_files()

    # ------------------------------------------------------------ corpus-level
    @property
    def warnings(self) -> List[str]:
        return self.corpus.warnings

    @property
    def n_docs(self) -> int:
        return len(self.corpus.order)

    def config(self) -> dict:
        return {"types": list(self.corpus.types), "warnings": self.corpus.warnings}

    def metadata(self) -> dict:
        # Corpus-wide type→sources map (selection is filled in per user).
        md = self.corpus.metadata()
        md.pop("selection", None)
        return md

    # -------------------------------------------------------------------- tags
    def tags(self) -> List[str]:
        return self.tag_bank.tags()

    def add_tag(self, name: str) -> str:
        """Create a tag in the shared bank; returns its normalized form."""
        tag = self.tag_bank.add(name)
        if not tag:
            raise ValueError("tag must be non-empty")
        return tag

    # ---------------------------------------------------------------- comments
    def comments(self, doc_id: str) -> List[dict]:
        """One document's shared comment thread, oldest first."""
        self._require_doc(doc_id)
        return self.comment_book.for_doc(doc_id)

    def add_comment(self, doc_id: str, author: str, text: str) -> List[dict]:
        """Append a comment and return the whole thread."""
        self._require_doc(doc_id)
        if not str(author or "").strip():
            raise ValueError("comment author must be non-empty")
        if not str(text or "").strip():
            raise ValueError("comment text must be non-empty")
        self.comment_book.add(doc_id, author, text)
        # Every annotator's output embeds the shared thread, so bring the files
        # (and any mirror) of everyone signed in right now back into step.
        with self._lock:
            stores = list(self._users.values())
        for store in stores:
            store.resync(doc_id)
        return self.comment_book.for_doc(doc_id)

    def _require_doc(self, doc_id: str) -> None:
        if doc_id not in self.corpus.docs:
            raise KeyError(doc_id)

    def _seed_shared_state_from_user_files(self) -> None:
        """Harvest tags and comments from every annotator's output without
        loading a Store.

        User stores are created on demand, so without this the shared bank and
        comment book would only know about annotators who happen to log in
        during this session.
        """
        found_tags: set = set()
        found_comments: Dict[str, List[dict]] = {}
        for path in sorted(self.users_root.glob("*.jsonl")):
            if path.name.startswith("__"):
                continue
            try:
                with path.open(encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except Exception:  # noqa: BLE001 - skip unreadable lines
                            continue
                        for entity in record.get("entities", []) or []:
                            if isinstance(entity, dict):
                                tags = entity.get("tags")
                                if isinstance(tags, list):
                                    found_tags.update(str(t) for t in tags)
                        comments = record.get("comments")
                        doc_id = record.get("doc_id")
                        if isinstance(comments, list) and doc_id is not None:
                            found_comments.setdefault(str(doc_id), []).extend(
                                c for c in comments if isinstance(c, dict)
                            )
            except OSError:
                continue
        self.tag_bank.add_many(found_tags)
        self.comment_book.merge(found_comments)

    # -------------------------------------------------------------- user-level
    def get_user(self, username: str) -> Store:
        username = (username or "").strip()
        if not username:
            raise ValueError("username must be non-empty")
        with self._lock:
            existing = self._users.get(username)
            if existing is not None:
                return existing
            slug = self._resolve_slug(username)
            store = Store(
                self.input_path,
                self.users_root / f"{slug}.jsonl",
                state_path=self.users_root / f"{slug}.jsonl.state.json",
                prefs_path=self.users_root / f"{slug}.prefs.json",
                types=self.types,
                tag_sink=self.tag_bank.add_many,
                doc_sink=self._doc_sink_for(username),
                comment_source=self.comment_book.for_doc,
                comment_sink=self.comment_book.merge,
            )
            self._users[username] = store
            # Backfill: the store just resumed this user's existing .jsonl, which
            # may hold annotations made before the mirror existed.
            if self.exporter is not None:
                store.sync_all()
            return store

    def _doc_sink_for(self, username: str):
        """Bind the shared exporter to one annotator, or None when disabled."""
        if self.exporter is None:
            return None
        exporter = self.exporter
        return lambda records: exporter.export(username, records)

    def known_users(self) -> List[str]:
        with self._lock:
            return sorted(self._registry.keys())

    # --------------------------------------------------------------- registry
    def _resolve_slug(self, username: str) -> str:
        if username in self._registry:
            return self._registry[username]
        base = slugify(username)
        slug = base
        # Case-insensitively: on Windows (and macOS) "Jane-Doe.jsonl" and
        # "jane-doe.jsonl" are the *same* file, so two annotators whose slugs
        # differ only in case would silently share annotations.
        taken = {s.casefold() for s in self._registry.values()}
        i = 2
        while slug.casefold() in taken:
            slug = f"{base}-{i}"
            i += 1
        self._registry[username] = slug
        self._save_registry()
        return slug

    def _load_registry(self) -> Dict[str, str]:
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            users = data.get("users", {})
            if isinstance(users, dict):
                return {str(k): str(v) for k, v in users.items()}
        except Exception:  # noqa: BLE001 - a missing/corrupt registry starts empty
            pass
        return {}

    def _save_registry(self) -> None:
        Store._atomic_write(
            self._registry_path,
            json.dumps({"users": self._registry}, ensure_ascii=False, indent=0),
        )
