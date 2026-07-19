"""FastAPI application factory.

Exposes the annotation API under ``/api`` and (in production) serves the built
SPA from ``frontend/dist``. During development the Vite dev server runs
separately and proxies ``/api`` here.

The API is multi-user: annotation/selection endpoints are scoped to a username
(``/api/users/{username}/…``) so each annotator keeps their own state, while
``/api/config`` stays corpus-wide.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .store import Store
from .workspace import Workspace


class SaveRequest(BaseModel):
    entities: List[dict]
    status: str = "in_progress"


class SelectionRequest(BaseModel):
    # doc-type -> [selected sources]
    selection: Dict[str, List[str]] = {}


class TagRequest(BaseModel):
    name: str


def create_app(workspace: Workspace, static_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="NER Entity Annotator", version="0.2.0")

    # Dev convenience: Vite dev server on another port may call the API directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _user(username: str) -> Store:
        try:
            return workspace.get_user(username)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/config")
    def get_config() -> dict:
        return workspace.config()

    # The tag bank is shared by all annotators, so these are not user-scoped.
    @app.get("/api/tags")
    def get_tags() -> dict:
        return {"tags": workspace.tags()}

    @app.post("/api/tags")
    def add_tag(req: TagRequest) -> dict:
        try:
            tag = workspace.add_tag(req.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"tag": tag, "tags": workspace.tags()}

    @app.get("/api/users/{username}/meta")
    def get_meta(username: str) -> dict:
        store = _user(username)
        md = workspace.metadata()
        md["selection"] = store.selection
        return md

    @app.put("/api/users/{username}/selection")
    def set_selection(username: str, req: SelectionRequest) -> dict:
        store = _user(username)
        return {"selection": store.set_selection(req.selection)}

    @app.get("/api/users/{username}/docs")
    def list_docs(username: str) -> List[dict]:
        return _user(username).summaries()

    @app.get("/api/users/{username}/docs/{doc_id}")
    def get_doc(username: str, doc_id: str) -> dict:
        doc = _user(username).get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"unknown doc_id {doc_id!r}")
        return doc

    # PUT for normal saves; POST alias so navigator.sendBeacon (POST-only) works on unload.
    @app.put("/api/users/{username}/docs/{doc_id}")
    @app.post("/api/users/{username}/docs/{doc_id}")
    def save_doc(username: str, doc_id: str, req: SaveRequest) -> dict:
        try:
            return _user(username).save_doc(doc_id, req.entities, req.status)
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
