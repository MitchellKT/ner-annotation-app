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
{"doc_id": "doc-0001", "type": "news", "source": "cnn.com", "text": "Barack Obama ... Hawaii.", "entities": [
  {"type": "PER", "mentions": [{"start": 0, "end": 12}, {"start": 33, "end": 38}]},
  {"type": "LOC", "mentions": [{"start": 25, "end": 31}]}
]}
```

- `end` is **exclusive** (`text[start:end]`); offsets are **Unicode code points** (matching Python `str`).
- `type` and `source` are optional **document metadata**: `type` is the kind of text
  (e.g. `news`, `article`, `social`) and `source` is where it came from (e.g. a site).
  They drive the per-annotator source-selection screen and are shown as a header while
  annotating. Missing values are treated as `"unspecified"`. Both are passed through to
  the output unchanged.
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

## Multiple annotators

The app is multi-user. The **login screen** is always the entry point — every time the app is
opened it asks for an annotator name, starting from an empty field, so a shared browser never
silently resumes as whoever used it last. Each annotator's work is stored independently, so
signing back in with the same name resumes exactly that person's annotations, review status and
source selection. Use **Switch user** (top bar) to sign in as someone else.

After logging in, a **source-selection screen** lists every `source` grouped by document `type`
(with document counts); tick the sources you want to label. **All sources start selected**, so
annotating everything just means clicking through. Long source lists stay manageable: they flow
into multiple columns, type headers stick while scrolling, and a filter box narrows the list
(with the bulk select/clear button then acting on just the matches). Only the selected documents then
appear in the navigator. The selection is saved per annotator and can be changed any time with
the **Sources** button. While annotating, the current document's **type and source are shown as
a header** in the top bar.

Per-user state lives next to the output under `<output>.jsonl.users/`:

```
<output>.jsonl.users/
  users.json                 # annotator-name -> on-disk slug registry
  <slug>.jsonl               # that annotator's annotations (the on-schema output)
  <slug>.jsonl.state.json    # per-document review status
  <slug>.prefs.json          # saved source selection
```

The `--output` path names this location; the plain single-file output described above is the
per-annotator `<slug>.jsonl` inside it.

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
backend/ner_annotator/   models.py · store.py · workspace.py            (per-user file I/O)
                         main.py · __main__.py                          (FastAPI app + CLI)
frontend/src/            lib/segments.ts · lib/offsets.ts               (rendering & selection core)
                         store.ts · api.ts · components/ · hooks/       (UI, incl. login + source select)
sample/input.jsonl       example docs: metadata, predictions, from-scratch, nested, unicode
```
