"""Signature-level tests; skipped when the optional ``dspy`` extra is absent."""

import typing

import pytest

dspy = pytest.importorskip("dspy")

from ner_annotator_llm import (  # noqa: E402
    AnnotateEntities,
    EntityAnnotator,
    EntityType,
    annotate_signature,
)
from ner_annotator_llm.schema import (  # noqa: E402
    EntityCandidate,
    MentionCandidate,
    SentenceMentions,
)

TEXT = "Annie and George Washington visited Mount Vernon. Annie waved."
FIRST = "Annie and George Washington visited Mount Vernon."


class StubPredictor(dspy.Module):
    """Stands in for the LM: records the inputs, returns a canned prediction."""

    def __init__(self, entities=(), sentences=()):
        super().__init__()
        self.entities = list(entities)
        self.sentences = list(sentences)
        self.seen = None

    def __call__(self, **kwargs):
        self.seen = kwargs
        return dspy.Prediction(entities=self.entities, sentences=self.sentences)


def test_signature_fields():
    # The document is the only input; the guidelines are instructions.
    assert list(AnnotateEntities.input_fields) == ["document"]
    # The roster is settled before the sentences that refer back to it.
    assert list(AnnotateEntities.output_fields) == ["entities", "sentences"]
    roster = AnnotateEntities.output_fields["entities"].annotation
    grouped = AnnotateEntities.output_fields["sentences"].annotation
    assert typing.get_args(roster) == (EntityCandidate,)
    assert typing.get_args(grouped) == (SentenceMentions,)


def test_the_guidelines_are_instructions_not_inputs():
    instructions = annotate_signature().instructions
    assert AnnotateEntities.instructions in instructions
    assert "## Part 1 — the entity list" in instructions      # general.md
    for member in EntityType:
        assert f"# {member.value} —" in instructions          # entities/*.md
    assert list(annotate_signature().input_fields) == ["document"]


def test_the_annotator_passes_only_the_document():
    stub = StubPredictor()
    EntityAnnotator(predictor=stub)(document=TEXT)
    assert stub.seen == {"document": TEXT}


def test_one_pass_annotates_several_types_from_one_roster():
    stub = StubPredictor(
        entities=[
            EntityCandidate(name="Annie Washington", type="PER"),
            EntityCandidate(name="Mount Vernon", type="LOC"),
        ],
        sentences=[
            SentenceMentions(sentence=FIRST, mentions=[
                MentionCandidate(entity="Annie Washington", text="Annie[…]Washington"),
                MentionCandidate(entity="Mount Vernon", text="Mount Vernon"),
            ]),
            SentenceMentions(sentence="Annie waved.", mentions=[
                MentionCandidate(entity="Annie Washington", text="Annie"),
            ]),
        ],
    )
    prediction = EntityAnnotator(predictor=stub)(document=TEXT)

    assert prediction.entities == [
        {"type": "PER", "mentions": [
            {"fragments": [{"start": 0, "end": 5}, {"start": 17, "end": 27}]},
            {"start": 50, "end": 55},
        ]},
        {"type": "LOC", "mentions": [{"start": 36, "end": 48}]},
    ]
    assert prediction.unresolved == []
    assert prediction.annotation.entities == stub.entities


def test_annotator_accepts_raw_dicts():
    stub = StubPredictor(
        entities=[{"name": "George Washington", "type": "PER"}],
        sentences=[{"sentence": FIRST,
                    "mentions": [{"entity": "George Washington",
                                  "text": "George Washington"}]}],
    )
    prediction = EntityAnnotator(predictor=stub)(document=TEXT)
    assert prediction.entities == [{"type": "PER", "mentions": [{"start": 10, "end": 27}]}]


def test_types_narrows_the_prompt_and_the_output():
    stub = StubPredictor(
        entities=[
            EntityCandidate(name="Mount Vernon", type="LOC"),
            EntityCandidate(name="Annie", type="PER"),
        ],
        sentences=[
            SentenceMentions(sentence=FIRST, mentions=[
                MentionCandidate(entity="Mount Vernon", text="Mount Vernon")]),
            SentenceMentions(sentence="Annie waved.", mentions=[
                MentionCandidate(entity="Annie", text="Annie")]),
        ],
    )
    annotator = EntityAnnotator(types=["PER"], predictor=stub)
    prediction = annotator(document=TEXT)

    assert "# PER —" in annotator.signature.instructions
    assert "# LOC —" not in annotator.signature.instructions
    # An out-of-scope entity the model returned anyway is dropped.
    assert prediction.entities == [{"type": "PER", "mentions": [{"start": 50, "end": 55}]}]


def test_custom_instructions_win():
    annotator = EntityAnnotator(instructions="be brief", predictor=StubPredictor())
    assert annotator.signature.instructions == "be brief"


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
    assert [(e.name, e.type.value) for e in example.entities] == [
        ("Annie[…]Washington", "PER"), ("Mount Vernon", "LOC")
    ]
    assert [m.entity for g in example.sentences for m in g.mentions] == [
        "Annie[…]Washington", "Mount Vernon"
    ]


def test_to_example_can_carry_the_reasoning():
    from ner_annotator_llm import to_example

    example = to_example(GOLD["text"], GOLD["entities"], reasoning="Two entities here.")
    assert set(example.inputs().keys()) == {"document"}
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
        annotate_signature(), [demo.toDict()], {"document": "doc"}
    )
    answer, = [m["content"] for m in messages if m["role"] == "assistant"]
    assert "Annie[…]Washington" in answer
    # The sentence is quoted once in the demo, whatever it mentions.
    assert answer.count(GOLD["text"]) == 1
