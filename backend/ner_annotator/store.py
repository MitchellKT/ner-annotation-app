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
from typing import Dict, List, Optional

from .models import CANONICAL_TYPES, Doc, Entity, Mention

VALID_STATUSES = ("unreviewed", "in_progress", "done")


def _entity_to_json(entity: Entity) -> dict:
    return {
        "type": entity.type,
        "mentions": [{"start": m.start, "end": m.end} for m in entity.mentions],
    }


class Store:
    def __init__(
        self,
        input_path: os.PathLike | str,
        output_path: os.PathLike | str,
        state_path: Optional[os.PathLike | str] = None,
    ) -> None:
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else self.output_path.with_name(self.output_path.name + ".state.json")
        )
        self._lock = threading.RLock()

        self.order: List[str] = []
        self.index: Dict[str, int] = {}
        # doc_id -> {"text", "prediction": [Entity], "entities": [Entity]}
        self.docs: Dict[str, dict] = {}
        self.status: Dict[str, str] = {}
        self.warnings: List[str] = []

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
                    "prediction": pred,
                    "entities": [e.model_copy(deep=True) for e in pred],
                }
                self.status[doc.doc_id] = "unreviewed"

        self._merge_output()
        self._load_state()

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

    def _sanitize(self, entities: List[Entity], text: str, where: str) -> List[Entity]:
        """Clamp offsets to text bounds, drop invalid/empty, preserve order."""
        n = len(text)  # code points, matching the frontend's Array.from() length
        cleaned: List[Entity] = []
        for entity in entities:
            mentions: List[Mention] = []
            seen = set()
            for m in entity.mentions:
                start = max(0, min(m.start, n))
                end = max(0, min(m.end, n))
                if end <= start:
                    self.warnings.append(f"{where}: dropped out-of-range mention [{m.start},{m.end}]")
                    continue
                key = (start, end)
                if key in seen:
                    continue
                seen.add(key)
                mentions.append(Mention(start=start, end=end))
            if mentions:
                cleaned.append(Entity(type=entity.type, mentions=mentions))
        return cleaned

    # ------------------------------------------------------------------- read
    def config(self) -> dict:
        return {"types": list(CANONICAL_TYPES)}

    def summaries(self) -> List[dict]:
        with self._lock:
            return [self._summary(doc_id) for doc_id in self.order]

    def _summary(self, doc_id: str) -> dict:
        d = self.docs[doc_id]
        return {
            "doc_id": doc_id,
            "index": self.index[doc_id],
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
