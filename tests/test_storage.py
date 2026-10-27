import json

import pytest

from pronresolve import AmbiguityIndex, ReadingProfile, Resolver, load_index, save_index


def test_index_round_trip_and_resolver_path(tmp_path):
    index = AmbiguityIndex(
        language="en",
        locale="en-US",
        profiles=(
            ReadingProfile(
                word="wug",
                pos="NOUN",
                reading_id="r1-en-example",
                ipa=("wʌg",),
                glosses=("a bird",),
            ),
            ReadingProfile(
                word="wug",
                pos="NOUN",
                reading_id="r1-en-example2",
                ipa=("wuːg",),
                glosses=("a bend",),
            ),
        ),
    )
    path = save_index(index, tmp_path / "index.json")
    loaded = load_index(path)
    assert loaded == index
    assert Resolver.from_path(path).index == index


def test_unknown_schema_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 99, "profiles": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported ambiguity index schema"):
        load_index(path)
