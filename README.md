# NER Entity Annotator

A clean, keyboard-first web app for annotating an **entity-clustering** extension of NER:
each *entity* is a typed cluster (e.g. `PER` / `LOC` / `ORG` / `TIME`) of reference **mentions**,
where every mention is a character span `(start, end)` over the document text.
The entity type set is configurable per run (see `--types`).

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
- An entity may carry an optional **`"uid"`** — a free-form unique identifier (e.g. a Wikidata QID
  or knowledge-base key): `{"type": "PER", "uid": "Q76", "mentions": [...]}`. It is omitted from
  the output when unset, so files without ids keep the original schema.

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
python -m ner_annotator --input ../sample/input.jsonl --output ../sample/annotations.jsonl --types PER,LOC,ORG,TIME
```

Re-running with the same `--output` **resumes** the previous session (annotations + status).

### Configuring entity types

`--types` / `-t` is **required**: pass the comma-separated label set for this run.

```bash
python -m ner_annotator -i in.jsonl -o out.jsonl --types PER,LOC,ORG,MISC,EVENT
```

The first nine types map to the digit keys `1`–`9` in the UI; any beyond that are still
selectable from each entity card's type dropdown. Types are free-form strings — predictions
loaded from `--input` may use labels outside this set and will still import.

### Development (hot reload)

```bash
# terminal 1 — API
cd backend && python -m ner_annotator -i ../sample/input.jsonl -o ../sample/annotations.jsonl --types PER,LOC,ORG,TIME --no-open
# terminal 2 — Vite dev server (proxies /api to :8000)
cd frontend && npm run dev      # http://localhost:5173
```

## Keyboard shortcuts

There is **one digit key per configured `--types` entry** (the first nine, `1`–`9`); the toolbar
shows the live `1 PER · 2 LOC · …` legend so you always know which number is which type.

| Key | Action |
| --- | --- |
| `1`…`N` | New entity of that type (the Nth configured type) from the selected text |
| `1`…`N` (nothing selected) | Change the active entity's type to that type |
| click an entity (text selected) | Add the selection to that entity — the only way to extend an existing entity |
| `Enter` / `Esc` (id prompt) | Save / skip the optional unique identifier asked after creating an entity |
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

**Unique identifiers.** Right after you create an entity, a small prompt asks for its optional
unique identifier (e.g. `Q76`). Press `Enter` to save it or `Esc` to skip — it never blocks the
flow. The id shows as a badge on the entity card; click the badge (or the card's `id` button)
to add or edit it later. Ids are saved as the entity's `"uid"` field in the output.

To grow an existing entity, select the text then **click that entity's card** in the right panel
(this is the only way to add a mention to an existing entity). The **active entity** (outlined in
the right panel) is what the type/confirm/merge shortcuts act on; set it with `Tab`, by clicking a
highlight in the text, or by clicking a card when no text is selected.

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
