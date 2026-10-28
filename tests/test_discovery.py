from pronresolve import discover_ambiguities, save_index


def entry(word, pos, ipa, gloss, sense_id):
    return {
        "word": word,
        "pos": pos,
        "etymology_number": "1",
        "pronunciations": [{"ipa": ipa, "tags": []}],
        "senses": [
            {
                "sense_id": sense_id,
                "glosses": [gloss],
                "topics": [],
                "tags": [],
                "examples": [],
                "synonyms": [],
                "antonyms": [],
            }
        ],
    }


def test_discovers_different_ipa_for_same_word_and_pos():
    result = discover_ambiguities(
        [
            entry("wug", "noun", "/wʌg/", "a small bird", "sense-a"),
            entry("Wug", "NOUN", "[wuːg]", "a bend in a road", "sense-b"),
        ],
        language="en",
        locale="en-US",
    )

    assert len(result.index.profiles) == 2
    assert result.report.resolvable_keys == 1
    assert result.report.unlinked_ambiguity_keys == 0
    assert {profile.ipa for profile in result.index.profiles} == {"wʌg", "wuːg"}
    assert {profile.word.casefold() for profile in result.index.profiles} == {"wug"}


def test_discovery_compiles_cues_without_examples_or_raw_runtime_evidence():
    rows = [
        entry("lead", "verb", "liːd", "to guide", "guide"),
        entry("lead", "verb", "lɛd", "a metallic element", "metal"),
    ]
    rows[0]["senses"][0]["examples"] = ["quizzicalexamplecue"]
    result = discover_ambiguities(rows, language="en")

    profiles = result.index.profiles
    assert len(profiles) == 2
    assert all(profile.ipa in {"liːd", "lɛd"} for profile in profiles)
    assert all(not hasattr(profile, "examples") for profile in profiles)
    assert all(not hasattr(profile, "glosses") for profile in profiles)
    assert all("quizzicalexamplecue" not in {cue.token for cue in p.cues} for p in profiles)
    assert all(profile.sense_ids for profile in profiles)
    for candidates in result.index.to_dict()["entries"]["lead"]["VERB"]:
        assert set(candidates) == {"id", "anchor_ipa", "cues"}


def test_same_entry_with_two_ipa_is_reported_but_not_guessed():
    result = discover_ambiguities(
        [
            {
                "word": "wug",
                "pos": "noun",
                "pronunciations": [{"ipa": "wʌg"}, {"ipa": "wuːg"}],
                "senses": [{"sense_id": "sense-a", "glosses": ["a small bird"]}],
            }
        ],
        language="en",
    )

    assert result.index.profiles == ()
    assert result.report.unlinked_ambiguity_keys == 1
    assert result.report.unlinked_keys == ("wug/NOUN",)


def test_same_ipa_across_entries_is_not_ambiguous():
    result = discover_ambiguities(
        [
            entry("wug", "noun", "wʌg", "a bird", "sense-a"),
            entry("wug", "noun", "/wʌg/", "a type of bird", "sense-b"),
        ],
        language="en",
    )

    assert result.index.profiles == ()
    assert result.report.non_ambiguous_keys == 1


def test_reading_ids_do_not_depend_on_input_order():
    rows = [
        entry("wug", "noun", "wʌg", "a bird", "sense-a"),
        entry("wug", "noun", "wuːg", "a bend", "sense-b"),
    ]
    one = discover_ambiguities(rows, language="en").index
    two = discover_ambiguities(reversed(rows), language="en").index
    assert {p.reading_id for p in one.profiles} == {p.reading_id for p in two.profiles}


