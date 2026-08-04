import pytest

from ner_annotator_llm.grounding import entities_to_json, resolve_entities
from ner_annotator_llm.schema import (
    Annotation,
    EntityCandidate,
    MentionCandidate,
    SentenceMentions,
    split_fragments,
)


class Answer:
    """Build an :class:`Annotation` the way the model writes one.

    ``declare`` adds a roster entry and returns its name; ``say`` adds mentions
    to a sentence, creating that sentence's entry on first use — so the tests
    read like the answer: entities first, then each sentence once.
    """

    def __init__(self):
        self.entities = []
        self.sentences = []

    def declare(self, name="e", type="PER"):
        self.entities.append(EntityCandidate(name=name, type=type))
        return name

    def say(self, sentence, *mentions):
        """``mentions`` are ``(entity, text)`` or ``(entity, text, flags)``."""
        group = next((g for g in self.sentences if g.sentence == sentence), None)
        if group is None:
            group = SentenceMentions(sentence=sentence, mentions=[])
            self.sentences.append(group)
        for m in mentions:
            group.mentions.append(
                MentionCandidate(entity=m[0], text=m[1], **(m[2] if len(m) > 2 else {}))
            )
        return self

    @property
    def annotation(self):
        return Annotation(entities=self.entities, sentences=self.sentences)


def one(*mentions, name="e", type="PER"):
    """The common case: a single entity, mentions given as ``(text, sentence)``."""
    answer = Answer()
    entity = answer.declare(name=name, type=type)
    for m in mentions:
        answer.say(m[1], (entity, m[0], m[2] if len(m) > 2 else {}))
    return answer.annotation


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
        ("Annie […] Washington", ["Annie", "Washington"]),
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
    res = resolve_entities(text, one(
        ("Barack Obama", "Barack Obama was born in Hawaii."),
        ("Obama", "Obama later moved to Chicago."),
    ))
    assert spans(res) == [[[(0, 12)], [(33, 38)]]]
    assert res.unresolved == []
    assert text[33:38] == "Obama"


def test_output_matches_the_annotation_schema():
    text = "Annie and George Washington visited Mount Vernon."
    answer = Answer()
    annie = answer.declare(name="Annie Washington")
    george = answer.declare(name="George Washington")
    answer.say(text, (annie, "Annie[…]Washington"), (george, "George Washington"))

    res = resolve_entities(text, answer.annotation)
    assert entities_to_json(res.entities) == [
        {"type": "PER", "mentions": [{"fragments": [{"start": 0, "end": 5},
                                                    {"start": 17, "end": 27}]}]},
        {"type": "PER", "mentions": [{"start": 10, "end": 27}]},
    ]


def test_entity_type_comes_from_the_roster():
    text = "The mayor of London opened the bridge."
    answer = Answer()
    job = answer.declare(name="the mayor", type="JOB_TITLE")
    city = answer.declare(name="London", type="LOC")
    answer.say(text, (job, "mayor"), (city, "London"))

    res = resolve_entities(text, answer.annotation)
    assert [e.type for e in res.entities] == ["JOB_TITLE", "LOC"]
    assert entities_to_json(res.entities)[0] == {
        "type": "JOB_TITLE", "mentions": [{"start": 4, "end": 9}]
    }


def test_flags_ride_through():
    text = "I went to the theatre with Maxim's brother."
    answer = Answer()
    maxim = answer.declare(name="Maxim")
    brother = answer.declare(name="the brother")
    answer.say(text, (maxim, "Maxim", {"implicit": True}),
               (brother, "Maxim's brother", {"relative": True}))

    res = resolve_entities(text, answer.annotation)
    assert entities_to_json(res.entities) == [
        {"type": "PER", "mentions": [{"start": 27, "end": 32, "implicit": True}]},
        {"type": "PER", "mentions": [{"start": 27, "end": 42, "relative": True}]},
    ]


# --- one sentence, many mentions, many entities -----------------------------


