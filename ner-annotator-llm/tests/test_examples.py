import json

import pytest
from pydantic import ValidationError

from ner_annotator_llm.examples import (
    examples_from_records,
    sentence_spans,
    to_annotation,
)
from ner_annotator_llm.grounding import entities_to_json, resolve_entities

# Annotated documents in the character-level schema, of the shape a corpus (or
# the annotator's own output) holds. Every one of them round-trips.
DOCS = [
    {
        "text": "Barack Obama was born in Hawaii. Obama later moved to Chicago, "
                "where he worked for the City Council.",
        "entities": [
            {"type": "PER", "mentions": [{"start": 0, "end": 12}, {"start": 7, "end": 12},
                                         {"start": 33, "end": 38}, {"start": 69, "end": 71}]},
            {"type": "LOC", "mentions": [{"start": 25, "end": 31}, {"start": 54, "end": 61}]},
            {"type": "ORG", "mentions": [{"start": 87, "end": 99}]},
        ],
    },
    {
        "text": "Annie and George Washington visited Mount Vernon.",
        "entities": [
            {"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5},
                                                        {"start": 17, "end": 27}]}]},
            {"type": "PER", "mentions": [{"start": 10, "end": 27}]},
            {"type": "LOC", "mentions": [{"start": 36, "end": 48}]},
        ],
    },
    {
        "text": "She joined the Bank of America board in 2010 before leaving America.",
        "entities": [
            {"type": "ORG", "mentions": [{"start": 15, "end": 30}]},
            {"type": "LOC", "mentions": [{"start": 23, "end": 30, "implicit": True},
                                         {"start": 60, "end": 67}]},
            {"type": "TIME", "mentions": [{"start": 40, "end": 44}]},
        ],
    },
    {
        "text": "Alice met Bob in Paris on Monday, then Alice flew home.",
        "entities": [
            {"type": "PER", "mentions": [{"start": 0, "end": 5}, {"start": 39, "end": 44}]},
            {"type": "PER", "mentions": [{"start": 10, "end": 13}]},
            {"type": "LOC", "mentions": [{"start": 17, "end": 22}]},
            {"type": "TIME", "mentions": [{"start": 26, "end": 32}]},
        ],
    },
    {
        "text": "🚀 Elon flew to Berlin 😀 with SpaceX in March.",
        "entities": [
            {"type": "PER", "mentions": [{"start": 2, "end": 6}]},
            {"type": "LOC", "mentions": [{"start": 15, "end": 21}]},
            {"type": "ORG", "mentions": [{"start": 29, "end": 35}]},
            {"type": "TIME", "mentions": [{"start": 39, "end": 44}]},
        ],
    },
    {
        "text": "דוד הלך לירושלים. הוא פגש שם את שרה.",
        "entities": [
            {"type": "PER", "mentions": [{"start": 0, "end": 3}, {"start": 18, "end": 21}]},
            {"type": "PER", "mentions": [{"start": 32, "end": 35}]},
            {"type": "LOC", "mentions": [{"start": 9, "end": 16, "implicit": True}]},
        ],
    },
    {
        "text": "The mayor of London opened the bridge.\nThe mayor left early.",
        "entities": [
            {"type": "JOB_TITLE", "mentions": [{"start": 4, "end": 9},
                                               {"start": 43, "end": 48}]},
            {"type": "PER", "mentions": [{"start": 0, "end": 19, "relative": True},
                                         {"start": 39, "end": 48, "relative": True}]},
            {"type": "LOC", "mentions": [{"start": 13, "end": 19, "implicit": True}]},
        ],
    },
]


# --- sentence segmentation --------------------------------------------------


def test_splits_on_terminators_and_trims_whitespace():
    text = "One thing.  Then another!  And a third?"
    assert [text[s:e] for s, e in sentence_spans(text)] == [
        "One thing.", "Then another!", "And a third?"
    ]


def test_splits_on_line_breaks():
    text = "A headline\nand the body."
    assert [text[s:e] for s, e in sentence_spans(text)] == ["A headline", "and the body."]


def test_an_abbreviation_ends_a_sentence_early():
    # No abbreviation list: a shorter quoted sentence, which is all this decides.
    text = "Dr. Smith arrived."
    assert [text[s:e] for s, e in sentence_spans(text)] == ["Dr.", "Smith arrived."]


def test_text_without_a_terminator_is_one_sentence():
    assert [t for t in sentence_spans("just a fragment")] == [(0, 15)]


def test_empty_text_has_no_sentences():
    assert sentence_spans("   \n  ") == []


# --- conversion -------------------------------------------------------------