def test_complete_index_is_deterministic_across_evidence_input_order(tmp_path):
    rows = [
        entry("wug", "noun", "wʌg", "zebra gloss", "sense-z"),
        entry("wug", "noun", "wʌg", "alpha gloss", "sense-a"),
        entry("wug", "noun", "wuːg", "bend", "sense-b"),
    ]
    one = discover_ambiguities(rows, language="en")
    two = discover_ambiguities(reversed(rows), language="en")
    one_index = one.index
    two_index = two.index
    assert one_index.to_dict() == two_index.to_dict()
    assert one.identity_audit == two.identity_audit
    one_path = save_index(one_index, tmp_path / "one.json")
    two_path = save_index(two_index, tmp_path / "two.json")
    assert one_path.read_bytes() == two_path.read_bytes()


def test_missing_or_empty_pos_is_skipped_and_reported():
    rows = [
        entry("wug", "noun", "wʌg", "a bird", "sense-a"),
        entry("wug", "noun", "wuːg", "a bend", "sense-b"),
        entry("wug", "", "wɑg", "missing POS", "sense-c"),
    ]
    result = discover_ambiguities(rows, language="en")
    assert len(result.index.profiles) == 2
    assert result.report.entries_without_pos == 1
    assert result.report.as_dict()["entries_without_pos"] == 1


def test_report_counts_entries_without_pronunciation():
    result = discover_ambiguities(
        [{"word": "blank", "pos": "noun", "senses": []}],
        language="en",
    )
    assert result.report.entries_scanned == 1
    assert result.report.entries_without_pronunciation == 1


def test_placeholder_pronunciation_is_rejected_and_reported():
    result = discover_ambiguities(
        [
            entry("wug", "noun", "wʌg", "a bird", "sense-a"),
            entry("wug", "noun", "…", "missing pronunciation", "sense-b"),
        ],
        language="de",
    )

    assert result.index.profiles == ()
    assert result.report.invalid_pronunciation_values == 1
    assert result.report.entries_without_pronunciation == 1
    assert result.report.non_ambiguous_keys == 1


def test_placeholder_in_three_reading_group_leaves_two_profiles():
    result = discover_ambiguities(
        [
            entry("wug", "noun", "vʊk", "first reading", "sense-a"),
            entry("wug", "noun", "vuːk", "second reading", "sense-b"),
            entry("wug", "noun", "…", "missing pronunciation", "sense-c"),
        ],
        language="de",
    )

    assert {profile.ipa for profile in result.index.profiles} == {"vʊk", "vuːk"}
    assert result.report.invalid_pronunciation_values == 1
    assert result.report.resolvable_keys == 1
    assert result.report.as_dict()["invalid_pronunciation_values"] == 1


def test_punctuation_only_pronunciations_are_rejected():
    for placeholder in ("…", "...", "—", "?"):
        result = discover_ambiguities(
            [entry("wug", "noun", placeholder, "missing", "sense-a")], language="de"
        )
        assert result.index.profiles == ()
        assert result.report.invalid_pronunciation_values == 1


def test_equivalence_suppresses_only_fully_pairwise_equivalent_groups():
    class AllEquivalent:
        def equivalent(self, left, right):
            return True

    rows = [
        entry("wug", "noun", "a", "first reading", "sense-a"),
        entry("wug", "noun", "b", "second reading", "sense-b"),
    ]
    result = discover_ambiguities(
        rows,
        language="en",
        pronunciation_equivalence=AllEquivalent(),
    )

    assert result.index.profiles == ()
    assert result.report.ambiguous_keys == 1
    assert result.report.equivalent_pronunciation_keys == 1
    assert result.report.equivalence_comparisons == 1
    assert result.report.non_ambiguous_keys == 1
    assert result.report.resolvable_keys == 0


def test_equivalence_uses_complete_linkage_not_transitive_chaining():
    class ChainEquivalence:
        equivalent_pairs = {frozenset(("a", "b")), frozenset(("b", "c"))}

        def equivalent(self, left, right):
            return frozenset((left, right)) in self.equivalent_pairs

    result = discover_ambiguities(
        [
            entry("wug", "noun", "a", "first reading", "sense-a"),
            entry("wug", "noun", "b", "second reading", "sense-b"),
            entry("wug", "noun", "c", "third reading", "sense-c"),
        ],
        language="en",
        pronunciation_equivalence=ChainEquivalence(),
    )

    assert result.index.profiles == ()
    assert result.report.equivalence_comparisons == 3
    assert result.report.equivalence_unsafe_keys == 1
    assert result.unresolved[0].reason == "non_transitive_equivalence_component"


