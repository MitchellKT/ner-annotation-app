# ner-annotator-llm

A DSPy signature that annotates entities with an LLM, plus the code that turns its answer into
**character-level** annotations.

An LLM cannot count characters, so it is never asked for `start` / `end`. It quotes text instead,
and this package grounds the quotes back to offsets — dropping, never inventing, whatever fails to
match. One pass covers every entity type.

```bash
pip install ner-annotator-llm[dspy]
```

## Use

```python
import dspy
from ner_annotator_llm import EntityAnnotator

dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-5"))
prediction = EntityAnnotator()(document=text)

prediction.entities   # [{"type": "PER", "mentions": [{"start": 0, "end": 12}]}, ...]
prediction.unresolved # mentions that could not be grounded
```

`EntityAnnotator(types=["PER", "LOC"])` narrows a run to a subset of the registered types.

Without DSPy, ground a prediction you obtained any other way — an `Annotation` or a plain dict of
the same shape:

```python
from ner_annotator_llm import resolve_entities, entities_to_json

resolution = resolve_entities(text, {"entities": [...], "sentences": [...]})
entities_to_json(resolution.entities)
```

## Entity types and their guidelines

Everything the prompt says lives under `ner_annotator_llm/guidelines/` as markdown, and it is meant
to be edited:

| file | what it holds |
| --- | --- |
| `general.md` | how to *report* annotations: the entity list, then the sentences, quoting, fragments, flags |
| `entities/PER.md`, `entities/LOC.md`, … | one file per entity type, named after it |

An entity file starts with a `# TYPE — one-line description` heading and continues with that
type's rules:

```markdown
# PER — An individual human being, real or fictional.

## What counts as a PER entity
- One entity per *person*, not per name: every way the text refers to that same person ...
```

`entities/` is the **single source of truth for the type set**. Dropping a file into it:

- adds a member to the `EntityType` enum, which is the type of `EntityCandidate.type`, so the
  model is offered a closed list and a predicted type is validated rather than trusted;
- adds `TYPE — description` to the index at the top of the instructions, and the file itself
  below it;
- makes that type valid in the output.

No code changes, and no second pass over the document — the model classifies each entity it finds
into one of the types. Ships with `PER`, `JOB_TITLE`, `LOC`, `ORG` and `TIME`.

The guidelines are the signature's **instructions**, not input fields — the document is the only
thing that varies per call:

```python
from ner_annotator_llm import annotate_signature

annotate_signature().instructions        # task text + general.md + every entity file
annotate_signature(["PER"])              # narrowed to one type
```

`EntityAnnotator(instructions=...)` replaces the text outright, e.g. to plug in an optimised
prompt.

## What the model returns

Two parts, in this order. First a **roster** of the distinct entities, each under a unique name.
Then the **sentences**: every sentence containing a mention, quoted once for the whole document,
holding every mention in it tagged with the name of the entity it refers to.

```json
{"entities": [{"name": "Barack Obama", "type": "PER"},
              {"name": "Michelle Obama", "type": "PER"},
              {"name": "Chicago", "type": "LOC"}],
 "sentences": [{"sentence": "Obama said that he and his wife had left Chicago.",
                "mentions": [{"entity": "Barack Obama", "text": "Obama"},
                             {"entity": "Barack Obama", "text": "he"},
                             {"entity": "Barack Obama", "text": "his", "implicit": true},
                             {"entity": "Michelle Obama", "text": "his wife", "relative": true},
                             {"entity": "Chicago", "text": "Chicago"}]}]}
```

The name **is** the identifier — there is no separate id to keep in sync. Two entities that would
share a name are told apart with a distinguishing detail ("Smith (the lawyer)" / "Smith (the
judge)"), which the guidelines ask for and `to_annotation` does with a numeric suffix.

Quoting each sentence **once for the document** — rather than once per entity that occurs in it —
is where the answer's cost is. On a paragraph with several entities per sentence this roughly
halves the output (measured: 3618 → 1772 characters on a 3-sentence, 9-entity, 26-mention
paragraph), and the model walks the text once instead of re-reading it per entity, which is also
the easier question to answer exhaustively: "who else in this sentence refers to an entity?"

