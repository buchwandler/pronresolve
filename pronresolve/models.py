"""Immutable public data models and JSON schema conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Mapping

INDEX_SCHEMA_VERSION = 1


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    try:
        return tuple(str(item) for item in value if item is not None and str(item))
    except TypeError:
        return ()


@dataclass(frozen=True, slots=True)
class ReadingProfile:
    word: str
    pos: str
    reading_id: str
    ipa: tuple[str, ...]
    sense_ids: tuple[str, ...] = ()
    etymology_numbers: tuple[str, ...] = ()
    glosses: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    antonyms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "pos": self.pos,
            "reading_id": self.reading_id,
            "ipa": list(self.ipa),
            "sense_ids": list(self.sense_ids),
            "etymology_numbers": list(self.etymology_numbers),
            "glosses": list(self.glosses),
            "topics": list(self.topics),
            "tags": list(self.tags),
            "examples": list(self.examples),
            "synonyms": list(self.synonyms),
            "antonyms": list(self.antonyms),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReadingProfile:
        return cls(
            word=str(value["word"]),
            pos=str(value["pos"]),
            reading_id=str(value["reading_id"]),
            ipa=_strings(value.get("ipa")),
            sense_ids=_strings(value.get("sense_ids")),
            etymology_numbers=_strings(value.get("etymology_numbers")),
            glosses=_strings(value.get("glosses")),
            topics=_strings(value.get("topics")),
            tags=_strings(value.get("tags")),
            examples=_strings(value.get("examples")),
            synonyms=_strings(value.get("synonyms")),
            antonyms=_strings(value.get("antonyms")),
        )


@dataclass(frozen=True, slots=True)
class AmbiguityIndex:
    language: str
    locale: str | None
    profiles: tuple[ReadingProfile, ...]
    schema_version: int = INDEX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INDEX_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ambiguity index schema {self.schema_version}; "
                f"supported schema is {INDEX_SCHEMA_VERSION}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "language": self.language,
            "locale": self.locale,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AmbiguityIndex:
        version = int(value.get("schema_version", 0))
        if version != INDEX_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ambiguity index schema {version}; "
                f"supported schema is {INDEX_SCHEMA_VERSION}"
            )
        raw_profiles = value.get("profiles", ())
        if not isinstance(raw_profiles, list):
            raise ValueError("'profiles' must be a JSON array")
        profiles = tuple(
            ReadingProfile.from_dict(item) for item in raw_profiles if isinstance(item, Mapping)
        )
        return cls(
            language=str(value.get("language", "")),
            locale=str(value["locale"]) if value.get("locale") is not None else None,
            profiles=profiles,
            schema_version=version,
        )


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    entries_scanned: int
    keys_scanned: int
    ambiguous_keys: int
    resolvable_keys: int
    unlinked_ambiguity_keys: int
    non_ambiguous_keys: int
    entries_without_pronunciation: int
    unlinked_keys: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries_scanned": self.entries_scanned,
            "keys_scanned": self.keys_scanned,
            "ambiguous_keys": self.ambiguous_keys,
            "resolvable_keys": self.resolvable_keys,
            "unlinked_ambiguity_keys": self.unlinked_ambiguity_keys,
            "non_ambiguous_keys": self.non_ambiguous_keys,
            "entries_without_pronunciation": self.entries_without_pronunciation,
            "unlinked_keys": list(self.unlinked_keys),
        }


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    index: AmbiguityIndex
    report: DiscoveryReport


@dataclass(frozen=True, slots=True)
class CandidateScore:
    reading_id: str
    score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Resolution:
    word: str
    pos: str
    reading_id: str
    ipa: tuple[str, ...]
    sense_ids: tuple[str, ...]
    score: float
    margin: float
    evidence_terms: tuple[str, ...]
    candidates: tuple[CandidateScore, ...]

    @property
    def selector(self) -> str:
        return f"READING:{self.reading_id}"