def test_equivalence_errors_fail_closed_and_are_counted():
    class BrokenEquivalence:
        def equivalent(self, left, right):
            raise ValueError("unsupported test IPA")

    result = discover_ambiguities(
        [
            entry("wug", "noun", "a", "first reading", "sense-a"),
            entry("wug", "noun", "b", "second reading", "sense-b"),
        ],
        language="en",
        pronunciation_equivalence=BrokenEquivalence(),
    )

    assert result.index.profiles == ()
    assert result.report.equivalence_comparisons == 1
    assert result.report.equivalence_errors == 1
    assert result.report.equivalence_unsafe_keys == 1
    assert result.unresolved[0].reason == "equivalence_error"


def test_phonodist_unsupported_comparison_is_audited_and_fails_closed():
    import pytest

    pytest.importorskip("phonodist")
    from pronresolve import PhonodistEquivalence

    rows = [
        entry("wug", "noun", "#p", "first reading", "sense-a"),
        entry("wug", "noun", "p", "second reading", "sense-b"),
    ]
    forward = discover_ambiguities(
        rows,
        language="de-DE",
        pronunciation_equivalence=PhonodistEquivalence("de-DE"),
        include_equivalence_audit=True,
    )
    reversed_result = discover_ambiguities(
        reversed(rows),
        language="de-DE",
        pronunciation_equivalence=PhonodistEquivalence("de-DE"),
        include_equivalence_audit=True,
    )

    assert forward.index.profiles == ()
    assert forward.report.equivalence_errors == 1
    assert forward.equivalence_audit == reversed_result.equivalence_audit
    assert "error" in forward.equivalence_audit[0]
    assert forward.unresolved[0].reason == "equivalence_error"


def test_safe_partial_equivalence_merges_only_pairwise_clique():
    class PartialEquivalence:
        def equivalent(self, left, right):
            return frozenset((left, right)) == frozenset(("a", "b"))

    result = discover_ambiguities(
        [
            entry("wug", "noun", "a", "first reading", "sense-a"),
            entry("wug", "noun", "b", "alternate form", "sense-b"),
            entry("wug", "noun", "c", "third reading", "sense-c"),
        ],
        language="en",
        pronunciation_equivalence=PartialEquivalence(),
    )

    assert len(result.index.profiles) == 2
    merged = next(
        identity for identity in result.identity_audit if identity.source_ipas == ("a", "b")
    )
    assert merged.sense_ids == ("sense-a", "sense-b")
    assert merged.semantic_anchor.keys == ("sense-a", "sense-b")
    assert all(profile.reading_id.startswith("r2-en-") for profile in result.index.profiles)


def test_bass_noun_is_the_same_pos_resolution_regression():
    fish = entry("bass", "NOUN", "bæs", "a freshwater fish", "bass-fish")
    music = entry("bass", "NOUN", "beɪs", "low musical range", "bass-music")
    first = discover_ambiguities([fish, music], language="en", locale="en-US")
    changed_fish = entry("bass", "NOUN", "bæːs", "a freshwater fish", "bass-fish")
    second = discover_ambiguities([changed_fish, music], language="en", locale="en-GB")

    assert len(first.index.profiles) == 2
    assert {profile.reading_id for profile in first.index.profiles} == {
        profile.reading_id for profile in second.index.profiles
    }
    assert all(profile.reading_id.startswith("r2-en-") for profile in first.index.profiles)


def test_pos_separated_single_readings_do_not_create_resolver_profiles():
    result = discover_ambiguities(
        [
            entry("possplit", "NOUN", "a", "noun reading", "sense-noun"),
            entry("possplit", "VERB", "b", "verb reading", "sense-verb"),
        ],
        language="en",
    )

    assert result.index.profiles == ()
    assert result.report.raw_ambiguous_keys == 0
    assert result.report.resolvable_keys == 0
    assert result.report.word_pos_keys_scanned == 2


