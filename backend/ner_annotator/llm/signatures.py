"""DSPy signature and module for LLM annotation.

The only module here that needs DSPy (``pip install dspy``); :mod:`.schema`,
:mod:`.guidelines` and :mod:`.grounding` work without it.

Usage::

    import dspy
    from ner_annotator.llm import EntityAnnotator

    dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-5"))
    annotator = EntityAnnotator(entity_type="PER")
    prediction = annotator(document=text)
    prediction.entities   # entities in the annotation schema, ready to store
    prediction.problems   # mentions that could not be grounded

The signature is deliberately type-agnostic: the entity type and its guidelines
are *inputs*, so the same task can be run for ``LOC`` / ``ORG`` / ``TIME`` (and
the guidelines can be tuned, or optimised by DSPy, without touching the task).
"""

from __future__ import annotations

from typing import List, Optional

import dspy

from .grounding import Resolution, resolve_entities, unicode_safe
from .guidelines import guidelines_for
from .schema import EntityCandidate


class AnnotateEntities(dspy.Signature):
    """Annotate every mention of the given entity type in a document.

    The output is an entity-clustering annotation: an *entity* is one real-world
    referent, and its `mentions` are all the places in the text that refer to
    it. Two mentions of the same referent must end up in the same entity, and
    two distinct referents must never be merged — even when they share a name.

    Mentions are quoted, never described:

    - `mention` is the exact substring of the document that refers to the
      entity, copied character for character (same spelling, case, punctuation
      and diacritics). Never paraphrase, translate or normalise it.
    - `sentence` is the full sentence containing that mention, also copied
      verbatim. It is what locates the mention in the document, so when the same
      surface form occurs several times, give the sentence of the occurrence you
      mean, and list repeated mentions in the order they appear in the text.
    - A mention split across the text by intervening words that belong to
      something else is written as its fragments joined by `[…]` — e.g.
      `Annie[…]Washington` in "Annie and George Washington visited Mount
      Vernon". Use it only for one reference cut in two, never to join two
      separate mentions.

    Mentions may overlap or nest (a shorter mention of one entity inside a
    longer mention of another is fine). Annotate only what the text actually
    says; do not add entities that are merely implied by world knowledge, and
    return an empty list when the document contains none.
    """

    guidelines: str = dspy.InputField(
        desc="Annotation guidelines for this entity type: what counts as an "
             "entity, what counts as a mention, and how to flag them."
    )
    entity_type: str = dspy.InputField(desc="The entity type to annotate, e.g. 'PER'.")
    document: str = dspy.InputField(desc="The full document text, verbatim.")
    entities: List[EntityCandidate] = dspy.OutputField(
        desc="One item per distinct entity of this type, each with all of its mentions."
    )


class EntityAnnotator(dspy.Module):
    """Predict entities for a document and ground them to character offsets.

    ``forward`` returns a :class:`dspy.Prediction` with:

    ``entities``    entity dicts in the annotation schema (``{"type",
                    "mentions": [{"start", "end"} | {"fragments": [...]}]}``),
                    ready to store;
    ``resolution``  the :class:`~.grounding.Resolution` (entity objects plus
                    per-mention problems);
    ``problems``    shorthand for ``resolution.problems``;
    ``candidates``  the raw quoted prediction, useful when debugging a drop.
    """

    def __init__(
        self,
        entity_type: str = "PER",
        guidelines: Optional[str] = None,
        predictor: Optional[dspy.Module] = None,
    ) -> None:
        super().__init__()
        self.entity_type = entity_type
        self.guidelines = guidelines if guidelines is not None else guidelines_for(entity_type)
        self.predict = predictor or dspy.ChainOfThought(AnnotateEntities)

    def forward(self, document: str) -> dspy.Prediction:
        # The offsets are computed against exactly the string the model saw, so
        # normalise once and use the same text for both.
        text = unicode_safe(document)
        prediction = self.predict(
            guidelines=self.guidelines,
            entity_type=self.entity_type,
            document=text,
        )
        candidates = prediction.entities or []
        resolution: Resolution = resolve_entities(
            text, candidates, default_type=self.entity_type
        )
        return dspy.Prediction(
            entities=resolution.to_json(),
            resolution=resolution,
            problems=resolution.problems,
            candidates=candidates,
            text=text,
        )
