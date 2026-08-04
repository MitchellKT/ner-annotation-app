# JOB_TITLE — A role, post or professional position someone can hold.

## What counts as a JOB_TITLE entity
- The *position*, not the person filling it: "mayor", "chief executive",
  "senior software engineer", "minister of defence", "goalkeeper".
- Every mention of the same post in the document is one entity. Two
  different posts are two entities, even at the same organisation.
- The same span is very often also a PER mention ("the mayor opened the
  bridge") — that overlap is expected, annotate both.

## What counts as a mention
- Include the qualifier that is part of the title: "deputy prime
  minister", "acting chief of staff", "head of research".
- Include the organisation or scope only when it is part of the title
  itself ("minister of defence"), not when it is separate context
  ("the chief executive of Acme" -> the title is "chief executive").
- Honorific-only forms of address ("Mr", "Dr" as a courtesy title) are
  not job titles; "Dr" is one only where the text means the profession.
- Academic degrees, ranks and awards are not job titles unless the text
  uses them as the person's post (military ranks like "colonel" count).

## Flags
- `relative`: the post is identified only through a relation — "her
  predecessor's job", "the role he took over".
- `implicit`: the title appears as background, typically modifying
  something else — "a mayoral aide", "the CEO's driver".
