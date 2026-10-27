"""Immutable public data models and JSON schema conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Mapping

INDEX_SCHEMA_VERSION = 1


def _required_string(value: Mapping[str, Any], field: str, path: str) -> str:
    if field not in value:
        raise ValueError(f"{path}.{field} is required")
    item = value[field]
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{path}.{field} must be a non-empty string")
    return item


def _string_array(value: Mapping[str, Any], field: str, path: str) -> tuple[str, ...]:
    if field not in value:
        return ()
    items = value[field]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError(f"{path}.{field} must be an array of strings")
    return tuple(items)


def _profile_strings(value: Mapping[str, Any], path: str) -> dict[str, str]:
    return {
        "word": _required_string(value, "word", path),
        "pos": _required_string(value, "pos", path),
        "reading_id": _required_string(value, "reading_id", path),
    }


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
    def from_dict(cls, value: Mapping[str, Any], *, path: str = "profile") -> ReadingProfile:
        if not isinstance(value, Mapping):
            raise ValueError(f"{path} must be a JSON object")
        fields = _profile_strings(value, path)
        ipa = _string_array(value, "ipa", path)
        if not ipa or any(not item.strip() for item in ipa):
            raise ValueError(f"{path}.ipa must be a non-empty array of strings")
        return cls(
            **fields,
            ipa=ipa,
            sense_ids=_string_array(value, "sense_ids", path),
            etymology_numbers=_string_array(value, "etymology_numbers", path),
            glosses=_string_array(value, "glosses", path),
            topics=_string_array(value, "topics", path),
            tags=_string_array(value, "tags", path),
            examples=_string_array(value, "examples", path),
            synonyms=_string_array(value, "synonyms", path),
            antonyms=_string_array(value, "antonyms", path),
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
        if not isinstance(value, Mapping):
            raise ValueError("ambiguity index root must be a JSON object")
        version = value.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("schema_version must be an integer")
        if version != INDEX_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ambiguity index schema {version}; "
                f"supported schema is {INDEX_SCHEMA_VERSION}"
            )
        language = _required_string(value, "language", "index")
        if "locale" not in value:
            raise ValueError("index.locale is required")
        locale = value["locale"]
        if locale is not None and not isinstance(locale, str):
            raise ValueError("index.locale must be a string or null")
        raw_profiles = value.get("profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError("index.profiles must be a JSON array")
        profiles: list[ReadingProfile] = []
        for position, item in enumerate(raw_profiles):
            profile_path = f"profiles[{position}]"
            if not isinstance(item, Mapping):
                raise ValueError(f"{profile_path} must be a JSON object")
            profiles.append(ReadingProfile.from_dict(item, path=profile_path))
        return cls(
            language=language,
            locale=locale,
            profiles=tuple(profiles),
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
    entries_without_pos: int = 0
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
            "entries_without_pos": self.entries_without_pos,
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