The sentence still does the disambiguating work — it says *which* occurrence of "Obama" is meant
when the document has five. Repeated wording is not deduplicated: three references means three
entries, matched left to right.

The price is referential integrity: a mention's `entity` has to name a roster entry. The name is
matched exactly, else against the closest one, so a near miss still lands — but a name matching
nothing drops the mention, since without a roster entry there is no type to give it.

A **non-continuous** mention is written as its fragments joined by `[…]`: in *"Annie and George
Washington visited Mount Vernon"*, the wife is `"Annie[…]Washington"`, one mention split by the
words that belong to George. `relative` marks a mention that identifies its entity only through a
relation to something else ("John's secretary"); `implicit` marks one that names the entity in a
background role ("Maxim" in "with Maxim's brother"). The two are independent.

## What comes out

```json
{"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]}]}
```

`end` is exclusive (`text[start:end]`) and offsets are Unicode code points, matching Python `str`.
A continuous mention is written as plain `{"start", "end"}`; `relative` / `implicit` appear only
when true. `Entity`, `Mention` and `Fragment` are plain dataclasses; `entities_to_json` (or
`Resolution.to_json()`) produces the shape above.

## How grounding works

The whole of it is one idea applied twice: **look for the exact text, and fall back to a fuzzy
match when it is not there.**

`resolve_entities` locates each quoted sentence in the document — exactly, else fuzzily — which
gives a window. Each mention's fragments are then located inside that window the same way, left to
right from where the previous mention started, so "Obama … Obama" in one sentence gets two spans
rather than one span twice, while a nested mention ("Obama" inside "Barack Obama") still lands
where it belongs. The mention is filed under the entity it names, matched against the roster
exactly, else by closest name.

Exact matching prefers whole words, which matters more than it looks: mentions are often pronouns,
and a plain substring search puts "he" inside "The". Fuzzy matching anchors on a substantial shared
run and spans from the first matching block to the last, so a mention retyped with different
spacing or punctuation still covers the right characters — and an answer the document simply does
not contain is refused rather than placed somewhere plausible.

**Nothing is invented.** A mention that cannot be placed, or that names no known entity, is dropped
and listed in `Resolution.unresolved`; an entity nobody mentioned is dropped too.

## From annotated data: round-trip and few-shot demos

`examples.py` runs the conversion the other way — a document annotated in the character-level
schema becomes the quoted, sentence-grouped format the model answers in:

```python
from ner_annotator_llm import to_annotation

to_annotation(text, [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}])
# Annotation(entities=[EntityCandidate(name="Annie", type=PER)],
#            sentences=[SentenceMentions(sentence="Annie waved.",
#                mentions=[MentionCandidate(entity="Annie", text="Annie")])])
```

Each entity is named after its longest mention (repeats get a numeric suffix, so names stay
unique); every mention of every entity is filed into the sentence it falls in (`sentence_spans` does the segmentation — a small heuristic, since it only
decides how much context a demo quotes), split mentions are rejoined with `[…]`, and the flags
carry over. A mention straddling a sentence boundary keeps both halves,
so the quoted sentence always contains its mentions. A type with no file in `entities/` cannot be
expressed and raises.

Feeding the result back through `resolve_entities` must return the original offsets — the
round-trip tests assert exactly that over fragmented, nested, repeated, emoji and RTL documents.
So the same conversion serves two purposes: it checks the grounding, and it turns a gold corpus
into **few-shot demos**, letting the corpus demonstrate the format instead of describing it twice:

```python
from ner_annotator_llm import EntityAnnotator, examples_from_jsonl

annotator = EntityAnnotator(demos=examples_from_jsonl("gold.jsonl")[:3])
```

`examples_from_jsonl` takes any `.jsonl` whose records have `text` and `entities` — the annotator's
own output files work as they are; other keys are ignored and unannotated records are skipped.
`to_example(text, entities)` builds one demo, and `annotator.set_demos(...)` swaps them later. A
demo is just a document and its answer — the guidelines are in the instructions, so they cost
nothing per demo. Pass `reasoning=...` to demonstrate the chain of thought too.

## Tests

```bash
pip install -e ".[dev]"
pytest        # grounding, the round trip, the guidelines registry, and the signature
```

The signature tests skip themselves when DSPy is not installed.
