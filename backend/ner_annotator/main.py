"""FastAPI application factory (multi-user).

Annotators identify themselves by name (a signed cookie session), upload the
``.jsonl`` file they want to annotate, and then use the annotation API — which
is identical in shape to the single-user version but scoped to *their* uploaded
workspace via :class:`WorkspaceManager`. In production the built SPA is served
from ``frontend/dist``; during development Vite proxies ``/api`` here.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import session
from .store import Store
from .workspace import WorkspaceError, WorkspaceManager


class SaveRequest(BaseModel):
    entities: List[dict]
    status: str = "in_progress"


class NameRequest(BaseModel):
    name: str


def create_app(manager: WorkspaceManager, static_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="NER Entity Annotator", version="0.2.0")

    # ---- session helpers --------------------------------------------------
    def current_user(request: Request) -> dict:
        data = session.read(request)
        if data is None:
            raise HTTPException(status_code=401, detail="not identified")
        return data

    def current_store(user: dict = Depends(current_user)) -> Store:
        store = manager.get_store(user["slug"])
        if store is None:
            # Identified but hasn't uploaded a file yet.
            raise HTTPException(status_code=409, detail="no workspace: upload a file first")
        return store

    # ---- session routes ---------------------------------------------------
    @app.get("/api/session")
    def whoami(request: Request, response: Response) -> dict:
        data = session.read(request)
        if data is None:
            raise HTTPException(status_code=401, detail="not identified")
        # Refresh the cookie so active users don't silently expire.
        session.issue(response, slug=data["slug"], name=data["name"])
        return {
            "slug": data["slug"],
            "name": data["name"],
            "has_workspace": manager.has_workspace(data["slug"]),
        }

    @app.post("/api/session")
    def identify(req: NameRequest, response: Response) -> dict:
        name = req.name.strip()
        slug = session.slugify(name)
        if not slug:
            raise HTTPException(
                status_code=400, detail="name must contain at least one letter or digit"
            )
        session.issue(response, slug=slug, name=name)
        return {"slug": slug, "name": name, "has_workspace": manager.has_workspace(slug)}

    @app.delete("/api/session")
    def sign_out(response: Response) -> dict:
        session.clear(response)
        return {"ok": True}

    # ---- workspace routes -------------------------------------------------
    @app.get("/api/workspace")
    def get_workspace(user: dict = Depends(current_user)) -> dict:
        info = manager.workspace_info(user["slug"])
        if info is None:
            raise HTTPException(status_code=409, detail="no workspace: upload a file first")
        return info

    @app.post("/api/workspace")
    async def upload_workspace(
        user: dict = Depends(current_user),
        file: UploadFile = File(...),
        types: str = Form(""),
    ) -> dict:
        raw = await file.read()
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        try:
            return manager.create_workspace(
                user["slug"],
                raw=raw,
                filename=file.filename or "input.jsonl",
                types=type_list or None,
            )
        except WorkspaceError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/api/workspace/output")
    def download_output(user: dict = Depends(current_user)) -> FileResponse:
        path = manager.output_path(user["slug"])
        if path is None:
            raise HTTPException(status_code=409, detail="no workspace: upload a file first")
        info = manager.workspace_info(user["slug"]) or {}
        name = info.get("filename") or "output.jsonl"
        download_name = name if name.endswith(".jsonl") else f"{name}.annotations.jsonl"
        return FileResponse(path, media_type="application/x-ndjson", filename=download_name)

    # ---- annotation routes (scoped to the caller's store) -----------------
    @app.get("/api/config")
    def get_config(store: Store = Depends(current_store)) -> dict:
        return {**store.config(), "warnings": store.warnings}

    @app.get("/api/docs")
    def list_docs(store: Store = Depends(current_store)) -> List[dict]:
        return store.summaries()

    @app.get("/api/docs/{doc_id}")
    def get_doc(doc_id: str, store: Store = Depends(current_store)) -> dict:
        doc = store.get_doc(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"unknown doc_id {doc_id!r}")
        return doc

    # PUT for normal saves; POST alias so navigator.sendBeacon (POST-only) works on unload.
    @app.put("/api/docs/{doc_id}")
    @app.post("/api/docs/{doc_id}")
    def save_doc(doc_id: str, req: SaveRequest, store: Store = Depends(current_store)) -> dict:
        try:
            return store.save_doc(doc_id, req.entities, req.status)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown doc_id {doc_id!r}")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    # ---- static SPA -------------------------------------------------------
    if static_dir is not None and static_dir.exists():
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

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
