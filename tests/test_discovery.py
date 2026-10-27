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
        assert set(candidates) == {"id", "ipa", "sense_ids", "cues"}


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
    one_index = discover_ambiguities(rows, language="en").index
    two_index = discover_ambiguities(reversed(rows), language="en").index
    assert one_index.to_dict() == two_index.to_dict()
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
