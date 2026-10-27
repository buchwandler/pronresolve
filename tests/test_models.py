import json

import pytest

from pronresolve.models import AmbiguityIndex
from pronresolve.storage import load_index


def valid_index():
    return {
        "schema_version": 1,
        "language": "en",
        "locale": None,
        "profiles": [
            {
                "word": "x",
                "pos": "NOUN",
                "reading_id": "r1",
                "ipa": ["ɛks"],
                "glosses": ["letter"],
            }
        ],
    }


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda value: value["profiles"].__setitem__(0, 123),
            r"profiles\[0\] must be a JSON object",
        ),
        (
            lambda value: value["profiles"][0].pop("reading_id"),
            r"profiles\[0\].reading_id is required",
        ),
        (
            lambda value: value["profiles"][0].update(ipa=[]),
            r"profiles\[0\].ipa must be a non-empty array",
        ),
        (
            lambda value: value["profiles"][0].update(ipa=[1]),
            r"profiles\[0\].ipa must be an array of strings",
        ),
        (
            lambda value: value["profiles"][0].update(tags="noun"),
            r"profiles\[0\].tags must be an array of strings",
        ),
        (lambda value: value.update(language=""), r"index.language must be a non-empty string"),
    ],
)
def test_index_rejects_malformed_schema(mutate, message):
    value = valid_index()
    mutate(value)
    with pytest.raises(ValueError, match=message):
        AmbiguityIndex.from_dict(value)


def test_index_round_trips_schema_one():
    value = valid_index()
    index = AmbiguityIndex.from_dict(value)
    assert AmbiguityIndex.from_dict(index.to_dict()) == index


@pytest.mark.parametrize("version", ["1", 1.0, True, None])
def test_load_index_rejects_invalid_schema_version_type(tmp_path, version):
    value = valid_index()
    value["schema_version"] = version
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version must be an integer"):
        load_index(path)
