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


# --- few-shot demos ---------------------------------------------------------


GOLD = {
    "doc_id": "gold-1",
    "text": "Annie and George Washington visited Mount Vernon.",
    "entities": [
        {"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5},
                                                    {"start": 17, "end": 27}]}]},
        {"type": "LOC", "mentions": [{"start": 36, "end": 48}]},
    ],
}


def test_to_example_builds_a_compact_demo():
    from ner_annotator_llm import to_example

    example = to_example(GOLD["text"], GOLD["entities"])
    assert set(example.inputs().keys()) == {"document"}
    assert example.document == GOLD["text"]
    assert [c.type.value for c in example.entities] == ["PER", "LOC"]
    # The guidelines are already in the prompt; a demo must not repeat them.
    assert "general_guidelines" not in example


def test_to_example_can_carry_the_guidelines_and_reasoning():
    from ner_annotator_llm import to_example

    example = to_example(GOLD["text"], GOLD["entities"],
                         include_guidelines=True, reasoning="Two entities here.")
    assert set(example.inputs().keys()) == {
        "general_guidelines", "entity_guidelines", "document"
    }
    assert example.reasoning == "Two entities here."


def test_examples_from_jsonl_reads_a_corpus(tmp_path):
    import json

    from ner_annotator_llm import examples_from_jsonl

    path = tmp_path / "gold.jsonl"
    path.write_text(
        json.dumps(GOLD, ensure_ascii=False) + "\n"
        + json.dumps({"doc_id": "gold-2", "text": "Nothing here."}) + "\n",
        encoding="utf-8",
    )
    examples = examples_from_jsonl(path)
    assert len(examples) == 1
    assert examples[0].document == GOLD["text"]


def test_demos_reach_the_predictor_and_the_prompt():
    from ner_annotator_llm import to_example

    demo = to_example(GOLD["text"], GOLD["entities"])
    annotator = EntityAnnotator(demos=[demo])

    leaf, = annotator.predict.predictors()
    assert leaf.demos == [demo]

    messages = dspy.ChatAdapter().format(
        AnnotateEntities,
        [demo.toDict()],
        {"general_guidelines": "G", "entity_guidelines": "E", "document": "doc"},
    )
    rendered = "\n".join(m["content"] for m in messages)
    assert GOLD["text"] in rendered
    assert "Annie[…]Washington" in rendered
