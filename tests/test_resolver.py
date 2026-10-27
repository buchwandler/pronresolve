from pronresolve import AmbiguityIndex, ReadingProfile, Resolver


def profile(ipa, gloss, reading_id):
    return ReadingProfile(
        word="wug",
        pos="NOUN",
        reading_id=reading_id,
        ipa=(ipa,),
        sense_ids=(f"sense-{reading_id}",),
        glosses=(gloss,),
    )


def make_resolver():
    return Resolver(
        AmbiguityIndex(
            language="en",
            locale="en-US",
            profiles=(
                profile("wʌg", "a small bird used in an aviary", "bird"),
                profile("wuːg", "a bend or curve in a road", "bend"),
            ),
        )
    )


def test_context_selects_reading_with_matching_gloss_evidence():
    text = "The wug flew into the aviary."
    start = text.index("wug")
    result = make_resolver().resolve(
        text,
        start=start,
        end=start + len("wug"),
        pos="noun",
        lemma="wug",
    )

    assert result is not None
    assert result.reading_id == "bird"
    assert result.ipa == ("wʌg",)
    assert result.selector == "READING:bird"
    assert "aviary" in result.evidence_terms


def test_weak_or_missing_context_returns_none():
    text = "The wug is here."
    start = text.index("wug")
    result = make_resolver().resolve(
        text,
        start=start,
        end=start + len("wug"),
        pos="NOUN",
        lemma="wug",
    )
    assert result is None


def test_missing_pos_with_multiple_pos_groups_returns_none():
    index = AmbiguityIndex(
        language="en",
        locale=None,
        profiles=(
            profile("wʌg", "a small bird", "noun-a"),
            profile("wuːg", "a bend in a road", "noun-b"),
            ReadingProfile(
                word="wug",
                pos="VERB",
                reading_id="verb-a",
                ipa=("wʌg",),
                glosses=("to move quickly",),
            ),
            ReadingProfile(
                word="wug",
                pos="VERB",
                reading_id="verb-b",
                ipa=("wuːg",),
                glosses=("to curve around",),
            ),
        ),
    )
    text = "The wug flew into the aviary."
    start = text.index("wug")
    assert Resolver(index).resolve(text, start=start, end=start + 3, lemma="wug") is None


def test_bad_offsets_return_none():
    text = "The wug flew."
    assert make_resolver().resolve(text, start=-1, end=2, lemma="wug") is None


def test_thresholds_ties_unknown_and_weak_context_abstain():
    resolver = make_resolver()
    text = "The wug flew into the aviary."
    start = text.index("wug")
    args = {"start": start, "end": start + 3, "pos": "NOUN", "lemma": "wug"}
    assert Resolver(resolver.index, min_score=100).resolve(text, **args) is None
    assert Resolver(resolver.index, min_margin=100).resolve(text, **args) is None
    assert resolver.resolve("The wug is here.", start=4, end=7, pos="NOUN", lemma="wug") is None
    assert resolver.resolve("The unknown flew into the aviary.", start=4, end=11) is None


def test_tied_candidates_abstain_and_three_candidates_are_supported():
    index = make_resolver().index
    tied = AmbiguityIndex(
        language="en",
        locale=None,
        profiles=(
            profile("a", "shared aviary", "a"),
            profile("b", "shared aviary", "b"),
        ),
    )
    assert Resolver(tied).resolve("wug shared", start=0, end=3, pos="NOUN", lemma="wug") is None
    three = AmbiguityIndex(
        language=index.language,
        locale=index.locale,
        profiles=(*index.profiles, profile("wʊg", "a nest", "nest")),
    )
    assert (
        Resolver(three).resolve("wug aviary", start=0, end=3, pos="NOUN", lemma="wug") is not None
    )


def test_pos_filter_and_unicode_casefold_resolution():
    resolver = make_resolver()
    assert resolver.resolve("wug aviary", start=0, end=3, pos="ADJ", lemma="wug") is None
    assert (
        resolver.resolve("WUG AVIARY", start=0, end=3, pos="noun", lemma="WUG").reading_id == "bird"
    )


def test_resolve_token_mapping_and_spacy_like_object():
    resolver = make_resolver()
    text = "The wug flew into the aviary."
    start = text.index("wug")
    mapping = {"start_char": start, "text": "wug", "pos": "NOUN", "lemma": "wug"}
    assert resolver.resolve_token(text, mapping).reading_id == "bird"

    class Token:
        pass

    Token.idx = start
    Token.text = "wug"
    Token.lemma_ = "wug"
    Token.pos_ = "NOUN"

    assert resolver.resolve_token(text, Token()).reading_id == "bird"


def test_equal_score_candidates_are_ordered_by_reading_id():
    tied = AmbiguityIndex(
        language="en",
        locale=None,
        profiles=(
            profile("a", "shared aviary", "z-reading"),
            profile("b", "shared aviary", "a-reading"),
        ),
    )
    result = Resolver(tied, min_margin=0).resolve(
        "wug shared", start=0, end=3, pos="NOUN", lemma="wug"
    )
    assert result is not None
    assert [candidate.reading_id for candidate in result.candidates] == ["a-reading", "z-reading"]
    assert result.reading_id == "a-reading"


def test_context_evidence_in_multiple_fields_counts_once_at_strongest_weight():
    base = profile("a", "aviary", "a")
    enriched = ReadingProfile(
        word=base.word,
        pos=base.pos,
        reading_id=base.reading_id,
        ipa=base.ipa,
        glosses=base.glosses,
        synonyms=("aviary",),
    )
    other = profile("b", "road", "b")
    plain = Resolver(AmbiguityIndex("en", None, (base, other))).resolve(
        "wug aviary", start=0, end=3, pos="NOUN", lemma="wug"
    )
    rich = Resolver(AmbiguityIndex("en", None, (enriched, other))).resolve(
        "wug aviary", start=0, end=3, pos="NOUN", lemma="wug"
    )
    assert plain is not None and rich is not None
    assert rich.score > plain.score
    assert rich.score < plain.score * 2
