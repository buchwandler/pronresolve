import unicodedata

from pronresolve.normalization import (
    normalize_ipa,
    normalize_pos,
    normalize_word,
    token_spans,
    tokens,
)


def test_nfc_and_casefold_word_normalization():
    composed = "CAFÉ"
    decomposed = unicodedata.normalize("NFD", composed)
    assert normalize_word(decomposed) == "café"


def test_ipa_brackets_and_slashes_are_removed():
    assert normalize_ipa("/wʌg/") == "wʌg"
    assert normalize_ipa("[wʌg]") == "wʌg"


def test_pos_normalization_and_empty_fallback():
    assert normalize_pos(" common noun ") == "COMMON NOUN"
    assert normalize_pos("") == "ENTRY"


def test_unicode_apostrophes_and_token_offsets():
    text = "l’été café"
    assert tokens(text) == ("l’été", "café")
    spans = token_spans(text)
    assert [(span.text, span.start, span.end) for span in spans] == [
        ("l’été", 0, 5),
        ("café", 6, 10),
    ]
