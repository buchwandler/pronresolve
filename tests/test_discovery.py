from pronresolve import discover_ambiguities


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
    assert {profile.ipa[0] for profile in result.index.profiles} == {"wʌg", "wuːg"}
    assert {profile.word.casefold() for profile in result.index.profiles} == {"wug"}


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


def test_report_counts_entries_without_pronunciation():
    result = discover_ambiguities(
        [{"word": "blank", "pos": "noun", "senses": []}],
        language="en",
    )
    assert result.report.entries_scanned == 1
    assert result.report.entries_without_pronunciation == 1