def test_entities_are_declared_once_under_their_longest_mention():
    doc = DOCS[0]
    annotation = to_annotation(doc["text"], doc["entities"])
    assert [(e.name, e.type.value) for e in annotation.entities] == [
        ("Barack Obama", "PER"),
        ("Chicago", "LOC"),
        ("City Council", "ORG"),
    ]


def test_entities_that_would_share_a_name_are_told_apart():
    text = "Washington met Washington."
    entities = [{"type": "PER", "mentions": [{"start": 0, "end": 10}]},
                {"type": "PER", "mentions": [{"start": 15, "end": 25}]}]
    annotation = to_annotation(text, entities)
    assert [e.name for e in annotation.entities] == ["Washington", "Washington (2)"]
    assert [m.entity for g in annotation.sentences for m in g.mentions] == [
        "Washington", "Washington (2)"
    ]
    # And the disambiguated names still round-trip.
    assert entities_to_json(resolve_entities(text, annotation).entities) == entities


def test_each_sentence_appears_once_carrying_every_entity_in_it():
    doc = DOCS[0]
    annotation = to_annotation(doc["text"], doc["entities"])
    assert [(g.sentence, [(m.entity, m.text) for m in g.mentions])
            for g in annotation.sentences] == [
        ("Barack Obama was born in Hawaii.",
         [("Barack Obama", "Barack Obama"), ("Barack Obama", "Obama"), ("Chicago", "Hawaii")]),
        ("Obama later moved to Chicago, where he worked for the City Council.",
         [("Barack Obama", "Obama"), ("Chicago", "Chicago"),
          ("Barack Obama", "he"), ("City Council", "City Council")]),
    ]


def test_split_mentions_use_the_fragment_separator():
    doc = DOCS[1]
    annotation = to_annotation(doc["text"], doc["entities"])
    group, = annotation.sentences
    assert [(m.entity, m.text) for m in group.mentions] == [
        ("Annie[…]Washington", "Annie[…]Washington"),
        ("George Washington", "George Washington"),
        ("Mount Vernon", "Mount Vernon"),
    ]
    assert annotation.entities[0].name == "Annie[…]Washington"


def test_flags_are_carried_over():
    doc = DOCS[2]
    annotation = to_annotation(doc["text"], doc["entities"])
    group, = annotation.sentences
    nested, plain = [m for m in group.mentions if m.text == "America"]
    assert (nested.implicit, nested.relative) == (True, False)
    assert plain.implicit is False


def test_a_mention_crossing_a_sentence_boundary_keeps_both_halves():
    text = "Ann arrived. Washington waited."
    entities = [{"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 3},
                                                            {"start": 13, "end": 23}]}]}]
    group, = to_annotation(text, entities).sentences
    assert group.sentence == text
    assert [m.text for m in group.mentions] == ["Ann[…]Washington"]


def test_entities_may_be_given_as_objects_or_json():
    from ner_annotator_llm.grounding import entities_from_json

    doc = DOCS[3]
    from_json = to_annotation(doc["text"], doc["entities"])
    from_objects = to_annotation(doc["text"], entities_from_json(doc["entities"]))
    assert from_json == from_objects


def test_a_type_with_no_guidelines_file_cannot_be_represented():
    text = "Alice met Bob."
    entities = [{"type": "MISC", "mentions": [{"start": 0, "end": 5}]}]
    with pytest.raises(ValidationError):
        to_annotation(text, entities)


def test_entities_without_mentions_are_dropped():
    empty = to_annotation("Alice met Bob.", [{"type": "PER", "mentions": []}])
    assert (empty.entities, empty.sentences) == ([], [])


# --- the round trip ---------------------------------------------------------


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d["text"][:24])
def test_round_trip_reproduces_the_original_offsets(doc):
    annotation = to_annotation(doc["text"], doc["entities"])
    resolution = resolve_entities(doc["text"], annotation)
    assert entities_to_json(resolution.entities) == doc["entities"]
    assert resolution.unresolved == []


def test_round_trip_survives_a_json_encode_decode():
    # What a demo actually goes through when the adapter serialises it.
    doc = DOCS[0]
    annotation = to_annotation(doc["text"], doc["entities"])
    payload = json.loads(annotation.model_dump_json())
    resolution = resolve_entities(doc["text"], payload)
    assert entities_to_json(resolution.entities) == doc["entities"]


# --- example records --------------------------------------------------------


def test_records_without_entities_are_skipped():
    pytest.importorskip("dspy")
    records = [DOCS[0], {"text": "Nothing here.", "entities": []}, {"text": "Nor here."}]
    assert len(examples_from_records(records)) == 1
