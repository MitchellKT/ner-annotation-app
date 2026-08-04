# PER — An individual human being, real or fictional.

## What counts as a PER entity
- One entity per *person*, not per name: every way the text refers to that
  same person belongs to the one entity ("Barack Obama", "Obama", "the
  president", "he").
- Two people who share a name are two entities. One person named two ways
  ("Bibi" / "Netanyahu") is one entity.
- Groups of people are not PER: families, teams, nations, companies and
  bands ("the Obamas", "the Lakers") are out of scope; so are deities and
  animals unless the text treats them as a named individual person.

## What counts as a mention
- Names ("Taylor Swift"), partial names ("Swift"), nicknames, and titles
  used referentially ("the president", "the defendant").
- Pronouns that refer to the person ("he", "her", "they", "himself"),
  including possessives ("his", "their").
- Take the maximal contiguous span that refers to the person: keep the
  given name and surname together, but leave out surrounding punctuation
  and appositive descriptions — "Barack Obama, the former president" is
  two mentions, not one span.
- Honorifics and role words that are part of the reference stay in
  ("President Obama", "Dr. Smith").
- A title used to refer to a person ("the mayor") is a PER mention *and*
  usually a JOB_TITLE mention of a separate entity. Annotate both.

## Flags
- `relative`: the person is identified only through someone else — "the
  father of Abraham", "John's secretary", "her husband".
- `implicit`: the person is named but in a background role — "Maxim" in
  "I went to the theatre with Maxim's brother".
