import pytest

from pronresolve.models import AmbiguityIndex
from pronresolve.storage import decode_v2, encode_v2


def valid_index():
    return {
        "schema_version": 2,
        "language": "en",
        "locale": None,
        "entries": {
            "read": {
                "VERB": [
                    {
                        "id": "r1",
                        "ipa": "ɹiːd",
                        "sense_ids": ["sense-read"],
                        "cues": {"3.5": ["interpret"], "3": ["comprehend"]},
                    },
                    {
                        "id": "r2",
                        "ipa": "ɹɛd",
                        "sense_ids": ["sense-past"],
                        "cues": {"3": ["past"]},
                    },
                ]
            }
        },
    }


def test_index_round_trips_schema_two_as_grouped_candidates():
    value = valid_index()
    index = decode_v2(value)
    encoded = encode_v2(index)
    assert encoded == value
    assert AmbiguityIndex.from_dict(value) == index
    assert list(encoded["entries"]) == ["read"]
    assert list(encoded["entries"]["read"]) == ["VERB"]


def test_index_rejects_bad_root_and_schema_version():
    with pytest.raises(ValueError, match="root must be a JSON object"):
        AmbiguityIndex.from_dict([])
    for version in ("2", 2.0, True, None, 99):
        value = valid_index()
        value["schema_version"] = version
        with pytest.raises(ValueError, match="schema_version|unsupported"):
            AmbiguityIndex.from_dict(value)


def test_runtime_model_rejects_non_scalar_ipa_and_duplicate_cues():
    value = valid_index()
    value["entries"]["read"]["VERB"][0]["ipa"] = ["ɹiːd"]
    with pytest.raises(ValueError, match="ipa must be a non-empty string"):
        AmbiguityIndex.from_dict(value)
