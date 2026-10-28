import pytest

from pronresolve.models import AmbiguityIndex, ReadingProfile
from pronresolve.storage import decode_v2, encode_v2


def valid_v2():
    return {
        "schema_version": 2,
        "language": "en",
        "locale": "en-US",
        "entries": {
            "read": {
                "VERB": [
                    {
                        "id": "r1",
                        "ipa": "ɹiːd",
                        "sense_ids": ["s1"],
                        "cues": {"3.5": ["interpret"], "3": ["comprehend"]},
                    },
                    {"id": "r2", "ipa": "ɹɛd", "sense_ids": [], "cues": {}},
                ]
            }
        },
    }


def _set_language(value):
    value["language"] = " "


def _set_locale(value):
    value["locale"] = 3


def _set_entries(value):
    value["entries"] = []


def _set_empty_word(value):
    value["entries"] = {" ": {"VERB": []}}


def _set_empty_pos(value):
    value["entries"]["read"] = {" ": []}


def _set_single_candidate(value):
    value["entries"]["read"]["VERB"].pop()


def _duplicate_id(value):
    value["entries"]["read"]["VERB"][1]["id"] = "r1"


def _empty_id(value):
    value["entries"]["read"]["VERB"][0]["id"] = " "


def _empty_ipa(value):
    value["entries"]["read"]["VERB"][0]["ipa"] = " "


def _non_array_sense_ids(value):
    value["entries"]["read"]["VERB"][0]["sense_ids"] = "s1"


def _bad_weight(value):
    value["entries"]["read"]["VERB"][0]["cues"] = {"not-a-weight": ["token"]}


def _unknown_weight(value):
    value["entries"]["read"]["VERB"][0]["cues"] = {"99": ["token"]}


def _non_string_token(value):
    value["entries"]["read"]["VERB"][0]["cues"] = {"3": [42]}


def _empty_token(value):
    value["entries"]["read"]["VERB"][0]["cues"] = {"3": [""]}


def _duplicate_cue(value):
    value["entries"]["read"]["VERB"][0]["cues"]["3.5"] = ["comprehend"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (_set_language, r"index.language must be a non-empty string"),
        (_set_locale, r"index.locale must be a non-empty string or null"),
        (_set_entries, r"index.entries must be a JSON object"),
        (_set_empty_word, r"empty or invalid word key"),
        (_set_empty_pos, r"empty POS key"),
        (_set_single_candidate, r"at least two candidates"),
        (_duplicate_id, r"duplicates reading ID"),
        (_empty_id, r"\.id must be a non-empty string"),
        (_empty_ipa, r"\.ipa must be a non-empty string"),
        (_non_array_sense_ids, r"sense_ids must be an array of strings"),
        (_bad_weight, r"numeric cue weight"),
        (_unknown_weight, r"unsupported weight"),
        (_non_string_token, r"non-string or empty token"),
        (_empty_token, r"non-string or empty token"),
        (_duplicate_cue, r"assigns token .* more than once"),
    ],
)
def test_schema_v2_rejects_malformed_payloads(mutate, message):
    value = valid_v2()
    mutate(value)
    with pytest.raises(ValueError, match=message):
        decode_v2(value)


def test_schema_v2_normalizes_loaded_data_to_canonical_internal_form():
    value = valid_v2()
    value["entries"] = {
        "Read": {
            "verb": [
                {
                    "id": "r1",
                    "ipa": "/ɹiːd/",
                    "sense_ids": ["s2", "s1"],
                    "cues": {"3.0": ["Comprehend"]},
                },
                {"id": "r2", "ipa": "ɹɛd", "sense_ids": [], "cues": {}},
            ]
        }
    }
    index = decode_v2(value)
    profile = index.profiles[0]
    assert profile.word == "read"
    assert profile.pos == "VERB"
    assert profile.ipa == "ɹiːd"
    assert profile.sense_ids == ("s1", "s2")
    assert profile.cues[0].token == "comprehend"
    assert encode_v2(index)["entries"].keys() == {"read"}


def test_encoder_rejects_an_emitted_group_with_fewer_than_two_candidates():
    index = AmbiguityIndex(
        language="en",
        locale=None,
        schema_version=2,
        profiles=(ReadingProfile("read", "VERB", "r1", "ɹiːd"),),
    )
    with pytest.raises(ValueError, match="at least two candidates"):
        encode_v2(index)
