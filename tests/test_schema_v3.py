from __future__ import annotations

import copy
import json

import pytest

from pronresolve import (
    AmbiguityIndex,
    Cue,
    ReadingProfile,
    Resolver,
    SemanticAnchor,
    decode_v2,
    decode_v3,
    encode_v3,
    reading_id_v2,
    save_index,
)
from pronresolve.storage import load_index


def sample_index() -> AmbiguityIndex:
    fish_anchor = SemanticAnchor("fixture:en", ("bass-fish",))
    music_anchor = SemanticAnchor("fixture:en", ("bass-music",))
    return AmbiguityIndex(
        language="en",
        locale="en-US",
        rules_id="en-us",
        profiles=(
            ReadingProfile(
                word="bass",
                pos="NOUN",
                reading_id=reading_id_v2("en", "bass", "NOUN", fish_anchor),
                anchor_ipa="bæs",
                cues=(Cue("fish", 3.0),),
            ),
            ReadingProfile(
                word="bass",
                pos="NOUN",
                reading_id=reading_id_v2("en", "bass", "NOUN", music_anchor),
                anchor_ipa="beɪs",
                cues=(Cue("music", 3.0),),
            ),
        ),
    )


def legacy_v2() -> dict[str, object]:
    return {
        "schema_version": 2,
        "language": "en",
        "locale": "en-US",
        "entries": {
            "bass": {
                "NOUN": [
                    {"id": "r1-fish", "ipa": "bæs", "sense_ids": [], "cues": {"3": ["fish"]}},
                    {"id": "r1-music", "ipa": "beɪs", "sense_ids": [], "cues": {"3": ["music"]}},
                ]
            }
        },
    }


def test_schema_v3_round_trip_uses_semantic_ids_and_anchor_ipa():
    index = sample_index()
    payload = encode_v3(index)

    assert payload["schema_version"] == 3
    assert payload["id_version"] == 2
    assert payload["rules_id"] == "en-us"
    candidates = payload["entries"]["bass"]["NOUN"]
    assert all(set(candidate) == {"id", "anchor_ipa", "cues"} for candidate in candidates)
    assert decode_v3(payload) == index


def test_schema_v3_rejects_invalid_id_version_and_non_r2_ids():
    payload = encode_v3(sample_index())
    for id_version in (True, 1, 2.0, "2", None):
        malformed = copy.deepcopy(payload)
        malformed["id_version"] = id_version
        with pytest.raises(ValueError, match="id_version must be 2"):
            decode_v3(malformed)

    malformed = copy.deepcopy(payload)
    malformed["entries"]["bass"]["NOUN"][0]["id"] = "r1-old-reading"
    with pytest.raises(ValueError, match="well-formed r2 reading ID"):
        decode_v3(malformed)


def test_schema_v3_rejects_duplicate_reading_ids():
    payload = encode_v3(sample_index())
    payload["entries"]["bass"]["NOUN"][1]["id"] = payload["entries"]["bass"]["NOUN"][0]["id"]

    with pytest.raises(ValueError, match="duplicates reading ID"):
        decode_v3(payload)


def test_schema_v2_load_save_preserves_legacy_ids_and_schema(tmp_path):
    source = tmp_path / "legacy-v2.json"
    source.write_text(json.dumps(legacy_v2()), encoding="utf-8")
    loaded = load_index(source)

    assert loaded.schema_version == 2
    assert {profile.reading_id for profile in loaded.profiles} == {"r1-fish", "r1-music"}
    output = save_index(loaded, tmp_path / "saved-v2.json")
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert {candidate["id"] for candidate in saved["entries"]["bass"]["NOUN"]} == {
        "r1-fish",
        "r1-music",
    }
    with pytest.raises(ValueError, match="well-formed r2"):
        save_index(loaded, tmp_path / "not-upgraded.json", schema_version=3)
    assert decode_v2(saved) == loaded


def test_v3_resolver_returns_r2_selector_and_diagnostic_aliases():
    index = sample_index()
    text = "bass fish swims"
    result = Resolver(index, min_score=0, min_margin=0).resolve(
        text,
        start=0,
        end=4,
        pos="NOUN",
        lemma="bass",
    )

    assert result is not None
    assert result.reading_id.startswith("r2-en-")
    assert result.selector == f"READING:{result.reading_id}"
    assert result.anchor_ipa == "bæs"
    assert result.ipa == result.anchor_ipa


def test_reading_profile_keeps_ipa_as_compatibility_alias():
    profile = ReadingProfile("bass", "NOUN", "r1-legacy", ipa="bæs")
    assert profile.anchor_ipa == "bæs"
    assert profile.ipa == profile.anchor_ipa
