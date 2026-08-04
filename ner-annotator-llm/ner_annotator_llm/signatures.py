"""DSPy signature and module for LLM annotation.

The only module here that needs DSPy (``pip install dspy``); :mod:`.schema`,
:mod:`.guidelines` and :mod:`.grounding` work without it.

Usage::

    import dspy
    from ner_annotator_llm import EntityAnnotator

    dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-5"))
    annotator = EntityAnnotator()
    prediction = annotator(document=text)
    prediction.entities     # entities in the annotation schema, ready to store
    prediction.unresolved   # mentions that could not be grounded

The guidelines are part of the signature's **instructions**, not inputs: the
document is the only thing that varies per call. :func:`annotate_signature`
builds the instructed signature by appending ``general.md`` and every entity
type's file to the task text.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Type

import dspy

from .grounding import Resolution, resolve_entities
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

    The guidelines below say how to report annotations and what each entity type
    covers. Classify each entity as exactly one of the listed types and annotate
    nothing outside them.

    Be exhaustive rather than cautious: a sentence usually holds several
    mentions of the same entity — a name, then a pronoun, then a possessive —
    and every one of them belongs in that sentence's list.
    """

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


def annotate_signature(types: Optional[Iterable[object]] = None) -> Type[dspy.Signature]:
    """:class:`AnnotateEntities` with the guidelines appended to its instructions.

    ``types`` narrows it to a subset of the registered entity types; by default
    every type in ``guidelines/entities/`` is included.
    """
    return AnnotateEntities.with_instructions(
        "\n\n".join(
            [AnnotateEntities.instructions, GENERAL_GUIDELINES, entity_guidelines_block(types)]
        )
    )


class EntityAnnotator(dspy.Module):
    """Predict entities for a document and ground them to character offsets.

    ``forward`` returns a :class:`dspy.Prediction` with:

    ``entities``    entity dicts in the annotation schema (``{"type",
                    "mentions": [{"start", "end"} | {"fragments": [...]}]}``),
                    ready to store;
    ``resolution``  the :class:`~.grounding.Resolution`;
    ``unresolved``  shorthand for ``resolution.unresolved`` — the mentions that
                    could not be placed;
    ``annotation``  the raw quoted prediction (roster + sentences), useful when
                    debugging a drop.

    ``types`` narrows the run to a subset of the registered entity types (their
    guidelines are the only ones in the instructions, and predictions of other
    types are dropped). ``instructions`` replaces the instruction text outright,
    e.g. when plugging in an optimised prompt. ``demos`` are few-shot examples —
    :func:`~.examples.examples_from_jsonl` turns an annotated corpus into them.
    """

    def __init__(
        self,
        types: Optional[Iterable[object]] = None,
        instructions: Optional[str] = None,
        demos: Optional[Iterable[Any]] = None,
        predictor: Optional[dspy.Module] = None,
    ) -> None:
        super().__init__()
        self.types = None if types is None else [str(getattr(t, "value", t)) for t in types]
        signature = annotate_signature(self.types)
        if instructions is not None:
            signature = signature.with_instructions(instructions)
        self.signature = signature
        self.predict = predictor or dspy.ChainOfThought(signature)
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
        prediction = self.predict(document=document)
        annotation = Annotation(
            entities=prediction.entities or [],
            sentences=prediction.sentences or [],
        )
        resolution: Resolution = resolve_entities(document, annotation)
        if self.types is not None:
            resolution.entities = [e for e in resolution.entities if e.type in self.types]
        return dspy.Prediction(
            entities=resolution.to_json(),
            resolution=resolution,
            unresolved=resolution.unresolved,
            annotation=annotation,
        )
