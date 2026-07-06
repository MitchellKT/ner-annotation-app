"""Per-user annotation workspaces on a shared data volume.

Each annotator ("user", identified by a slug) owns a directory::

    <data_dir>/users/<slug>/
        meta.json                  # types, original filename, counts, timestamps
        input.jsonl                # the file the user uploaded
        output.jsonl               # written continuously; downloadable
        output.jsonl.state.json    # per-doc review status sidecar
        archive/<timestamp>/       # previous input/output when the file is replaced

The existing :class:`Store` is reused unchanged as the per-workspace unit: it
already has its own lock and atomic writes, and different users touch disjoint
files, so cross-user concurrency is trivially safe. The manager keeps a bounded
LRU cache of live ``Store`` objects and reconstructs them from disk on demand,
so a pod restart transparently resumes every user where they left off.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import Doc
from .store import Store

# Reject uploads larger than this (defence against filling the volume / OOM).
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# Cap live in-memory stores; evicted users are lazily reloaded from disk.
DEFAULT_MAX_LIVE_STORES = 64


class WorkspaceError(ValueError):
    """A user-facing problem with an upload (bad JSONL, empty, too large)."""


def validate_jsonl(text: str) -> Tuple[int, List[str]]:
    """Count valid docs and collect per-line warnings without side effects."""
    n_docs = 0
    warnings: List[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            doc = Doc.model_validate(json.loads(line))
        except Exception as exc:  # noqa: BLE001 - collect and report bad lines
            warnings.append(f"line {lineno}: {exc}")
            continue
        if doc.doc_id in seen:
            warnings.append(f"line {lineno}: duplicate doc_id {doc.doc_id!r} (kept first)")
            continue
        seen.add(doc.doc_id)
        n_docs += 1
    return n_docs, warnings


class WorkspaceManager:
    def __init__(
        self,
        data_dir: os.PathLike | str,
        *,
        default_types: List[str],
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        max_live_stores: int = DEFAULT_MAX_LIVE_STORES,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.users_dir = self.data_dir / "users"
        self.default_types = list(default_types)
        self.max_upload_bytes = max_upload_bytes
        self.max_live_stores = max_live_stores

        self.users_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # slug -> Store, ordered by recency of use (LRU eviction from the front).
        self._live: "OrderedDict[str, Store]" = OrderedDict()

    # ----------------------------------------------------------- paths / meta
    def _user_dir(self, slug: str) -> Path:
        return self.users_dir / slug

    def _input_path(self, slug: str) -> Path:
        return self._user_dir(slug) / "input.jsonl"

    def _output_path(self, slug: str) -> Path:
        return self._user_dir(slug) / "output.jsonl"

    def _meta_path(self, slug: str) -> Path:
        return self._user_dir(slug) / "meta.json"

    def has_workspace(self, slug: str) -> bool:
        return self._input_path(slug).exists()

    def workspace_info(self, slug: str) -> Optional[dict]:
        """Metadata for the user's current file, or ``None`` if none uploaded."""
        if not self.has_workspace(slug):
            return None
        meta = self._read_meta(slug)
        store = self.get_store(slug)
        summaries = store.summaries() if store else []
        done = sum(1 for s in summaries if s["status"] == "done")
        return {
            "filename": meta.get("filename"),
            "types": meta.get("types", self.default_types),
            "uploaded_at": meta.get("uploaded_at"),
            "n_docs": len(summaries),
            "n_done": done,
            "warnings": store.warnings if store else [],
        }

    def _read_meta(self, slug: str) -> dict:
        try:
            return json.loads(self._meta_path(slug).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    # -------------------------------------------------------------- live store
    def get_store(self, slug: str) -> Optional[Store]:
        """Return the user's live ``Store``, loading it from disk on demand.

        ``None`` when the user has not uploaded a file yet.
        """
        with self._lock:
            store = self._live.get(slug)
            if store is not None:
                self._live.move_to_end(slug)
                return store
            if not self.has_workspace(slug):
                return None
            meta = self._read_meta(slug)
            types = meta.get("types") or self.default_types
            store = Store(self._input_path(slug), self._output_path(slug), types=types)
            self._live[slug] = store
            self._evict_if_needed()
            return store

    def _evict_if_needed(self) -> None:
        # Called under _lock. Drop least-recently-used stores beyond the cap;
        # their state is already flushed to disk and reloads lazily.
        while len(self._live) > self.max_live_stores:
            self._live.popitem(last=False)

    # ------------------------------------------------------------- create file
    def create_workspace(
        self,
        slug: str,
        *,
        raw: bytes,
        filename: str,
        types: Optional[List[str]] = None,
    ) -> dict:
        """Validate and install an uploaded file as the user's active workspace.

        Any existing workspace is archived (not deleted) first. Raises
        :class:`WorkspaceError` for oversize / undecodable / empty input,
        leaving a prior workspace untouched.
        """
        if len(raw) > self.max_upload_bytes:
            raise WorkspaceError(
                f"file is {len(raw) // 1024} KB; limit is {self.max_upload_bytes // 1024} KB"
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError(f"file is not valid UTF-8: {exc}") from exc

        n_docs, warnings = validate_jsonl(text)
        if n_docs == 0:
            detail = warnings[0] if warnings else "no records found"
            raise WorkspaceError(f"no valid documents in file ({detail})")

        use_types = [t.strip() for t in (types or self.default_types) if t.strip()]
        if not use_types:
            use_types = list(self.default_types)

        with self._lock:
            user_dir = self._user_dir(slug)
            user_dir.mkdir(parents=True, exist_ok=True)
            # Drop any cached store and archive existing files before overwrite.
            self._live.pop(slug, None)
            self._archive_existing(slug)

            self._input_path(slug).write_text(text, encoding="utf-8")
            meta = {
                "filename": filename,
                "types": use_types,
                "uploaded_at": time.time(),
                "n_docs": n_docs,
            }
            self._meta_path(slug).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # Build the store now so the first load is warm and warnings surface.
            store = Store(self._input_path(slug), self._output_path(slug), types=use_types)
            self._live[slug] = store
            self._evict_if_needed()

        info = self.workspace_info(slug) or {}
        info["warnings"] = list(dict.fromkeys(warnings + store.warnings))
        return info

    def _archive_existing(self, slug: str) -> None:
        # Called under _lock. Move current input/output/state into a timestamped
        # archive dir so replacing a file never loses prior annotations.
        existing = [
            self._input_path(slug),
            self._output_path(slug),
            self._output_path(slug).with_name("output.jsonl.state.json"),
        ]
        if not any(p.exists() for p in existing):
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = self._user_dir(slug) / "archive" / stamp
        dest.mkdir(parents=True, exist_ok=True)
        for p in existing:
            if p.exists():
                os.replace(p, dest / p.name)

    # --------------------------------------------------------------- download
    def output_path(self, slug: str) -> Optional[Path]:
        """Path to the user's output file (ensuring it is flushed), or ``None``."""
        store = self.get_store(slug)
        if store is None:
            return None
        out = self._output_path(slug)
        # Force a flush so a mid-session download reflects the latest edits even
        # if the debounced autosave hasn't fired.
        with store._lock:  # noqa: SLF001 - deliberate: ensure on-disk output is current
            store._flush()  # noqa: SLF001
        return out if out.exists() else None
