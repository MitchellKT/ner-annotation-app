import pytest

from ner_annotator_llm.grounding import (
    DUPLICATE_MENTION,
    EMPTY_MENTION,
    INVALID_CANDIDATE,
    MENTION_NOT_FOUND,
    MENTION_OUTSIDE_SENTENCE,
    SENTENCE_NOT_FOUND,
    entities_to_json,
    resolve_entities,
)
from ner_annotator_llm.schema import (
    EntityCandidate,
    MentionCandidate,
    SentenceMentions,
    split_fragments,
)


def entity(*mentions, name="e", type="PER"):
    """Build a candidate from (mention, sentence[, flags]) tuples.

    Consecutive tuples quoting the same sentence become one sentence group, so
    the tests read like the model's answer: mention, mention, mention, all under
    one quotation.
    """
    groups = []
    for m in mentions:
        text, sentence = m[0], m[1]
        flags = m[2] if len(m) > 2 else {}
        if not groups or groups[-1].sentence != sentence:
            groups.append(SentenceMentions(sentence=sentence, mentions=[]))
        groups[-1].mentions.append(MentionCandidate(text=text, **flags))
    return EntityCandidate(name=name, type=type, sentences=groups)


def spans(resolution):
    return [
        [[(f.start, f.end) for f in m.fragments] for m in e.mentions]
        for e in resolution.entities
    ]


# --- fragment parsing -------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Barack Obama", ["Barack Obama"]),
        ("Annie[…]Washington", ["Annie", "Washington"]),
        ("Annie[...]Washington", ["Annie", "Washington"]),
        ("Annie [ ... ] Washington", ["Annie", "Washington"]),
        ("Annie … Washington", ["Annie", "Washington"]),
        ("a[…]b[…]c", ["a", "b", "c"]),
        ("[…]Washington", ["Washington"]),
        ("   ", []),
    ],
)
def test_split_fragments(raw, expected):
    assert split_fragments(raw) == expected


# --- basic grounding --------------------------------------------------------


def test_continuous_mentions_get_character_offsets():
    text = "Barack Obama was born in Hawaii. Obama later moved to Chicago."
    res = resolve_entities(
        text,
        [entity(
            ("Barack Obama", "Barack Obama was born in Hawaii."),
            ("Obama", "Obama later moved to Chicago."),
        )],
    )
    assert spans(res) == [[[(0, 12)], [(33, 38)]]]
    assert res.problems == []
    assert text[33:38] == "Obama"


def test_output_matches_the_annotation_schema():
    text = "Annie and George Washington visited Mount Vernon."
    res = resolve_entities(
        text,
        [
            entity(("Annie[…]Washington", text), name="Annie Washington"),
            entity(("George Washington", text), name="George Washington"),
        ],
    )
    assert entities_to_json(res.entities) == [
        {"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5},
                                                    {"start": 17, "end": 27}]}]},
        {"type": "PER", "mentions": [{"start": 10, "end": 27}]},
    ]


def test_entity_type_comes_from_the_registry():
    text = "The mayor of London opened the bridge."
    res = resolve_entities(
        text,
        [
            entity(("mayor", text), name="the mayor", type="JOB_TITLE"),
            entity(("London", text), name="London", type="LOC"),
        ],
    )
    assert [e.type for e in res.entities] == ["JOB_TITLE", "LOC"]
    assert entities_to_json(res.entities)[0] == {
        "type": "JOB_TITLE", "mentions": [{"start": 4, "end": 9}]
    }


def test_flags_ride_through():
    text = "I went to the theatre with Maxim's brother."
    res = resolve_entities(
        text,
        [
            entity(("Maxim", text, {"implicit": True}), name="Maxim"),
            entity(("Maxim's brother", text, {"relative": True}), name="the brother"),
        ],
    )
    assert entities_to_json(res.entities) == [
        {"type": "PER", "mentions": [{"start": 27, "end": 32, "implicit": True}]},
        {"type": "PER", "mentions": [{"start": 27, "end": 42, "relative": True}]},
    ]


# --- many mentions in one sentence ------------------------------------------


def test_all_mentions_in_one_sentence_resolve_left_to_right():
    text = "Obama said that he and his wife had left Chicago, where Obama grew up."
    res = resolve_entities(
        text,
        [EntityCandidate(name="Barack Obama", type="PER", sentences=[
            SentenceMentions(sentence=text, mentions=[
                MentionCandidate(text="Obama"),
                MentionCandidate(text="he"),
                MentionCandidate(text="his", implicit=True),
                MentionCandidate(text="Obama"),
            ]),
        ])],
    )
    assert spans(res) == [[[(0, 5)], [(16, 18)], [(23, 26)], [(56, 61)]]]
    assert res.problems == []
    assert [text[s:e] for (s, e), in spans(res)[0]] == ["Obama", "he", "his", "Obama"]


