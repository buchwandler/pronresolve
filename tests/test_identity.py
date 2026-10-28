import pytest
from typing import Any, cast

from pronresolve.discovery import reading_id_v2
from pronresolve.models import ReadingProfile, SemanticAnchor, SemanticIdentity, is_reading_id_v2


def test_reading_id_v2_matches_golden_serialization_fixture() -> None:
    anchor = SemanticAnchor(
        namespace="lexhint:en:dictionary",
        keys=("fixture:bass:fish",),
    )

    reading_id = reading_id_v2("en", "BASS", "noun", anchor)

    assert reading_id == "r2-en-4ac47bae8fd561b340ad3cec"
    assert is_reading_id_v2(reading_id)


def test_semantic_anchor_normalizes_opaque_keys_without_casefolding() -> None:
    anchor = SemanticAnchor(
        namespace=" lexhint:en:e\u0301 ",
        keys=(" sense:B ", "sense:A", "sense:A"),
    )

    assert anchor.namespace == "lexhint:en:é"
    assert anchor.keys == ("sense:A", "sense:B")
    assert SemanticAnchor("lexhint:en:é", ("Sense:A", "sense:B")) != anchor


def test_reading_id_v2_uses_only_semantic_identity_fields() -> None:
    anchor = SemanticAnchor("lexhint:en:dictionary", ("sense-fish", "sense-water"))
    equivalent_anchor = SemanticAnchor(
        "lexhint:en:dictionary", (" sense-water ", "sense-fish", "sense-fish")
    )

    expected = reading_id_v2("en-US", "Bass", "Noun", anchor)

    assert reading_id_v2("en-US", "bass", "NOUN", equivalent_anchor) == expected
    single_sense = SemanticAnchor(anchor.namespace, ("sense-fish",))
    assert reading_id_v2("en-US", "bass", "NOUN", single_sense) != expected
    assert reading_id_v2("en-US", "bass", "VERB", anchor) != expected
    assert reading_id_v2("en-US", "bass-fish", "NOUN", anchor) != expected
    assert expected.startswith("r2-en-us-")


def test_semantic_anchor_rejects_missing_or_empty_identity() -> None:
    with pytest.raises(ValueError, match="namespace values must be non-empty"):
        SemanticAnchor("  ", ("sense-a",))
    with pytest.raises(ValueError, match="at least one key"):
        SemanticAnchor("lexhint:en:dictionary", ())
    with pytest.raises(ValueError, match="key values must be non-empty"):
        SemanticAnchor("lexhint:en:dictionary", (" ",))
    with pytest.raises(ValueError, match="tuple of strings"):
        SemanticAnchor("lexhint:en:dictionary", cast(Any, ["sense-a"]))  # type: ignore[arg-type]


def test_semantic_identity_provenance_is_canonical_and_validated() -> None:
    anchor = SemanticAnchor("lexhint:en:dictionary", ("sense-fish",))
    identity = SemanticIdentity(
        reading_id=reading_id_v2("en", "bass", "noun", anchor),
        word="Bass",
        pos="noun",
        semantic_anchor=anchor,
        sense_ids=(" sense-z ", "sense-a", "sense-z"),
        source_ipas=("/bæs/", "beɪs"),
        anchor_ipa="beɪs",
    )

    assert identity.word == "bass"
    assert identity.pos == "NOUN"
    assert identity.sense_ids == ("sense-a", "sense-z")
    assert identity.source_ipas == ("beɪs", "bæs")
    assert identity.to_dict()["semantic_anchor"] == {
        "namespace": "lexhint:en:dictionary",
        "keys": ["sense-fish"],
    }
    with pytest.raises(ValueError, match="first sorted source IPA"):
        SemanticIdentity(
            reading_id=identity.reading_id,
            word="bass",
            pos="NOUN",
            semantic_anchor=anchor,
            sense_ids=(),
            source_ipas=("bæs", "beɪs"),
            anchor_ipa="bæs",
        )


def test_r2_id_validation_rejects_malformed_values() -> None:
    assert not is_reading_id_v2("r2-en-not-a-digest")
    assert not is_reading_id_v2("r1-en-4ac47bae8fd561b340ad3cec")


def test_reading_id_v2_rejects_non_string_identity_fields() -> None:
    anchor = SemanticAnchor("lexhint:en:dictionary", ("sense-a",))
    with pytest.raises(ValueError, match="language must be a non-empty string"):
        reading_id_v2(None, "bass", "NOUN", anchor)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="word must be a non-empty string"):
        reading_id_v2("en", None, "NOUN", anchor)  # type: ignore[arg-type]


def test_reading_profile_rejects_malformed_r2_id() -> None:
    with pytest.raises(ValueError, match="well-formed r2 ID"):
        ReadingProfile("bass", "NOUN", "r2-en-invalid", "bæs")
