"""Signature-level tests; skipped when the optional ``llm`` extra is absent."""

import typing

import pytest

dspy = pytest.importorskip("dspy")

from ner_annotator_llm import AnnotateEntities, EntityAnnotator  # noqa: E402
from ner_annotator_llm.schema import EntityCandidate, MentionCandidate  # noqa: E402

TEXT = "Annie and George Washington visited Mount Vernon. Annie waved."


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
    assert list(AnnotateEntities.input_fields) == ["guidelines", "entity_type", "document"]
    assert list(AnnotateEntities.output_fields) == ["entities"]
    annotation = AnnotateEntities.output_fields["entities"].annotation
    assert typing.get_origin(annotation) is list
    assert typing.get_args(annotation) == (EntityCandidate,)


def test_annotator_passes_guidelines_and_grounds_the_prediction():
    stub = StubPredictor([
        EntityCandidate(name="Annie Washington", type="PER", mentions=[
            MentionCandidate(mention="Annie[…]Washington", sentence=TEXT.split(". ")[0] + "."),
            MentionCandidate(mention="Annie", sentence="Annie waved."),
        ]),
    ])
    annotator = EntityAnnotator(entity_type="PER", predictor=stub)
    prediction = annotator(document=TEXT)

    assert stub.seen["entity_type"] == "PER"
    assert "Entity type: PER" in stub.seen["guidelines"]
    assert prediction.entities == [
        {"type": "PER", "mentions": [
            {"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]},
            {"start": 50, "end": 55},
        ]},
    ]
    assert prediction.problems == []


def test_annotator_accepts_raw_dicts_and_fills_the_type():
    stub = StubPredictor([
        {"name": "George Washington", "mentions": [
            {"mention": "George Washington", "sentence": TEXT.split(". ")[0] + "."}]},
    ])
    prediction = EntityAnnotator(entity_type="PER", predictor=stub)(document=TEXT)
    assert prediction.entities == [{"type": "PER", "mentions": [{"start": 10, "end": 27}]}]


def test_custom_guidelines_win():
    stub = StubPredictor([])
    EntityAnnotator(entity_type="LOC", guidelines="only capitals", predictor=stub)(document=TEXT)
    assert stub.seen["guidelines"] == "only capitals"
