"""DSPy signature and module for LLM annotation.

The only module here that needs DSPy (``pip install dspy``); :mod:`.schema`,
:mod:`.guidelines` and :mod:`.grounding` work without it.

Usage::

    import dspy
    from ner_annotator_llm import EntityAnnotator

    dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-5"))
    annotator = EntityAnnotator()
    prediction = annotator(document=text)
    prediction.entities   # entities in the annotation schema, ready to store
    prediction.problems   # mentions that could not be grounded

One signature covers **every** entity type: the type set, each type's one-line
description and each type's full rules all come from
``guidelines/entities.json`` and are rendered into an input field, and the
predicted ``type`` is an :data:`~.guidelines.EntityType` member — so a new type
is a JSON edit, not a code change or a second pass over the document.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

import dspy

from .grounding import Resolution, resolve_entities, unicode_safe
from .guidelines import GENERAL_GUIDELINES, entity_guidelines_block
from .schema import Annotation, EntityCandidate, SentenceMentions


class AnnotateEntities(dspy.Signature):
    """Find every entity in the document and every mention of each one.

    Answer in two parts. First `entities`: one entry per distinct referent in
    the document, each under a unique `name`. Then `sentences`: every sentence
    that contains at least one mention, quoted verbatim once, holding every
    mention in it tagged with the `entity` it refers to. A sentence is written
    once for the whole document, however many entities it mentions, and every
    entity a mention names must be one you declared.

    Follow `general_guidelines` for *how* to report annotations — clustering,
    quoting, the two flags. Follow `entity_guidelines` for *what* to annotate:
    it lists the entity types, one line each, then the full rules per type.
    Classify each entity as exactly one of those types and annotate nothing
    outside them.

    Be exhaustive rather than cautious: a sentence usually holds several
    mentions of the same entity — a name, then a pronoun, then a possessive —
    and every one of them belongs in that sentence's list.
    """

    general_guidelines: str = dspy.InputField(
        desc="How to report annotations. Applies to every entity type."
    )
    entity_guidelines: str = dspy.InputField(
        desc="The entity types to annotate — key, description and full rules for each."
    )
    document: str = dspy.InputField(desc="The full document text, verbatim.")
    entities: List[EntityCandidate] = dspy.OutputField(
        desc=(
            "The distinct entities in the document, of any of the listed types, "
            "each under a unique name the mentions refer back to."
        )
    )
    sentences: List[SentenceMentions] = dspy.OutputField(
        desc=(
            "Each sentence containing mentions, quoted once, with every mention "
            "in it and the name of the entity it refers to."
        )
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
    ``annotation``  the raw quoted prediction (roster + sentences), useful when
                    debugging a drop.

    ``types`` narrows the run to a subset of the registered entity types (their
    guidelines are the only ones shown, and predictions of other types are
    dropped); by default every type in ``guidelines/entities.json`` is in scope.
    ``general_guidelines`` / ``entity_guidelines`` override the rendered text
    outright, e.g. when tuning wording or plugging in an optimised prompt.
    ``demos`` are few-shot examples — :func:`~.examples.examples_from_jsonl`
    turns an annotated corpus into them.
    """

    def __init__(
        self,
        types: Optional[Iterable[object]] = None,
        general_guidelines: Optional[str] = None,
        entity_guidelines: Optional[str] = None,
        demos: Optional[Iterable[Any]] = None,
        predictor: Optional[dspy.Module] = None,
    ) -> None:
        super().__init__()
        self.types = None if types is None else [str(getattr(t, "value", t)) for t in types]
        self.general_guidelines = (
            GENERAL_GUIDELINES if general_guidelines is None else general_guidelines
        )
        self.entity_guidelines = (
            entity_guidelines_block(self.types) if entity_guidelines is None else entity_guidelines
        )
        self.predict = predictor or dspy.ChainOfThought(AnnotateEntities)
        if demos is not None:
            self.set_demos(demos)

    def set_demos(self, demos: Iterable[Any]) -> None:
        """Attach few-shot examples, replacing any already set.

        Demos live on the leaf ``Predict``, not on the wrapper, so they are set
        through ``predictors()`` — a ``ChainOfThought`` keeps its own inside.
        """
        demos = list(demos)
        for predictor in self.predict.predictors():
            predictor.demos = demos

    def forward(self, document: str) -> dspy.Prediction:
        # The offsets are computed against exactly the string the model saw, so
        # normalise once and use the same text for both.
        text = unicode_safe(document)
        prediction = self.predict(
            general_guidelines=self.general_guidelines,
            entity_guidelines=self.entity_guidelines,
            document=text,
        )
        annotation = Annotation(
            entities=prediction.entities or [],
            sentences=prediction.sentences or [],
        )
        resolution: Resolution = resolve_entities(text, annotation)
        if self.types is not None:
            resolution.entities = [e for e in resolution.entities if e.type in self.types]
        return dspy.Prediction(
            entities=resolution.to_json(),
            resolution=resolution,
            problems=resolution.problems,
            annotation=annotation,
            text=text,
        )