def test_all_mentions_in_one_sentence_resolve_left_to_right():
    text = "Obama said that he and his wife had left Chicago, where Obama grew up."
    answer = Answer()
    obama = answer.declare(name="Barack Obama")
    answer.say(text, (obama, "Obama"), (obama, "he"),
               (obama, "his", {"implicit": True}), (obama, "Obama"))

    res = resolve_entities(text, answer.annotation)
    assert spans(res) == [[[(0, 5)], [(16, 18)], [(23, 26)], [(56, 61)]]]
    assert res.unresolved == []
    assert [text[s:e] for (s, e), in spans(res)[0]] == ["Obama", "he", "his", "Obama"]


def test_one_sentence_entry_serves_every_entity_in_it():
    text = "Obama said that he and his wife had left Chicago."
    answer = Answer()
    obama = answer.declare(name="Barack Obama")
    wife = answer.declare(name="his wife")
    city = answer.declare(name="Chicago", type="LOC")
    answer.say(text, (obama, "Obama"), (obama, "he"), (obama, "his", {"implicit": True}),
               (wife, "his wife", {"relative": True}), (city, "Chicago"))

    res = resolve_entities(text, answer.annotation)
    assert len(answer.sentences) == 1
    assert entities_to_json(res.entities) == [
        {"type": "PER", "mentions": [{"start": 0, "end": 5}, {"start": 16, "end": 18},
                                     {"start": 23, "end": 26, "implicit": True}]},
        {"type": "PER", "mentions": [{"start": 23, "end": 31, "relative": True}]},
        {"type": "LOC", "mentions": [{"start": 41, "end": 48}]},
    ]
    assert res.unresolved == []
    assert text[41:48] == "Chicago"


def test_mentions_of_one_entity_come_back_in_document_order():
    text = "Chicago is cold. Obama left Chicago. He misses the city."
    answer = Answer()
    city = answer.declare(name="Chicago", type="LOC")
    answer.say("He misses the city.", (city, "the city"))
    answer.say("Chicago is cold.", (city, "Chicago"))
    answer.say("Obama left Chicago.", (city, "Chicago"))

    # The sentences arrive out of order; the mentions still come back sorted.
    res = resolve_entities(text, answer.annotation)
    assert spans(res) == [[[(0, 7)], [(28, 35)], [(47, 55)]]]


def test_sentence_is_quoted_once_per_group_not_per_mention():
    text = "Alice met Bob. Alice told Alice's sister about Alice."
    second = "Alice told Alice's sister about Alice."
    res = resolve_entities(text, one(
        ("Alice", "Alice met Bob."),
        ("Alice", second), ("Alice", second), ("Alice", second),
    ))
    assert spans(res) == [[[(0, 5)], [(15, 20)], [(26, 31)], [(47, 52)]]]


def test_repeated_surface_form_walks_forward():
    text = "Alice met Bob in Paris on Monday, then Alice flew home."
    res = resolve_entities(text, one(("Alice", text), ("Alice", text)))
    assert spans(res) == [[[(0, 5)], [(39, 44)]]]


def test_sentence_disambiguates_between_occurrences():
    text = "Obama spoke in Berlin. Later, Obama flew home."
    res = resolve_entities(text, one(("Obama", "Later, Obama flew home.")))
    assert spans(res) == [[[(30, 35)]]]


def test_nested_mention_of_another_entity_still_resolves():
    text = "She joined the Bank of America board before leaving America."
    answer = Answer()
    org = answer.declare(name="Bank of America", type="ORG")
    usa = answer.declare(name="America", type="LOC")
    answer.say(text, (org, "Bank of America"), (usa, "America"), (usa, "America"))

    res = resolve_entities(text, answer.annotation)
    # The nested "America" resolves where it is; overlapping the ORG is normal.
    assert spans(res) == [[[(15, 30)]], [[(23, 30)], [(52, 59)]]]


def test_word_boundaries_are_preferred():
    text = "Annie greeted Ann at the door."
    res = resolve_entities(text, one(("Ann", text)))
    assert spans(res) == [[[(14, 17)]]]


def test_two_entities_sharing_a_name_do_not_land_on_the_same_span():
    text = "Washington met Washington."
    answer = Answer()
    george, martha = answer.declare(name="George"), answer.declare(name="Martha")
    answer.say(text, (george, "Washington"), (martha, "Washington"))

    res = resolve_entities(text, answer.annotation)
    assert spans(res) == [[[(0, 10)]], [[(15, 25)]]]