def test_sentence_is_quoted_once_per_group_not_per_mention():
    text = "Alice met Bob. Alice told Alice's sister about Alice."
    second = "Alice told Alice's sister about Alice."
    res = resolve_entities(
        text,
        [entity(
            ("Alice", "Alice met Bob."),
            ("Alice", second),
            ("Alice", second),
            ("Alice", second),
        )],
    )
    assert spans(res) == [[[(0, 5)], [(15, 20)], [(26, 31)], [(47, 52)]]]


def test_a_verbatim_repeated_sentence_hands_out_its_occurrences_in_order():
    # Both groups quote the same sentence because the document says it twice;
    # the second group must land on the second copy, not re-resolve the first.
    text = "Ann arrived. Ann arrived."
    res = resolve_entities(
        text,
        [entity(("Ann", "Ann arrived."), name="Ann", type="PER")],
    )
    assert spans(res) == [[[(0, 3)]]]

    res = resolve_entities(
        text,
        [EntityCandidate(name="Ann", type="PER", sentences=[
            SentenceMentions(sentence="Ann arrived.", mentions=[MentionCandidate(text="Ann")]),
            SentenceMentions(sentence="Ann arrived.", mentions=[MentionCandidate(text="Ann")]),
        ])],
    )
    assert spans(res) == [[[(0, 3)], [(13, 16)]]]
    assert res.problems == []


def test_one_stray_mention_does_not_move_the_rest_of_the_group():
    text = "Ann met Bob in Paris. Carol waved at Ann."
    res = resolve_entities(
        text,
        [entity(
            ("Ann", "Ann met Bob in Paris."),
            ("Bob", "Ann met Bob in Paris."),
            ("Carol", "Ann met Bob in Paris."),  # quoted with the wrong sentence
        )],
    )
    assert spans(res) == [[[(0, 3)], [(8, 11)], [(22, 27)]]]
    assert [(p.mention, p.reason, p.dropped) for p in res.problems] == [
        ("Carol", MENTION_OUTSIDE_SENTENCE, False)
    ]


def test_repeated_surface_form_walks_forward():
    text = "Alice met Bob in Paris on Monday, then Alice flew home."
    res = resolve_entities(text, [entity(("Alice", text), ("Alice", text))])
    assert spans(res) == [[[(0, 5)], [(39, 44)]]]


def test_sentence_disambiguates_between_occurrences():
    text = "Obama spoke in Berlin. Later, Obama flew home."
    res = resolve_entities(text, [entity(("Obama", "Later, Obama flew home."))])
    assert spans(res) == [[[(30, 35)]]]


def test_nested_mention_of_another_entity_still_resolves():
    text = "She joined the Bank of America board before leaving America."
    res = resolve_entities(
        text,
        [
            entity(("Bank of America", text), name="BoA", type="ORG"),
            entity(("America", text), ("America", text), name="USA", type="LOC"),
        ],
    )
    # "America" prefers the unused occurrence, then falls back to the nested one.
    assert spans(res) == [[[(15, 30)]], [[(52, 59)], [(23, 30)]]]


def test_word_boundaries_are_preferred():
    text = "Annie greeted Ann at the door."
    res = resolve_entities(text, [entity(("Ann", text))])
    assert spans(res) == [[[(14, 17)]]]


# --- tolerant matching ------------------------------------------------------


def test_whitespace_and_line_breaks_are_forgiven():
    text = "Barack\n  Obama was born\nin Hawaii."
    res = resolve_entities(
        text,
        [entity(("Barack Obama", "Barack Obama was born in Hawaii."))],
    )
    assert spans(res) == [[[(0, 14)]]]
    assert text[0:14] == "Barack\n  Obama"


def test_case_quotes_and_dashes_are_forgiven():
    text = 'The judge called “Jean‑Luc Picard” to the stand.'
    res = resolve_entities(
        text,
        [entity(('"jean-luc picard"', 'The judge called "Jean-Luc Picard" to the stand.'))],
    )
    (start, end), = spans(res)[0][0]
    assert text[start:end] == "“Jean‑Luc Picard”"


def test_bidi_marks_in_the_document_are_skipped():
    text = "אמר ‏דוד‎ לרות."
    res = resolve_entities(text, [entity(("דוד", "אמר דוד לרות."))])
    (start, end), = spans(res)[0][0]
    assert text[start:end] == "דוד"


