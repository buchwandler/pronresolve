"""Small, dependency-free text normalization helpers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)

# Generic function words only; this is not a word- or heteronym-specific list.
STOPWORDS = frozenset(
    """
    a an and are as at be been being but by can could did do does for from had has have he her
    hers him his how i if in into is it its may me might must my no nor not of on once only or
    other our ours out over own same she should so some such than that the their theirs them
    then there these they this those through to too under until up very was we were what when
    where which while who whom why will with would you your yours
    """.split()
)


def normalize_word(value: str) -> str:
    return unicodedata.normalize("NFC", str(value)).casefold().strip()


def normalize_pos(value: str | None) -> str:
    normalized = " ".join(unicodedata.normalize("NFC", str(value or "")).strip().split())
    return normalized.upper() if normalized else "ENTRY"


def normalize_ipa(value: str) -> str:
    normalized = unicodedata.normalize("NFC", str(value or "")).strip()
    if len(normalized) >= 2 and (
        (normalized[0] == "[" and normalized[-1] == "]")
        or (normalized[0] == "/" and normalized[-1] == "/")
    ):
        normalized = normalized[1:-1]
    return normalized.strip()


def tokens(value: str) -> tuple[str, ...]:
    return tuple(normalize_word(match.group(0)) for match in _WORD_RE.finditer(value or ""))


@dataclass(frozen=True, slots=True)
class TokenSpan:
    text: str
    normalized: str
    start: int
    end: int


def token_spans(value: str) -> tuple[TokenSpan, ...]:
    return tuple(
        TokenSpan(
            text=match.group(0),
            normalized=normalize_word(match.group(0)),
            start=match.start(),
            end=match.end(),
        )
        for match in _WORD_RE.finditer(value or "")
    )
