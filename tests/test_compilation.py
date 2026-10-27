import pytest

from pronresolve.compile import EVIDENCE_WEIGHTS, compile_cues
from pronresolve.models import Cue, ReadingProfile


def cue_map(cues):
    return {cue.token: cue.weight for cue in cues}


def test_policy_b_weights_are_canonical_and_examples_are_not_a_scoring_field():
    assert EVIDENCE_WEIGHTS == {
        "synonyms": 3.5,
        "glosses": 3.0,
        "topics": 2.5,
        "tags": 1.0,
        "antonyms": 0.75,
    }
    assert "examples" not in EVIDENCE_WEIGHTS


def test_compiler_assigns_each_policy_b_weight_and_discards_stopwords():
    cues = compile_cues(
        {
            "synonyms": ["synonymword"],
            "glosses": ["glossword"],
            "topics": ["topicword"],
            "tags": ["tagword"],
            "antonyms": ["antonymword"],
        }
    )
    assert cue_map(cues) == {
        "synonymword": 3.5,
        "glossword": 3.0,
        "topicword": 2.5,
        "tagword": 1.0,
        "antonymword": 0.75,
    }
    assert "the" not in cue_map(compile_cues({"glosses": ["the instrument"]}))


def test_compiler_ignores_examples_and_uses_maximum_duplicate_weight():
    cues = compile_cues(
        {
            "examples": ["exampleonlycue sharedcue"],
            "glosses": ["glosscue sharedcue"],
            "synonyms": ["synonymcue sharedcue"],
        }
    )
    assert cue_map(cues) == {
        "glosscue": 3.0,
        "sharedcue": 3.5,
        "synonymcue": 3.5,
    }
    assert "exampleonlycue" not in cue_map(cues)


def test_compiler_is_independent_of_field_order_and_unicode_composition():
    first = compile_cues(
        {
            "glosses": ["Cafe\u0301 instrument"],
            "synonyms": ["instrument café"],
            "tags": ["useful"],
        }
    )
    second = compile_cues(
        {
            "tags": ["useful"],
            "synonyms": ["café instrument"],
            "glosses": ["café instrument"],
        }
    )
    assert first == second
    assert [cue.token for cue in first] == sorted(cue.token for cue in first)
    assert cue_map(first)["café"] == 3.5


def test_runtime_profile_is_lean_scalar_and_has_unique_ordered_cues():
    profile = ReadingProfile(
        word="Read",
        pos="verb",
        reading_id="r1",
        ipa="/ɹɛd/",
        sense_ids=("sense-b", "sense-a"),
        cues=(Cue("zebra", 1), Cue("alpha", 3)),
    )
    assert profile.word == "read"
    assert profile.pos == "VERB"
    assert profile.ipa == "ɹɛd"
    assert profile.sense_ids == ("sense-a", "sense-b")
    assert [cue.token for cue in profile.cues] == ["alpha", "zebra"]
    assert set(profile.to_dict()) == {"id", "ipa", "sense_ids", "cues"}
    with pytest.raises(ValueError, match="duplicate tokens"):
        ReadingProfile("read", "VERB", "r2", "ɹɛd", cues=(Cue("word", 1), Cue("WORD", 3)))

    with pytest.raises(ValueError, match="not defined by the Policy B"):
        Cue("unknown", 4.0)
