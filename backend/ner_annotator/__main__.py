"""CLI entrypoint (multi-user server).

    python -m ner_annotator --data-dir /data --types PER,LOC,ORG,TIME

Each annotator identifies by name and uploads their own file; per-user
workspaces live under ``<data-dir>/users/<slug>/``. ``--types`` is only the
*default* type set offered to a new workspace (each upload may override it).
"""

from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path

import uvicorn

from .main import create_app
from .workspace import WorkspaceManager

# frontend/dist relative to the repo root (backend/ner_annotator/__main__.py -> repo root)
DEFAULT_STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def main() -> None:
    parser = argparse.ArgumentParser(prog="ner_annotator", description="Entity-clustering NER annotator")
    parser.add_argument(
        "--data-dir",
        "-d",
        default=os.environ.get("DATA_DIR", "/data"),
        help="root directory for per-user workspaces (default: $DATA_DIR or /data)",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", "-p", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--static", default=None, help="path to built frontend (frontend/dist)")
    parser.add_argument(
        "--types",
        "-t",
        default=os.environ.get("DEFAULT_TYPES", "PER,LOC,ORG,TIME"),
        help="default comma-separated entity types offered to new workspaces; "
        "the first nine map to digit keys 1-9 in the UI",
    )
    parser.add_argument("--no-open", action="store_true", help="don't open the browser on start")
    args = parser.parse_args()

    default_types = [t.strip() for t in args.types.split(",") if t.strip()]
    if not default_types:
        parser.error("--types must list at least one non-empty entity type")

    static_dir = Path(args.static) if args.static else DEFAULT_STATIC
    manager = WorkspaceManager(args.data_dir, default_types=default_types)
    app = create_app(manager, static_dir=static_dir)

    url = f"http://{args.host}:{args.port}/"
    print(f"[ner_annotator] data dir: {args.data_dir}")
    print(f"[ner_annotator] default entity types: {', '.join(default_types)}")
    print(f"[ner_annotator] serving at {url}")
    if not os.environ.get("SESSION_SECRET"):
        print("[ner_annotator] WARNING: SESSION_SECRET unset — sessions won't survive a restart")
    if not args.no_open and static_dir.exists():
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
