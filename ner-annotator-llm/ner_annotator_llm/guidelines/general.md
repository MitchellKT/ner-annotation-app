# General annotation guidelines

These rules hold for every entity type. The type-specific guidelines say *what*
to annotate; this file says *how* to report it.

## Entities and mentions

- An **entity** is one real-world referent. Its **mentions** are every place in
  the text that refers to it.
- All mentions of the same referent belong to **one** entity: "Barack Obama",
  "Obama", "the president" and "he" are four mentions of one entity, not four
  entities.
- Two referents are never merged, even when they share a surface form. Two
  different people called "Smith" are two entities; one company and the city it
  is named after are two entities.
- Give each entity a short `name` — any readable label for the referent. It is
  a bookkeeping aid, not part of the annotation.
- Annotate only what the text actually says. Do not add entities that are merely
  implied by world knowledge, and do not resolve a reference the text leaves
  open. If the document contains no entity of any known type, return an empty
  list.
- Mentions may **overlap or nest**, including across types: "America" (a place)
  inside "Bank of America" (an organisation), or a job title inside a longer
  reference to the person holding it. Annotate both.

## How to quote a mention

You are not asked for character positions — you quote text, and the surrounding
code locates it. Quote precisely:

- `text` is the mention **exactly as it appears in the document**, copied
  character for character: same spelling, case, punctuation and diacritics.
  Never paraphrase, translate, expand an abbreviation or normalise anything.
- `sentence` is the **full sentence containing the mentions**, also copied
  verbatim. It is what pins them to one place in the document, so when the same
  wording occurs more than once, quote the sentence of the occurrence you mean.

## Group mentions by sentence

For each entity, report **one entry per sentence** that contains mentions of it,
holding **every** mention of that entity in that sentence, in the order they
appear. Quote the sentence once, no matter how many mentions it holds.

> "Obama said that he and his wife had left Chicago, where Obama grew up."

is a single entry for the Obama entity, whose mentions are `"Obama"`, `"he"`,
`"his"` and `"Obama"` — four entries, in that order, sharing one quoted
sentence. Repeated wording is not deduplicated: if the same word refers to the
entity three times in the sentence, list it three times, and the occurrences are
matched left to right.

Do not split one sentence across several entries for the same entity, and do not
merge two sentences into one entry.

## Non-continuous mentions

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
