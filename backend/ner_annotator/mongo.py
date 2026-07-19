"""Optional MongoDB mirror of the annotation output.

The ``.jsonl`` files stay the source of truth: they are written exactly as
before, and this module only *mirrors* what was written so annotations are also
queryable from a database. It is opt-in — without ``--mongo-uri`` nothing here
is imported and ``pymongo`` need not be installed.

One document per (annotator, doc_id) pair, keyed by ``"<annotator>:<doc_id>"``
so repeated saves upsert in place rather than piling up revisions::

    {"_id": "Alice:d1", "annotator": "Alice", "doc_id": "d1",
     "text": "Alice met Bob.", "status": "done",
     "entities": [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}],
     "updated_at": datetime(...)}

``entities`` is the same JSON the ``.jsonl`` line carries, so a record here and
its output line always agree.

Writes are best-effort: a database that is down or misconfigured must never
cost an annotator their work, so failures are reported once and then swallowed.
"""

from __future__ import annotations

import datetime as _dt
import threading
from typing import Iterable, List, Optional

DEFAULT_DATABASE = "ner_annotator"
DEFAULT_COLLECTION = "annotations"

# How long to wait for the server before giving up on a call. Kept short: a save
# holds the store lock, so a hanging driver would stall the annotator's UI.
DEFAULT_TIMEOUT_MS = 5000


class MongoExporter:
    """Mirrors saved annotations into a MongoDB collection.

    Constructing this does *not* connect — pymongo dials lazily on the first
    operation — so an unreachable server surfaces as a warning on the first
    export instead of blocking startup.
    """

    def __init__(
        self,
        uri: str,
        database: str = DEFAULT_DATABASE,
        collection: str = DEFAULT_COLLECTION,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise RuntimeError(
                "MongoDB export needs pymongo: pip install 'ner-annotator[mongo]'"
            ) from exc

        self.uri = uri
        self.database = database
        self.collection_name = collection
        self._client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        self._collection = self._client[database][collection]
        self._lock = threading.Lock()
        # Set after the first failure so a persistently unreachable server logs
        # once instead of once per save.
        self._failed = False

    @staticmethod
    def _key(annotator: str, doc_id: str) -> str:
        return f"{annotator}:{doc_id}"

    def export(self, annotator: str, records: Iterable[dict]) -> bool:
        """Upsert one annotator's records. Returns False if the write failed."""
        from pymongo import UpdateOne

        now = _dt.datetime.now(_dt.timezone.utc)
        ops: List[UpdateOne] = [
            UpdateOne(
                {"_id": self._key(annotator, record["doc_id"])},
                {"$set": {**record, "annotator": annotator, "updated_at": now}},
                upsert=True,
            )
            for record in records
        ]
        if not ops:
            return True

        with self._lock:
            try:
                self._collection.bulk_write(ops, ordered=False)
            except Exception as exc:  # noqa: BLE001 - the .jsonl write already succeeded
                if not self._failed:
                    self._failed = True
                    print(
                        f"[ner_annotator] MongoDB export failed ({exc}); "
                        "annotations are still written to .jsonl. "
                        "Further export errors are suppressed."
                    )
                return False
            if self._failed:
                self._failed = False
                print("[ner_annotator] MongoDB export recovered")
            return True

    def ping(self) -> Optional[str]:
        """Check the connection at startup. Returns an error message, or None."""
        try:
            self._client.admin.command("ping")
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return None

    def close(self) -> None:
        self._client.close()
