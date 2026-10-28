from pronresolve import AmbiguityIndex, Resolver
from pronresolve.models import Cue, ReadingProfile
from pronresolve.normalization import STOPWORDS, normalize_word, token_spans
from pronresolve.storage import decode_v1


def profile(ipa, cues, reading_id, *, pos="NOUN"):
    return ReadingProfile(
        word="wug",
        pos=pos,
        reading_id=reading_id,
        ipa=ipa,
        sense_ids=(f"sense-{reading_id}",),
        cues=tuple(Cue(token, weight) for token, weight in cues.items()),
    )


def make_resolver():
    return Resolver(
        AmbiguityIndex(
            language="en",
            locale="en-US",
            schema_version=2,
            profiles=(
                profile("wʌg", {"aviary": 3.0}, "bird"),
                profile("wuːg", {"road": 3.0}, "bend"),
            ),
        )
    )


def test_context_selects_reading_with_precompiled_cues_and_matched_terms():
    text = "The wug flew into the aviary."
    start = text.index("wug")
    resolver = make_resolver()
    result = resolver.resolve(
        text,
        start=start,
        end=start + len("wug"),
        pos="noun",
        lemma="wug",
    )

    assert result is not None
    assert result.reading_id == "bird"
    assert result.ipa == "wʌg"
    assert result.selector == "READING:bird"
    assert result.sense_ids == ("sense-bird",)
    assert result.evidence_terms == ("aviary",)
    assert resolver._cue_maps["bird"] == {"aviary": 3.0}


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
        schema_version=2,
        profiles=(
            profile("wʌg", {"aviary": 3.0}, "noun-a"),
            profile("wuːg", {"road": 3.0}, "noun-b"),
            profile("wʌg", {"quickly": 3.0}, "verb-a", pos="VERB"),
            profile("wuːg", {"curve": 3.0}, "verb-b", pos="VERB"),
        ),
    )
    text = "The wug flew into the aviary."
    assert Resolver(index).resolve(text, start=4, end=7, lemma="wug") is None


def test_bad_offsets_return_none():
    text = "The wug flew."
    assert make_resolver().resolve(text, start=-1, end=2, lemma="wug") is None
    assert make_resolver().resolve(text, start=5, end=4, lemma="wug") is None


def test_thresholds_ties_unknown_words_and_wrong_pos_abstain():
    resolver = make_resolver()
    text = "The wug flew into the aviary."
    start = text.index("wug")
    args = {"start": start, "end": start + 3, "pos": "NOUN", "lemma": "wug"}
    assert Resolver(resolver.index, min_score=100).resolve(text, **args) is None
    assert Resolver(resolver.index, min_margin=100).resolve(text, **args) is None
    assert resolver.resolve("The wug is here.", start=4, end=7, pos="NOUN", lemma="wug") is None
    assert resolver.resolve("The unknown flew into the aviary.", start=4, end=11) is None
    assert resolver.resolve("wug aviary", start=0, end=3, pos="ADJ", lemma="wug") is None


def test_tied_candidates_abstain_and_single_candidate_is_never_emitted():
    tied = AmbiguityIndex(
        language="en",
        locale=None,
        schema_version=2,
        profiles=(
            profile("a", {"shared": 3.0}, "a"),
            profile("b", {"shared": 3.0}, "b"),
        ),
    )
    assert Resolver(tied).resolve("wug shared", start=0, end=3, pos="NOUN", lemma="wug") is None

    single = AmbiguityIndex(
        language="en",
        locale=None,
        schema_version=2,
        profiles=(profile("a", {"shared": 3.0}, "only"),),
    )
    assert Resolver(single).resolve("wug shared", start=0, end=3, pos="NOUN", lemma="wug") is None

    three = AmbiguityIndex(
        language="en",
        locale=None,
        schema_version=2,
        profiles=(
            profile("a", {"aviary": 3.0}, "a"),
            profile("b", {"road": 3.0}, "b"),
            profile("c", {"nest": 3.0}, "nest"),
        ),
    )
    result = Resolver(three).resolve("wug aviary", start=0, end=3, pos="NOUN", lemma="wug")
    assert result is not None


