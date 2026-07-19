"""In-memory document store with resumable, atomic JSONL persistence.

Lifecycle:

* On start, ``input.jsonl`` is loaded in order. Each doc's ``entities`` become its
  *prediction snapshot* (kept immutable for "revert to prediction" / diffing) and
  also seed the *current* annotation.
* If ``output.jsonl`` already exists, it is merged back in so a previous session
  resumes where it left off.
* Per-doc review *status* lives in a sidecar ``<output>.state.json`` so the output
  file stays exactly on-schema.
* Saves overwrite the current annotation and rewrite ``output.jsonl`` atomically
  (temp file + ``os.replace``). Offsets are sanitised against the text length and
  empty entities are pruned.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set

from .models import CANONICAL_TYPES, Doc, Entity, Fragment, Mention, merge_fragments

VALID_STATUSES = ("unreviewed", "in_progress", "done")

# Fallback bucket for docs whose input omits ``type`` / ``source``.
UNSPECIFIED = "unspecified"


def _mention_to_json(mention: Mention) -> dict:
    # Single-fragment (continuous) mentions keep the original {"start","end"}
    # shape; only non-continuous mentions use the {"fragments": [...]} form.
    if len(mention.fragments) == 1:
        f = mention.fragments[0]
        return {"start": f.start, "end": f.end}
    return {"fragments": [{"start": f.start, "end": f.end} for f in mention.fragments]}


def _entity_to_json(entity: Entity) -> dict:
    out = {
        "type": entity.type,
        "mentions": [_mention_to_json(m) for m in entity.mentions],
    }
    if entity.uid is not None:
        out["uid"] = entity.uid
    # Like ``uid``: only written when set, so untagged entities keep the
    # original on-disk shape.
    if entity.tags:
        out["tags"] = list(entity.tags)
    return out


class Store:
    def __init__(
        self,
        input_path: os.PathLike | str,
        output_path: os.PathLike | str,
        state_path: Optional[os.PathLike | str] = None,
        types: Optional[List[str]] = None,
        prefs_path: Optional[os.PathLike | str] = None,
        tag_sink: Optional[Callable[[Iterable[str]], None]] = None,
    ) -> None:
        # Called with every tag this store sees (at load, and on each save) so a
        # workspace-wide bank can grow from tags already present in the files.
        self._tag_sink = tag_sink
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else self.output_path.with_name(self.output_path.name + ".state.json")
        )
        # Per-user preferences (currently the source selection). Kept in a
        # separate sidecar so the annotation output stays exactly on-schema.
        self.prefs_path = (
            Path(prefs_path)
            if prefs_path is not None
            else self.output_path.with_name(self.output_path.name + ".prefs.json")
        )
        # Entity types offered in the UI (digit keys 1-9 map to the first nine).
        self.types: List[str] = list(types) if types else list(CANONICAL_TYPES)
        self._lock = threading.RLock()

        self.order: List[str] = []
        self.index: Dict[str, int] = {}
        # doc_id -> {"text", "type", "source", "prediction": [Entity], "entities": [Entity]}
        self.docs: Dict[str, dict] = {}
        self.status: Dict[str, str] = {}
        self.warnings: List[str] = []
        # doc-type -> [selected sources]; None means "no selection saved yet"
        # (unfiltered — every document is shown).
        self.selection: Optional[Dict[str, List[str]]] = None

        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        if not self.input_path.exists():
            raise FileNotFoundError(f"input file not found: {self.input_path}")

        with self.input_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = Doc.model_validate(json.loads(line))
                except Exception as exc:  # noqa: BLE001 - report and skip bad lines
                    self.warnings.append(f"{self.input_path.name}:{lineno}: {exc}")
                    continue
                if doc.doc_id in self.docs:
                    self.warnings.append(
                        f"{self.input_path.name}:{lineno}: duplicate doc_id {doc.doc_id!r} (kept first)"
                    )
                    continue
                pred = self._sanitize(doc.entities, doc.text, where=f"input {doc.doc_id}")
                self.index[doc.doc_id] = len(self.order)
                self.order.append(doc.doc_id)
                self.docs[doc.doc_id] = {
                    "text": doc.text,
                    "type": doc.type or UNSPECIFIED,
                    "source": doc.source or UNSPECIFIED,
                    "prediction": pred,
                    "entities": [e.model_copy(deep=True) for e in pred],
                }
                self.status[doc.doc_id] = "unreviewed"

        self._merge_output()
        self._load_state()
        self._load_prefs()
        self._publish_tags()

    def _merge_output(self) -> None:
        if not self.output_path.exists():
            return
        with self.output_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = Doc.model_validate(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
                if doc.doc_id in self.docs:
                    text = self.docs[doc.doc_id]["text"]
                    self.docs[doc.doc_id]["entities"] = self._sanitize(
                        doc.entities, text, where=f"output {doc.doc_id}"
                    )

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        for doc_id, st in data.get("status", {}).items():
            if doc_id in self.status and st in VALID_STATUSES:
                self.status[doc_id] = st

    def _load_prefs(self) -> None:
        if not self.prefs_path.exists():
            return
        try:
            data = json.loads(self.prefs_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        sel = data.get("selection")
        if isinstance(sel, dict):
            self.selection = self._sanitize_selection(sel)

    def _sanitize_selection(self, selection: dict) -> Dict[str, List[str]]:
        """Keep only (type, source) pairs that exist in the loaded corpus."""
        available = self._sources_by_type()
        cleaned: Dict[str, List[str]] = {}
        for doc_type, sources in selection.items():
            if doc_type not in available or not isinstance(sources, (list, tuple)):
                continue
            allowed = available[doc_type]
            picked = [s for s in sources if s in allowed]
            if picked:
                cleaned[doc_type] = picked
        return cleaned

    def _sources_by_type(self) -> Dict[str, set]:
        by_type: Dict[str, set] = {}
        for doc_id in self.order:
            d = self.docs[doc_id]
            by_type.setdefault(d["type"], set()).add(d["source"])
        return by_type

    def _sanitize(self, entities: List[Entity], text: str, where: str) -> List[Entity]:
        """Clamp offsets to text bounds, drop invalid/empty, preserve order."""
        n = len(text)  # code points, matching the frontend's Array.from() length
        cleaned: List[Entity] = []
        for entity in entities:
            mentions: List[Mention] = []
            seen = set()
            for m in entity.mentions:
                fragments: List[Fragment] = []
                for f in m.fragments:
                    start = max(0, min(f.start, n))
                    end = max(0, min(f.end, n))
                    if end <= start:
                        self.warnings.append(
                            f"{where}: dropped out-of-range fragment [{f.start},{f.end}]"
                        )
                        continue
                    fragments.append(Fragment(start=start, end=end))
                if not fragments:
                    continue
                fragments = merge_fragments(fragments)
                key = tuple((f.start, f.end) for f in fragments)
                if key in seen:
                    continue
                seen.add(key)
                mentions.append(Mention(fragments=fragments))
            if mentions:
                cleaned.append(
                    Entity(
                        type=entity.type,
                        mentions=mentions,
                        uid=entity.uid,
                        tags=list(entity.tags),
                    )
                )
        return cleaned

    def used_tags(self) -> Set[str]:
        """Every tag appearing on a current annotation or an input prediction."""
        tags: Set[str] = set()
        for d in self.docs.values():
            for key in ("entities", "prediction"):
                for entity in d[key]:
                    tags.update(entity.tags)
        return tags

    def _publish_tags(self) -> None:
        if self._tag_sink is not None:
            self._tag_sink(self.used_tags())

    # ------------------------------------------------------------------- read
    def config(self) -> dict:
        return {"types": list(self.types)}

    def metadata(self) -> dict:
        """Document metadata for the source-selection screen: the sources
        available under each doc ``type`` (sorted) plus per-(type, source)
        document counts, and this user's saved ``selection`` (if any)."""
        with self._lock:
            counts: Dict[str, Dict[str, int]] = {}
            for doc_id in self.order:
                d = self.docs[doc_id]
                counts.setdefault(d["type"], {})
                counts[d["type"]][d["source"]] = counts[d["type"]].get(d["source"], 0) + 1
            sources_by_type = {t: sorted(srcs) for t, srcs in counts.items()}
            return {
                "sourcesByType": sources_by_type,
                "counts": counts,
                "selection": self.selection,
            }

    def set_selection(self, selection: dict) -> Dict[str, List[str]]:
        with self._lock:
            self.selection = self._sanitize_selection(selection or {})
            self._flush_prefs()
            return self.selection

    def _is_selected(self, doc_id: str) -> bool:
        if self.selection is None:
            return True
        d = self.docs[doc_id]
        return d["source"] in self.selection.get(d["type"], [])

    def summaries(self) -> List[dict]:
        with self._lock:
            return [self._summary(doc_id) for doc_id in self.order if self._is_selected(doc_id)]

    def _summary(self, doc_id: str) -> dict:
        d = self.docs[doc_id]
        return {
            "doc_id": doc_id,
            "index": self.index[doc_id],
            "type": d["type"],
            "source": d["source"],
            "status": self.status[doc_id],
            "n_entities": len(d["entities"]),
            "n_mentions": sum(len(e.mentions) for e in d["entities"]),
            "has_prediction": len(d["prediction"]) > 0,
        }

    def get_doc(self, doc_id: str) -> Optional[dict]:
        with self._lock:
            d = self.docs.get(doc_id)
            if d is None:
                return None
            return {
                "doc_id": doc_id,
                "index": self.index[doc_id],
                "type": d["type"],
                "source": d["source"],
                "text": d["text"],
                "status": self.status[doc_id],
                "entities": [_entity_to_json(e) for e in d["entities"]],
                "prediction": [_entity_to_json(e) for e in d["prediction"]],
            }

    # ------------------------------------------------------------------ write
    def save_doc(self, doc_id: str, entities_json: List[dict], status: str) -> dict:
        with self._lock:
            d = self.docs.get(doc_id)
            if d is None:
                raise KeyError(doc_id)
            parsed = [Entity.model_validate(e) for e in entities_json]
            d["entities"] = self._sanitize(parsed, d["text"], where=f"save {doc_id}")
            if status in VALID_STATUSES:
                self.status[doc_id] = status
            self._flush()
            # Tags applied here join the shared bank, so a tag one annotator
            # uses becomes suggestible to the others.
            if self._tag_sink is not None:
                self._tag_sink({t for e in d["entities"] for t in e.tags})
            return self._summary(doc_id)

    def _flush(self) -> None:
        self._atomic_write(
            self.output_path,
            "".join(
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "text": self.docs[doc_id]["text"],
                        "entities": [_entity_to_json(e) for e in self.docs[doc_id]["entities"]],
                    },
                    ensure_ascii=False,
                )
                + "\n"
                for doc_id in self.order
            ),
        )
        self._atomic_write(
            self.state_path,
            json.dumps({"status": self.status}, ensure_ascii=False, indent=0),
        )

    def _flush_prefs(self) -> None:
        self._atomic_write(
            self.prefs_path,
            json.dumps({"selection": self.selection}, ensure_ascii=False, indent=0),
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
