"""Per-entity-type annotation guidelines injected into the prompt.

The signature takes the guidelines as an *input field* rather than baking them
into its docstring, so the wording can be tuned (or optimised by DSPy) per
entity type without touching the task definition. ``PER`` is filled in below;
the other canonical types get a placeholder that is meant to be replaced by the
same kind of hand-written text.
"""

from __future__ import annotations

from typing import Dict

PERSON_GUIDELINES = """\
Entity type: PER — an individual human being, real or fictional.

What counts as a PER entity
- One entity per *person*, not per name: every way the text refers to that same
  person belongs to the one entity ("Barack Obama", "Obama", "the president",
  "he").
- Two people who share a name are two entities. One person named two ways
  ("Bibi" / "Netanyahu") is one entity.
- Groups of people are not PER: families, teams, nations, companies and bands
  ("the Obamas", "the Lakers") are out of scope here; so are deities and
  animals unless the text treats them as a named individual person.
- Job titles alone ("the mayor") are mentions only when they refer to a
  specific individual, not to whoever might hold the office.

What counts as a mention
- Names ("Taylor Swift"), partial names ("Swift"), nicknames, and titles used
  referentially ("the president", "the defendant").
- Pronouns that refer to the person ("he", "her", "they", "himself").
- Take the maximal contiguous span that refers to the person: include the given
  name and surname together, but leave out surrounding punctuation, articles
  that are not part of the reference, and appositive descriptions
  ("Barack Obama, the former president" is two mentions, not one span).
- Honorifics and role words that are part of the reference stay in
  ("President Obama", "Dr. Smith").
- Do not annotate the same span twice for the same entity.

relative / implicit
- Mark a mention `relative` when it identifies the person only through a
  relation to someone else and never names them: "the father of Abraham",
  "John's secretary", "her husband".
- Mark a mention `implicit` when it does name the person, but the sentence is
  not about them — they appear in a background or possessive role: "Maxim" in
  "I went to the theatre with Maxim's brother".
- The two are independent: a mention can be neither, either, or both.

Non-continuous mentions
- When one reference to a person is split across the text by words that belong
  to someone else, return the fragments joined by "[…]".
  In "Annie and George Washington visited Mount Vernon", the wife is mentioned
  as "Annie[…]Washington" (and "George Washington" is a separate entity).
- Only use this when the pieces really are one reference; two separate
  mentions of the same person are two entries in `mentions`, not fragments.
"""

_PLACEHOLDER = """\
Entity type: {entity_type}.

No type-specific guidelines have been written yet. Annotate every mention of
each distinct {entity_type} entity in the text, cluster all mentions of the same
referent into one entity, and follow the general rules in the task description.
"""

GUIDELINES: Dict[str, str] = {
    "PER": PERSON_GUIDELINES,
}


def guidelines_for(entity_type: str) -> str:
    """Guidelines for ``entity_type``, or a generic placeholder if unwritten."""
    return GUIDELINES.get(entity_type, _PLACEHOLDER.format(entity_type=entity_type))
