"""FastAPI application factory.

Exposes the annotation API under ``/api`` and (in production) serves the built
SPA from ``frontend/dist``. During development the Vite dev server runs
separately and proxies ``/api`` here.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .store import Store


class EntityIn(BaseModel):
    type: str
    mentions: List[dict]


class SaveRequest(BaseModel):
    entities: List[dict]
    status: str = "in_progress"


def create_app(store: Store, static_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="NER Entity Annotator", version="0.1.0")

    # Dev convenience: Vite dev server on another port may call the API directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/config")
    def get_config() -> dict:
        return {**store.config(), "warnings": store.warnings}

    @app.get("/api/docs")
    def list_docs() -> List[dict]:
        return store.summaries()

    @app.get("/api/docs/{doc_id}")
    def get_doc(doc_id: str) -> dict:
        doc = store.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"unknown doc_id {doc_id!r}")
        return doc

    # PUT for normal saves; POST alias so navigator.sendBeacon (POST-only) works on unload.
    @app.put("/api/docs/{doc_id}")
    @app.post("/api/docs/{doc_id}")
    def save_doc(doc_id: str, req: SaveRequest) -> dict:
        try:
            return store.save_doc(doc_id, req.entities, req.status)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown doc_id {doc_id!r}")

    if static_dir is not None and static_dir.exists():
        # Serve hashed assets, then fall back to index.html for the SPA.
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> FileResponse:
            candidate = static_dir / path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app
