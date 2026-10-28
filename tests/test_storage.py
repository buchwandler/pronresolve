import json

import pytest

from pronresolve.models import AmbiguityIndex, Cue, ReadingProfile
from pronresolve.storage import decode_v1, decode_v2, load_index, save_index


def _v1_profile(reading_id, ipa, **evidence):
    return {
        "word": "read",
        "pos": "VERB",
        "reading_id": reading_id,
        "ipa": [ipa],
        "sense_ids": [f"sense-{reading_id}"],
        "etymology_numbers": ["1"],
        "glosses": evidence.get("glosses", []),
        "topics": evidence.get("topics", []),
        "tags": evidence.get("tags", []),
        "examples": evidence.get("examples", []),
        "synonyms": evidence.get("synonyms", []),
        "antonyms": evidence.get("antonyms", []),
    }


def test_index_round_trip_saves_compact_v2_and_resolver_path_loads_it(tmp_path):
    index = AmbiguityIndex(
        language="en",
        locale="en-US",
        schema_version=2,
        profiles=(
            ReadingProfile(
                word="wug",
                pos="NOUN",
                reading_id="r1-en-example",
                ipa="wʌg",
                cues=(Cue("bird", 3),),
            ),
            ReadingProfile(
                word="wug",
                pos="NOUN",
                reading_id="r1-en-example2",
                ipa="wuːg",
                cues=(Cue("bend", 3),),
            ),
        ),
    )
    path = save_index(index, tmp_path / "nested" / "index.json")
    raw = path.read_text(encoding="utf-8")
    loaded = load_index(path)
    assert json.loads(raw)["schema_version"] == 2
    assert "\n  " not in raw
    assert loaded == index
    assert decode_v2(json.loads(raw)) == index


def test_v1_load_applies_policy_b_and_save_writes_v2(tmp_path):
    value = {
        "schema_version": 1,
        "language": "en",
        "locale": "en-US",
        "profiles": [
            _v1_profile(
                "read-present",
                "/ɹiːd/",
                glosses=["comprehend text"],
                synonyms=["interpret"],
                topics=["communications"],
                tags=["transitive"],
                examples=["exampleonlycue"],
                antonyms=["ignore"],
            ),
            _v1_profile("read-past", "[ɹɛd]", glosses=["past participle"]),
        ],
    }
    index = decode_v1(value)
    by_id = {profile.reading_id: profile for profile in index.profiles}
    present = {cue.token: cue.weight for cue in by_id["read-present"].cues}
    assert present["interpret"] == 3.5
    assert present["comprehend"] == 3.0
    assert present["communications"] == 2.5
    assert present["transitive"] == 1.0
    assert present["ignore"] == 0.75
    assert "exampleonlycue" not in present
    assert by_id["read-present"].ipa == "ɹiːd"
    assert by_id["read-present"].sense_ids == ("sense-read-present",)
    assert not hasattr(by_id["read-present"], "etymology_numbers")

    source = tmp_path / "legacy.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    assert load_index(source) == index
    output = save_index(index, tmp_path / "new.json")
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 2


def test_v1_rejects_multiple_distinct_ipa_values_in_one_runtime_profile():
    value = {
        "schema_version": 1,
        "language": "en",
        "locale": None,
        "profiles": [_v1_profile("ambiguous", "ɹiːd", glosses=["x"]) | {"ipa": ["ɹiːd", "ɹɛd"]}],
    }
    with pytest.raises(ValueError, match="exactly one"):
        decode_v1(value)


def test_unknown_schema_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported ambiguity index schema"):
        load_index(path)
