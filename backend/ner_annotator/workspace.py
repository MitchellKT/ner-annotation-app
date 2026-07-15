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
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .store import Store

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")


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
    ) -> None:
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.types = list(types) if types else None
        # Per-user files live alongside the output, under "<output>.users/".
        self.users_root = self.output_path.with_name(self.output_path.name + ".users")
        self._registry_path = self.users_root / "users.json"

        self._lock = threading.RLock()
        self._users: Dict[str, Store] = {}
        # raw username -> slug, so the same user always maps to the same files.
        self._registry: Dict[str, str] = self._load_registry()

        # Read-only corpus view. It is never saved (``save_doc`` is never called),
        # so no file is written for this store — its output path is nominal.
        self.corpus = Store(
            self.input_path,
            self.users_root / "__corpus__.jsonl",
            types=types,
        )

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
            )
            self._users[username] = store
            return store

    def known_users(self) -> List[str]:
        with self._lock:
            return sorted(self._registry.keys())

    # --------------------------------------------------------------- registry
    def _resolve_slug(self, username: str) -> str:
        if username in self._registry:
            return self._registry[username]
        base = slugify(username)
        slug = base
        taken = set(self._registry.values())
        i = 2
        while slug in taken:
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
