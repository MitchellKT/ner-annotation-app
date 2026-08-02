# General annotation guidelines

These rules hold for every entity type. The type-specific guidelines say *what*
to annotate; this file says *how* to report it.

You answer in two parts, in this order: the **entity list**, then the
**sentences**. Read the whole document before writing either — the entity list
has to be complete, because every mention points back into it.

## Part 1 — the entity list

One entry per distinct referent in the document.

- An **entity** is one real-world referent. All mentions of the same referent
  belong to **one** entity: "Barack Obama", "Obama", "the president" and "he"
  are four mentions of one entity, not four entities.
- Two referents are never merged, even when they share a surface form. Two
  different people called "Smith" are two entities; one company and the city it
  is named after are two entities.
- `label` is a short unique id — use `e1`, `e2`, `e3`, … in order. It is how the
  mentions refer back to the entity, so every label must be unique, and a
  mention must never use a label that is not in this list.
- `name` is a readable name for the referent ("Barack Obama", "the Chancellor's
  plan"), for a human reading the answer.
- `type` is one of the types in the entity guidelines, and nothing else.
- List an entity only if it is actually mentioned in the document. Annotate only
  what the text says: do not add entities implied by world knowledge, and do not
  resolve a reference the text leaves open. A document with no entity of any
  known type gets two empty lists.

## Part 2 — the sentences

Walk the document from the start. For **every sentence that contains at least
one mention of any entity**, give one entry:

- `sentence` is the full sentence, copied **verbatim** from the document —
  same spelling, case, punctuation and diacritics. It is what locates the
  mentions, so when the same wording occurs more than once in the document,
  quote the occurrence you mean.
- `mentions` holds **every** mention in that sentence, of **every** entity, in
  the order they appear. Each carries the `label` of the entity it refers to and
  the mention `text` copied verbatim.

> "Obama said that he and his wife had left Chicago, where Obama grew up."

is a single entry whose mentions are `Obama` (e1), `he` (e1), `his` (e1),
`his wife` (e2), `Chicago` (e3) and `Obama` (e1) — six entries, in that order,
under one quoted sentence.

Rules for this part:

- A sentence appears **once**, no matter how many entities it mentions. Do not
  repeat a sentence per entity, and do not split one sentence into two entries.
- Repeated wording is not deduplicated: if the same word refers to an entity
  three times in the sentence, list it three times, and the occurrences are
  matched left to right.
- Mentions may **overlap or nest**, including across types and entities:
  "America" (a place) inside "Bank of America" (an organisation), or a job title
  inside a longer reference to the person holding it. List both.
- Skip a sentence entirely if it contains no mentions.

## How to quote a mention

You are not asked for character positions — you quote text, and the surrounding
code locates it. Copy the mention exactly as it appears; never paraphrase,
translate, expand an abbreviation or normalise anything.

A single reference can be split by words that belong to something else. Write it
as its fragments joined by `[…]`:

> "Annie and George Washington visited Mount Vernon."

The wife is mentioned as `Annie[…]Washington`; "George Washington" is a separate
entity. Use this **only** for one reference cut in two — two separate mentions
of the same entity are two entries in the list, never fragments of one.

## Flags

Two independent booleans on each mention; a mention may carry neither, either,
or both. Both default to false.

- `relative` — the mention identifies its entity **only through a relation** to
  something else and never names it: "the father of Abraham", "John's
  secretary", "her husband", "the company's largest rival".
- `implicit` — the mention does name its entity, but the sentence is **not
  about** it: it appears in a background, possessive or modifier role. "Maxim"
  in "I went to the theatre with Maxim's brother"; "Paris" in "a Paris-based
  photographer".
