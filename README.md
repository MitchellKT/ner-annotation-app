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
- A mention may be **non-continuous**: a single mention made of several disjoint *fragments*,
  written as `{"fragments": [{"start": ..., "end": ...}, ...]}` in place of `{"start", "end"}`.
  E.g. in *"Annie and George Washington"*, the mention "Annie Washington" is
  `{"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]}`. Fragments are kept sorted
  and non-overlapping (touching fragments are merged). Continuous mentions are always written back
  in the plain `{"start", "end"}` shape, so files without non-continuous mentions keep the original schema.

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

# 3) launch — a multi-user server; opens http://127.0.0.1:8000
cd ../backend
python -m ner_annotator --data-dir ./_data --types PER,LOC,ORG,TIME
```

The app is a **multi-user system**. Each annotator:

1. **Identifies** by name on the first screen (a signed, HttpOnly cookie session — no
   password; the name is the identity, so annotations are saved under it).
2. **Uploads** the `.jsonl` file they want to annotate. Every user gets their own isolated
   workspace under `<data-dir>/users/<slug>/`, so different people annotate different files
   concurrently without interfering.
3. Annotates as before, and can **download their `output.jsonl`** at any time (⭳ output in
   the toolbar). "file…" swaps the current file (the old one is archived, never lost);
   the name button switches user.

`--data-dir` / `-d` is the root for all workspaces (default `$DATA_DIR` or `/data`). Per-user
state — input, output, and per-doc review status — persists there, so a restart transparently
resumes every user. `SESSION_SECRET` should be set to a stable value in production so sessions
survive restarts and can't be forged.

### Configuring entity types

`--types` / `-t` (or `$DEFAULT_TYPES`) sets the **default** comma-separated label set offered to
a new workspace; each annotator may override it on the upload screen.

The first nine types map to the digit keys `1`–`9` in the UI; any beyond that are still
selectable from each entity card's type dropdown. Types are free-form strings — predictions in
an uploaded file may use labels outside this set and will still import.

### Development (hot reload)

```bash
# terminal 1 — API (SESSION_SECRET keeps cookies stable across restarts in dev)
cd backend && SESSION_SECRET=dev python -m ner_annotator --data-dir ./_data --types PER,LOC,ORG,TIME --no-open
# terminal 2 — Vite dev server (proxies /api to :8000)
cd frontend && npm run dev      # http://localhost:5173
```

### Kubernetes

The app is built to run as a container on k8s: identify → upload → annotate, with per-user
files on a persistent volume. See [`k8s/`](k8s/) for manifests (Deployment, PVC, Service,
Ingress, Secret, ConfigMap) and [`k8s/README.md`](k8s/README.md) for the deploy walkthrough and
the single-replica rationale.

## Keyboard shortcuts

There is **one digit key per configured `--types` entry** (the first nine, `1`–`9`); the toolbar
shows the live `1 PER · 2 LOC · …` legend so you always know which number is which type.

| Key | Action |
| --- | --- |
| `1`…`N` | New entity of that type (the Nth configured type) from the selected text |
| `1`…`N` (nothing selected) | Change the active entity's type to that type |
| click an entity (text selected) | Add the selection to that entity — the only way to extend an existing entity |
| `Enter` / `Esc` (id prompt) | Save / skip the optional unique identifier asked after creating an entity |
| `x` (text selected) | Extend a mention with the selection as an extra **fragment** (non-continuous mention): targets the hovered mention, else the active entity's last mention |
| click a mention chip (text selected) | Add the selection as a fragment of that mention |
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

**Auto-annotate repeats.** With the *auto-annotate repeats* checkbox (text toolbar, on by
default), annotating a mention also annotates every other identical occurrence of that text in
the document — like walking Ctrl+F matches, but case-sensitive and in one keystroke. This applies
both to creating an entity (digit keys) and to adding a mention to an existing entity (clicking
its card). Auto-added mentions are ordinary mentions: remove any false positive with its chip's
`×` (or hover + `Del`), and one `Ctrl+Z` undoes the whole batch. Untick the checkbox to go back
to annotating only the selected span.

**Unique identifiers.** Right after you create an entity, a small prompt asks for its optional
unique identifier (e.g. `Q76`). Press `Enter` to save it or `Esc` to skip — it never blocks the
flow. The id shows as a badge on the entity card; click the badge (or the card's `id` button)
to add or edit it later. Ids are saved as the entity's `"uid"` field in the output.

**Non-continuous mentions.** To annotate e.g. "Annie Washington" in *"Annie and George
Washington"*: select "Annie", press its type digit (a new entity + mention), then select
"Washington" and press `x` — the two spans become **one mention**, shown in the chip as
`Annie ‥ Washington` and underlined in the text as two linked spans. `x` extends the hovered
mention if you're pointing at a chip, otherwise the active entity's most recent mention; with
a selection you can also click any mention chip directly. In a multi-fragment chip each
fragment has its own `×` to detach just that fragment.

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
backend/ner_annotator/   models.py · store.py           (per-file schema + JSONL I/O)
                         session.py · workspace.py      (named sessions + per-user workspaces)
                         main.py · __main__.py          (FastAPI app + server entrypoint)
frontend/src/            lib/segments.ts · lib/offsets.ts               (rendering & selection core)
                         session.ts · components/NameScreen · UploadScreen (identify + upload gate)
                         store.ts · api.ts · components/ · hooks/       (annotator UI)
k8s/                     Deployment · PVC · Service · Ingress · Secret · ConfigMap
sample/input.jsonl       example docs: predictions, from-scratch, nested, unicode
```