# --- tolerant matching ------------------------------------------------------


def test_whitespace_and_line_breaks_are_forgiven():
    text = "Barack\n  Obama was born\nin Hawaii."
    res = resolve_entities(text, one(("Barack Obama", "Barack Obama was born in Hawaii.")))
    assert spans(res) == [[[(0, 14)]]]
    assert text[0:14] == "Barack\n  Obama"


def test_bidi_marks_in_the_document_are_skipped():
    text = "אמר ‏דוד‎ לרות."
    res = resolve_entities(text, one(("דוד", "אמר דוד לרות.")))
    (start, end), = spans(res)[0][0]
    assert text[start:end] == "דוד"


def test_fuzzy_sentence_still_anchors_the_window():
    text = (
        "The council met on Tuesday. Ahmed explained the whole thing better "
        "than the news did, everyone agreed. Ahmed left early."
    )
    # Sentence retyped with a dropped clause — the anchor is still long enough.
    res = resolve_entities(text, one(
        ("Ahmed", "Ahmed explained the whole thing better than the news.")
    ))
    assert spans(res) == [[[(28, 33)]]]
    assert res.unresolved == []


# --- entity names ----------------------------------------------------------


def test_a_name_that_matches_nothing_drops_the_mention():
    text = "Alice met Bob."
    answer = Answer()
    alice = answer.declare(name="Alice")
    answer.say(text, (alice, "Alice"), ("nobody at all", "Bob"))

    res = resolve_entities(text, answer.annotation)
    assert entities_to_json(res.entities) == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]
    assert [m.text for m in res.unresolved] == ["Bob"]


@pytest.mark.parametrize("written", ["Alice Cooper", "alice cooper", "Alice  Cooper!"])
def test_near_miss_names_are_matched_to_the_declared_entity(written):
    text = "Alice met Bob."
    answer = Answer()
    answer.declare(name="Alice Cooper")
    answer.say(text, (written, "Alice"))

    res = resolve_entities(text, answer.annotation)
    assert entities_to_json(res.entities) == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]
    assert res.unresolved == []


def test_a_declared_entity_nobody_mentions_is_dropped():
    text = "Alice met Bob."
    answer = Answer()
    alice = answer.declare(name="Alice")
    answer.declare(name="Carol")
    answer.say(text, (alice, "Alice"))

    res = resolve_entities(text, answer.annotation)
    assert len(res.entities) == 1


def test_a_plain_dict_answer_is_accepted():
    text = "Alice met Bob."
    res = resolve_entities(text, {
        "entities": [{"name": "Alice", "type": "PER"}],
        "sentences": [{"sentence": text, "mentions": [{"entity": "Alice", "text": "Alice"}]}],
    })
    assert entities_to_json(res.entities) == [{"type": "PER", "mentions": [{"start": 0, "end": 5}]}]


# --- what cannot be placed -------------------------------------------------


def test_unfindable_mention_is_dropped():
    text = "Alice met Bob in Paris."
    answer = Answer()
    carol, bob = answer.declare(name="Carol"), answer.declare(name="Bob")
    answer.say(text, (carol, "Carol"), (bob, "Bob"))

    res = resolve_entities(text, answer.annotation)
    assert spans(res) == [[[(10, 13)]]]
    assert [m.text for m in res.unresolved] == ["Carol"]


def test_a_sentence_that_is_not_in_the_document_still_places_its_mentions():
    text = "Alice met Bob in Paris."
    res = resolve_entities(text, one(("Alice", "A sentence from another document entirely.")))
    assert spans(res) == [[[(0, 5)]]]


def test_resolution_counts_what_it_grounded():
    text = "Barack Obama was born in Hawaii. Obama later moved to Chicago."
    res = resolve_entities(text, one(
        ("Barack Obama", text),
        ("Obama", "Obama later moved to Chicago."),
        ("Xi Jinping", text),
    ))
    assert res.n_mentions == 2
    assert [m.text for m in res.unresolved] == ["Xi Jinping"]
