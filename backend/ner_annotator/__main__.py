"""CLI entrypoint:  python -m ner_annotator --input data.jsonl --output annotations.jsonl"""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

import uvicorn

from .main import create_app
from .mongo import DEFAULT_COLLECTION, DEFAULT_DATABASE
from .workspace import Workspace

# frontend/dist relative to the repo root (backend/ner_annotator/__main__.py -> repo root)
DEFAULT_STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _make_exporter(parser: argparse.ArgumentParser, args: argparse.Namespace):
    """Build the MongoDB mirror, or None when --mongo-uri wasn't given."""
    if not args.mongo_uri:
        return None

    from .mongo import MongoExporter

    try:
        exporter = MongoExporter(args.mongo_uri, args.mongo_db, args.mongo_collection)
    except RuntimeError as exc:  # pymongo missing — a config error worth failing on
        parser.error(str(exc))

    # An unreachable server is only warned about: the .jsonl output is the source
    # of truth, so annotating must still be possible while Mongo is down.
    error = exporter.ping()
    if error:
        print(f"[ner_annotator] warning: MongoDB unreachable ({error}); will retry on each save")
    return exporter


def main() -> None:
    parser = argparse.ArgumentParser(prog="ner_annotator", description="Entity-clustering NER annotator")
    parser.add_argument("--input", "-i", required=True, help="input .jsonl to annotate")
    parser.add_argument("--output", "-o", required=True, help="output .jsonl for annotations")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", "-p", type=int, default=8000)
    parser.add_argument("--static", default=None, help="path to built frontend (frontend/dist)")
    parser.add_argument(
        "--types",
        "-t",
        required=True,
        help="comma-separated entity types, e.g. PER,LOC,ORG,TIME; "
        "the first nine map to digit keys 1-9 in the UI",
    )
    parser.add_argument("--no-open", action="store_true", help="don't open the browser on start")
    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="also mirror annotations to this MongoDB, e.g. mongodb://localhost:27017 "
        "(the .jsonl output is written either way)",
    )
    parser.add_argument("--mongo-db", default=DEFAULT_DATABASE, help="MongoDB database name")
    parser.add_argument(
        "--mongo-collection", default=DEFAULT_COLLECTION, help="MongoDB collection name"
    )
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    if not types:
        parser.error("--types must list at least one non-empty entity type")

    exporter = _make_exporter(parser, args)

    static_dir = Path(args.static) if args.static else DEFAULT_STATIC
    workspace = Workspace(args.input, args.output, types=types, exporter=exporter)

    if workspace.warnings:
        print(f"[ner_annotator] {len(workspace.warnings)} load warning(s):")
        for w in workspace.warnings[:20]:
            print(f"  - {w}")

    app = create_app(workspace, static_dir=static_dir)

    url = f"http://{args.host}:{args.port}/"
    print(f"[ner_annotator] {workspace.n_docs} docs loaded from {args.input}")
    print(f"[ner_annotator] entity types: {', '.join(workspace.corpus.types)}")
    print(f"[ner_annotator] per-user annotations under {workspace.users_root}")
    if exporter is not None:
        print(
            f"[ner_annotator] mirroring to MongoDB "
            f"{args.mongo_db}.{args.mongo_collection}"
        )
    print(f"[ner_annotator] serving at {url}")
    if not args.no_open and static_dir.exists():
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
