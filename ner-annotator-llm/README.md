# ner-annotator-llm

A DSPy signature that annotates entities with an LLM, plus the code that turns its answer into
**character-level** annotations.

An LLM cannot count characters, so it is never asked for `start` / `end`. It quotes text instead,
and this package grounds the quotes back to offsets — dropping, never inventing, whatever fails to
match.

```bash
pip install ner-annotator-llm[dspy]
```

## Use

```python
import dspy
from ner_annotator_llm import EntityAnnotator

dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-5"))
prediction = EntityAnnotator(entity_type="PER")(document=text)

prediction.entities   # [{"type": "PER", "mentions": [{"start": 0, "end": 12}]}, ...]
prediction.problems   # mentions that could not be grounded, with the reason
```

Without DSPy, ground a prediction you obtained any other way — `candidates` may be
`EntityCandidate` objects or plain dicts in the same shape:

```python
from ner_annotator_llm import resolve_entities, entities_to_json

resolution = resolve_entities(text, candidates)
entities_to_json(resolution.entities)
```

## What the model returns

Each mention comes back as two verbatim quotations — the **mention** itself and the **sentence**
around it, which says *which* occurrence of "Obama" is meant:

```json
{"name": "Annie Washington", "type": "PER", "mentions": [
  {"mention": "Annie[…]Washington",
   "sentence": "Annie and George Washington visited Mount Vernon.",
   "relative": false, "implicit": false}
]}
```

A **non-continuous** mention is written as its fragments joined by `[…]` — above, *Annie
Washington* is one mention split by the words that belong to George. `relative` marks a mention
that identifies its entity only through a relation to something else ("John's secretary");
`implicit` marks one that names the entity in a background role ("Maxim" in "with Maxim's
brother"). The two are independent.

## What comes out

```json
{"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]}]}
```

`end` is exclusive (`text[start:end]`) and offsets are Unicode code points, matching Python `str`.
A continuous mention is written as plain `{"start", "end"}`; `relative` / `implicit` appear only
when true. `Entity`, `Mention` and `Fragment` are plain dataclasses; `entities_to_json` (or
`Resolution.to_json()`) produces the shape above.

## How grounding works

`resolve_entities` locates the quoted sentence in the document, then places each fragment inside
that window, left to right, with backtracking. Matching runs over a normalised copy of the text
(whitespace collapsed, case folded, curly quotes and dashes flattened, bidi and zero-width marks
dropped) with a per-character index map back to the original, so a model that reflows a line break
or straightens a quote still lands on the right characters.

- Repeated surface forms are handed out in reading order, so "Alice … then Alice" gets two spans.
- Nested mentions still resolve — "Washington" inside "George Washington" is fine.
- A sentence that cannot be found falls back to a fuzzy window, then to the whole document.
- **Nothing is invented.** A mention that does not match is dropped, an entity left with no
  mentions is pruned, and every deviation is reported in `Resolution.problems` with a reason
  (`sentence-not-found`, `mention-outside-sentence`, `mention-not-found`, `empty-mention`,
  `duplicate-mention`) and a `dropped` flag.

## Guidelines per entity type

The entity type and its guidelines are **input fields** of the signature, not part of the task
text, so one signature serves every type and the wording can be tuned — or optimised by DSPy —
without touching the task. `PER` guidelines are written out in `guidelines.py`; other types fall
back to a placeholder meant to be replaced:

```python
from ner_annotator_llm import EntityAnnotator, guidelines_for

EntityAnnotator(entity_type="LOC", guidelines=my_loc_guidelines)
guidelines_for("PER")   # the built-in text
```

Run one pass per entity type and concatenate the entity lists.

## Tests

```bash
pip install -e ".[dev]"
pytest        # grounding: fragments, nesting, repeats, unicode/RTL, every problem path
```

The signature tests skip themselves when DSPy is not installed.
