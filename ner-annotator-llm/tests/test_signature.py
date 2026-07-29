"""Signature-level tests; skipped when the optional ``dspy`` extra is absent."""

import typing

import pytest

dspy = pytest.importorskip("dspy")

from ner_annotator_llm import AnnotateEntities, EntityAnnotator, EntityType  # noqa: E402
from ner_annotator_llm.schema import (  # noqa: E402
    EntityCandidate,
    MentionCandidate,
    SentenceMentions,
)

TEXT = "Annie and George Washington visited Mount Vernon. Annie waved."
FIRST = "Annie and George Washington visited Mount Vernon."


class StubPredictor(dspy.Module):
    """Stands in for the LM: records the inputs, returns a canned prediction."""

    def __init__(self, entities):
        super().__init__()
        self.entities = entities
        self.seen = None

    def __call__(self, **kwargs):
        self.seen = kwargs
        return dspy.Prediction(entities=self.entities)


def test_signature_fields():
    assert list(AnnotateEntities.input_fields) == [
        "general_guidelines",
        "entity_guidelines",
        "document",
    ]
    assert list(AnnotateEntities.output_fields) == ["entities"]
    annotation = AnnotateEntities.output_fields["entities"].annotation
    assert typing.get_origin(annotation) is list
    assert typing.get_args(annotation) == (EntityCandidate,)


def test_the_prompt_carries_every_type_key_and_description():
    stub = StubPredictor([])
    EntityAnnotator(predictor=stub)(document=TEXT)

    block = stub.seen["entity_guidelines"]
    for member in EntityType:
        assert f"# {member.value} —" in block
    assert "## Group mentions by sentence" in stub.seen["general_guidelines"]
    assert stub.seen["document"] == TEXT


def test_one_pass_annotates_several_types():
    stub = StubPredictor([
        EntityCandidate(name="Annie Washington", type="PER", sentences=[
            SentenceMentions(sentence=FIRST, mentions=[
                MentionCandidate(text="Annie[…]Washington")]),
            SentenceMentions(sentence="Annie waved.", mentions=[MentionCandidate(text="Annie")]),
        ]),
        EntityCandidate(name="Mount Vernon", type="LOC", sentences=[
            SentenceMentions(sentence=FIRST, mentions=[MentionCandidate(text="Mount Vernon")]),
        ]),
    ])
    prediction = EntityAnnotator(predictor=stub)(document=TEXT)

    assert prediction.entities == [
        {"type": "PER", "mentions": [
            {"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]},
            {"start": 50, "end": 55},
        ]},
        {"type": "LOC", "mentions": [{"start": 36, "end": 48}]},
    ]
    assert prediction.problems == []


def test_annotator_accepts_raw_dicts():
    stub = StubPredictor([
        {"name": "George Washington", "type": "PER", "sentences": [
            {"sentence": FIRST, "mentions": [{"text": "George Washington"}]}]},
    ])
    prediction = EntityAnnotator(predictor=stub)(document=TEXT)
    assert prediction.entities == [{"type": "PER", "mentions": [{"start": 10, "end": 27}]}]


def test_types_narrows_the_prompt_and_the_output():
    stub = StubPredictor([
        EntityCandidate(name="Mount Vernon", type="LOC", sentences=[
            SentenceMentions(sentence=FIRST, mentions=[MentionCandidate(text="Mount Vernon")])]),
        EntityCandidate(name="Annie", type="PER", sentences=[
            SentenceMentions(sentence="Annie waved.", mentions=[MentionCandidate(text="Annie")])]),
    ])
    prediction = EntityAnnotator(types=["PER"], predictor=stub)(document=TEXT)

    assert "# PER —" in stub.seen["entity_guidelines"]
    assert "# LOC —" not in stub.seen["entity_guidelines"]
    # An out-of-scope entity the model returned anyway is dropped.
    assert prediction.entities == [{"type": "PER", "mentions": [{"start": 50, "end": 55}]}]


def test_custom_guidelines_win():
    stub = StubPredictor([])
    EntityAnnotator(
        general_guidelines="be brief",
        entity_guidelines="only capitals",
        predictor=stub,
    )(document=TEXT)
    assert stub.seen["general_guidelines"] == "be brief"
    assert stub.seen["entity_guidelines"] == "only capitals"
