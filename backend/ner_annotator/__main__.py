"""CLI entrypoint:  python -m ner_annotator --input data.jsonl --output annotations.jsonl"""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

import uvicorn

from .main import create_app
from .store import Store

# frontend/dist relative to the repo root (backend/ner_annotator/__main__.py -> repo root)
DEFAULT_STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"


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
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    if not types:
        parser.error("--types must list at least one non-empty entity type")

    static_dir = Path(args.static) if args.static else DEFAULT_STATIC
    store = Store(args.input, args.output, types=types)

    if store.warnings:
        print(f"[ner_annotator] {len(store.warnings)} load warning(s):")
        for w in store.warnings[:20]:
            print(f"  - {w}")

    app = create_app(store, static_dir=static_dir)

    url = f"http://{args.host}:{args.port}/"
    print(f"[ner_annotator] {len(store.order)} docs loaded from {args.input}")
    print(f"[ner_annotator] entity types: {', '.join(store.types)}")
    print(f"[ner_annotator] writing annotations to {args.output}")
    print(f"[ner_annotator] serving at {url}")
    if not args.no_open and static_dir.exists():
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