def test_fuzzy_sentence_still_anchors_the_window():
    text = (
        "The council met on Tuesday. Ahmed explained the whole thing better "
        "than the news did, everyone agreed. Ahmed left early."
    )
    # Sentence retyped with a dropped clause — the anchor is still long enough.
    res = resolve_entities(
        text,
        [entity(("Ahmed", "Ahmed explained the whole thing better than the news."))],
    )
    assert spans(res) == [[[(28, 33)]]]
    assert res.problems == []


# --- problems ---------------------------------------------------------------


def test_unfindable_mention_is_dropped_and_reported():
    text = "Alice met Bob in Paris."
    res = resolve_entities(text, [entity(("Carol", text), ("Bob", text))])
    assert spans(res) == [[[(10, 13)]]]
    assert [(p.mention, p.reason, p.dropped) for p in res.problems] == [
        ("Carol", MENTION_NOT_FOUND, True)
    ]


def test_entity_with_no_resolvable_mention_is_pruned():
    res = resolve_entities("Alice met Bob.", [entity(("Carol", "Alice met Bob."))])
    assert res.entities == []
    assert res.n_dropped == 1


def test_unknown_sentence_falls_back_to_the_document_and_flags_it():
    text = "Alice met Bob in Paris."
    res = resolve_entities(text, [entity(("Alice", "A sentence from another document entirely."))])
    assert spans(res) == [[[(0, 5)]]]
    assert [(p.reason, p.dropped) for p in res.problems] == [(SENTENCE_NOT_FOUND, False)]


def test_mention_outside_its_quoted_sentence_is_kept_and_flagged():
    text = "Alice met Bob in Paris. Carol stayed home."
    res = resolve_entities(text, [entity(("Carol", "Alice met Bob in Paris."))])
    assert spans(res) == [[[(24, 29)]]]
    assert [(p.reason, p.dropped) for p in res.problems] == [(MENTION_OUTSIDE_SENTENCE, False)]


def test_empty_mention_is_reported():
    res = resolve_entities("Alice met Bob.", [entity(("[…]", "Alice met Bob."), ("Alice", ""))])
    assert spans(res) == [[[(0, 5)]]]
    reasons = [(p.reason, p.dropped) for p in res.problems]
    assert reasons == [(EMPTY_MENTION, True), (SENTENCE_NOT_FOUND, False)]


def test_duplicate_mentions_collapse_within_an_entity():
    text = "Alice met Bob."
    res = resolve_entities(text, [entity(("Alice", text), ("alice", text))])
    assert spans(res) == [[[(0, 5)]]]
    assert [p.reason for p in res.problems] == [DUPLICATE_MENTION]


def test_fragments_must_appear_in_order():
    text = "Annie and George Washington visited Mount Vernon."
    res = resolve_entities(text, [entity(("Washington[…]Annie", text))])
    assert res.entities == []
    assert [p.reason for p in res.problems] == [MENTION_NOT_FOUND]


def test_unknown_entity_type_is_reported_not_raised():
    text = "Alice met Bob."
    res = resolve_entities(
        text,
        [
            {"name": "the vibe", "type": "GENRE",
             "sentences": [{"sentence": text, "mentions": [{"text": "Alice"}]}]},
            {"name": "Alice", "type": "PER",
             "sentences": [{"sentence": text, "mentions": [{"text": "Alice"}]}]},
        ],
    )
    assert entities_to_json(res.entities) == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]
    problem, = res.problems
    assert (problem.reason, problem.dropped, problem.name) == (INVALID_CANDIDATE, True, "the vibe")
    assert "type" in problem.detail


def test_resolution_counts():
    text = "Barack Obama was born in Hawaii. Obama later moved to Chicago."
    res = resolve_entities(
        text,
        [entity(("Barack Obama", text), ("Obama", "Obama later moved to Chicago."), ("Xi", text))],
    )
    assert res.n_mentions == 2
    assert res.n_dropped == 1


def test_candidates_may_be_plain_dicts():
    text = "Alice met Bob."
    res = resolve_entities(
        text,
        [{"name": "Alice", "type": "PER",
          "sentences": [{"sentence": text, "mentions": [{"text": "Alice"}]}]}],
    )
    assert entities_to_json(res.entities) == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]


def test_adjacent_fragments_collapse_into_a_continuous_mention():
    text = "Annie greeted Bob."
    res = resolve_entities(text, [entity(("Ann[…]ie", text))])
    assert entities_to_json(res.entities) == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]