def test_missing_semantic_anchor_is_structured_unresolved():
    result = discover_ambiguities(
        [
            {"word": "wug", "pos": "noun", "pronunciations": [{"ipa": "a"}], "senses": []},
            {"word": "wug", "pos": "noun", "pronunciations": [{"ipa": "b"}], "senses": []},
        ],
        language="en",
    )

    assert result.index.profiles == ()
    assert result.report.missing_semantic_anchor_keys == 1
    assert result.unresolved[0].reason == "missing_semantic_anchor"
    assert result.report.as_dict()["unresolved_reason_counts"] == {"missing_semantic_anchor": 1}


def test_curated_semantic_anchor_overlay_supports_entries_without_sense_ids():
    rows = [
        {
            "word": "bass",
            "pos": "NOUN",
            "source_id": "fish-row",
            "pronunciations": [{"ipa": "bæs"}],
            "senses": [{"glosses": ["a fish"]}],
        },
        {
            "word": "bass",
            "pos": "NOUN",
            "source_id": "music-row",
            "pronunciations": [{"ipa": "beɪs"}],
            "senses": [{"glosses": ["a low musical range"]}],
        },
    ]
    overlay = [
        {
            "word": "bass",
            "pos": "noun",
            "source_id": "fish-row",
            "semantic_anchor": {"namespace": "pronresolve:curated:en", "keys": ["bass-fish"]},
        },
        {
            "word": "bass",
            "pos": "noun",
            "source_id": "music-row",
            "semantic_anchor": {"namespace": "pronresolve:curated:en", "keys": ["bass-music"]},
        },
    ]

    result = discover_ambiguities(rows, language="en", curated_anchors=overlay)

    assert len(result.index.profiles) == 2
    assert {identity.semantic_anchor.namespace for identity in result.identity_audit} == {
        "pronresolve:curated:en"
    }
    assert {identity.semantic_anchor.keys for identity in result.identity_audit} == {
        ("bass-fish",),
        ("bass-music",),
    }


def test_semantic_anchor_overlap_rejects_entire_word_pos_group():
    result = discover_ambiguities(
        [
            entry("wug", "noun", "a", "first reading", "shared-sense"),
            entry("wug", "noun", "b", "second reading", "shared-sense"),
        ],
        language="en",
    )

    assert result.index.profiles == ()
    assert result.report.semantic_overlap_keys == 1
    assert result.unresolved[0].reason == "semantic_anchor_overlap"
    assert result.unresolved[0].details == {"overlapping_keys": ["shared-sense"]}


def test_discovery_removes_universal_cues_from_every_runtime_profile():
    result = discover_ambiguities(
        [
            entry("bass", "NOUN", "bæs", "a common freshwater fish", "bass-fish"),
            entry("bass", "NOUN", "beɪs", "a common low musical range", "bass-music"),
        ],
        language="en",
    )

    assert len(result.index.profiles) == 2
    assert all(
        "common" not in {cue.token for cue in profile.cues} for profile in result.index.profiles
    )


def test_discovery_rejects_identical_or_empty_contrastive_cue_maps():
    identical = discover_ambiguities(
        [
            entry("wug", "noun", "a", "common wording", "sense-a"),
            entry("wug", "noun", "b", "common wording", "sense-b"),
        ],
        language="en",
    )
    insufficient = discover_ambiguities(
        [
            entry("wug", "noun", "a", "common fish", "sense-a"),
            entry("wug", "noun", "b", "common", "sense-b"),
        ],
        language="en",
    )

    assert identical.index.profiles == ()
    assert identical.unresolved[0].reason == "non_discriminative_rules"
    assert identical.report.non_discriminative_keys == 1
    assert insufficient.index.profiles == ()
    assert insufficient.unresolved[0].reason == "insufficient_contrastive_evidence"
