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
