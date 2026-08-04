# TIME — A time expression: date, clock time, period or duration.

## What counts as a TIME entity
- Absolute dates and times ("2010", "March", "14 July 1789", "9:30 am"),
  periods ("the 1990s", "the third quarter"), durations ("two hours") and
  relative expressions ("last night", "next Wednesday", "today").
- One entity per point or span of time referred to: "Wednesday" and "that
  day" referring to the same day are one entity.
- Two expressions that pick out different times are different entities,
  even with identical wording in different sentences.
- Vague temporal adverbs ("later", "soon", "often", "again") are not TIME
  entities.

## What counts as a mention
- Take the whole expression ("on Sunday morning" -> "Sunday morning",
  "in March" -> "March"), leaving out the preposition.
- Include the modifier that is part of the expression ("early 2011",
  "the same evening").

## Flags
- `relative`: the time is identified only through a relation to something
  else — "the day after the vote", "her birthday".
- `implicit`: it is named but in a background or modifier role — "the
  2010 election", "a Monday meeting".