def test_pos_filter_unicode_casefold_and_token_adapter():
    resolver = make_resolver()
    result = resolver.resolve("WUG AVIARY", start=0, end=3, pos="noun", lemma="WUG")
    assert result is not None and result.reading_id == "bird"

    mapping = {"start_char": 4, "text": "wug", "pos": "NOUN", "lemma": "wug"}
    assert resolver.resolve_token("The wug flew into the aviary.", mapping).reading_id == "bird"

    class Token:
        pass

    Token.idx = 4
    Token.text = "wug"
    Token.lemma_ = "wug"
    Token.pos_ = "NOUN"
    assert resolver.resolve_token("The wug flew into the aviary.", Token()).reading_id == "bird"


def test_equal_scores_are_ordered_by_reading_id_and_report_matched_cues():
    tied = AmbiguityIndex(
        language="en",
        locale=None,
        schema_version=2,
        profiles=(
            profile("a", {"shared": 3.0}, "z-reading"),
            profile("b", {"shared": 3.0}, "a-reading"),
        ),
    )
    result = Resolver(tied, min_margin=0).resolve(
        "wug shared", start=0, end=3, pos="NOUN", lemma="wug"
    )
    assert result is not None
    assert [candidate.reading_id for candidate in result.candidates] == ["a-reading", "z-reading"]
    assert result.reading_id == "a-reading"
    assert result.evidence_terms == ("shared",)


def test_example_only_context_has_no_compiled_score():
    index = AmbiguityIndex(
        language="en",
        locale=None,
        schema_version=2,
        profiles=(
            profile("a", {"aviary": 3.0}, "a"),
            profile("b", {"road": 3.0}, "b"),
        ),
    )
    text = "wug quizzicalexamplecue"
    assert Resolver(index).resolve(text, start=0, end=3, pos="NOUN", lemma="wug") is None


def _policy_b_reference_score(profile, text, start, end):
    spans = token_spans(text)
    target_word = normalize_word(text[start:end])
    target_index = next(
        (index for index, span in enumerate(spans) if span.start < end and span.end > start),
        sum(1 for span in spans if span.end <= start),
    )
    nearest = {}
    for index, span in enumerate(spans):
        if span.start < end and span.end > start:
            continue
        if span.normalized in STOPWORDS or span.normalized == target_word:
            continue
        distance = abs(index - target_index)
        nearest[span.normalized] = min(nearest.get(span.normalized, distance), distance)
    cue_weights = {cue.token: cue.weight for cue in profile.cues}
    score = sum(
        cue_weights.get(token, 0.0) / (1.0 + 0.15 * max(distance - 1, 0))
        for token, distance in nearest.items()
    )
    return round(score, 6)


def test_v1_resolution_scores_match_policy_b_reference_not_legacy_examples():
    legacy = {
        "schema_version": 1,
        "language": "en",
        "locale": None,
        "profiles": [
            {
                "word": "read",
                "pos": "VERB",
                "reading_id": "read-cue",
                "ipa": ["ɹiːd"],
                "sense_ids": ["s1"],
                "synonyms": ["interpret"],
                "glosses": ["comprehend"],
                "topics": ["communication"],
                "tags": ["transitive"],
                "antonyms": ["ignore"],
                "examples": ["exampleonlycue"],
            },
            {
                "word": "read",
                "pos": "VERB",
                "reading_id": "read-other",
                "ipa": ["ɹɛd"],
                "sense_ids": ["s2"],
                "glosses": ["unrelated"],
            },
        ],
    }
    index = decode_v1(legacy)
    resolver = Resolver(index, min_score=0, min_margin=0)
    text = "read interpret comprehend communication transitive ignore exampleonlycue"
    result = resolver.resolve(text, start=0, end=4, pos="VERB", lemma="read")

    assert result is not None
    expected = {
        profile.reading_id: _policy_b_reference_score(profile, text, 0, 4)
        for profile in index.profiles
    }
    actual = {candidate.reading_id: candidate.score for candidate in result.candidates}
    assert actual == expected
    assert result.reading_id == "read-cue"
    assert "exampleonlycue" not in result.evidence_terms
