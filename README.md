# NER Entity Annotator

A clean, keyboard-first web app for annotating an **entity-clustering** extension of NER:
each *entity* is a typed cluster (`PER` / `LOC` / `ORG` / `TIME`) of reference **mentions**,
where every mention is a character span `(start, end)` over the document text.

It is built for two workflows, both optimised for minimal time per document:

1. **Refine** an existing model/LLM prediction — skim, confirm correct entities in one keystroke,
   and fix the rest (merge over-split entities, split wrong groupings, reassign / add / remove mentions).
2. **Annotate from scratch** when no prediction is present.

## Data format

Input and output are the same `.jsonl` schema, one record per line:

```json
{"doc_id": "doc-0001", "text": "Barack Obama ... Hawaii.", "entities": [
  {"type": "PER", "mentions": [{"start": 0, "end": 12}, {"start": 33, "end": 38}]},
  {"type": "LOC", "mentions": [{"start": 25, "end": 31}]}
]}
```

- `end` is **exclusive** (`text[start:end]`); offsets are **Unicode code points** (matching Python `str`).
- `entities` is optional on input (a prediction to refine). Mentions may also be given as `[start, end]` pairs.
- Mentions may **overlap / nest** (e.g. `LOC` "America" inside `ORG` "Bank of America").

The output file is written continuously as you annotate. Per-document review status is kept in a
sidecar `<output>.jsonl.state.json` so the output stays exactly on-schema.

## Run

```bash
# 1) install backend (uses uv; plain pip works too)
cd backend
uv pip install -e ".[dev]"        # or: pip install -e ".[dev]"

# 2) build the frontend once (served by the backend in production)
cd ../frontend
npm install
npm run build

# 3) launch — opens http://127.0.0.1:8000
cd ../backend
python -m ner_annotator --input ../sample/input.jsonl --output ../sample/annotations.jsonl
```

Re-running with the same `--output` **resumes** the previous session (annotations + status).

### Development (hot reload)

```bash
# terminal 1 — API
cd backend && python -m ner_annotator -i ../sample/input.jsonl -o ../sample/annotations.jsonl --no-open
# terminal 2 — Vite dev server (proxies /api to :8000)
cd frontend && npm run dev      # http://localhost:5173
```

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `P` `L` `O` `T` | New entity (PER/LOC/ORG/TIME) from the selected text |
| `1`–`9` | Add selection to entity N (or activate it when nothing is selected) |
| `a` | Add selection to the active entity |
| `n` | New empty entity |
| `Tab` / `Shift+Tab` | Cycle the active entity |
| `Del` / `Backspace` | Delete the hovered mention |
| `r` | Confirm / unconfirm the active entity |
| `A` | Accept all (confirm every entity) |
| `m` | Merge: press `m`, then click another entity (or drag card onto card) |
| `s` | Split the hovered mention into its own entity |
| drag chip → card | Reassign a mention to another entity |
| `Esc` | Cancel a pending merge / clear selection |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / redo |
| `d` | Mark document done & jump to next unreviewed |
| `←` / `→` | Previous / next document |
| `?` | Toggle the shortcut help |

The **active entity** (outlined in the right panel) is the default target for new spans — set it once,
then double-click each coreferent mention to add them quickly.

## Tests

```bash
cd backend && uv run pytest            # store load / merge / save round-trip, unicode, validation
cd frontend && npm test                # segment tiling + offset/selection logic
```

## Project layout

```
backend/ner_annotator/   models.py · store.py · main.py · __main__.py   (FastAPI + file I/O)
frontend/src/            lib/segments.ts · lib/offsets.ts               (rendering & selection core)
                         store.ts · api.ts · components/ · hooks/       (UI)
sample/input.jsonl       example docs: predictions, from-scratch, nested, unicode
```
