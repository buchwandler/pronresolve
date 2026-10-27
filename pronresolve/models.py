"""Immutable runtime data models and schema-v2 conversion."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .normalization import normalize_ipa, normalize_pos, normalize_word, tokens

INDEX_SCHEMA_VERSION = 2


def _required_string(value: Mapping[str, Any], field: str, path: str) -> str:
    if field not in value:
        raise ValueError(f"{path}.{field} is required")
    item = value[field]
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{path}.{field} must be a non-empty string")
    return item.strip()


def _string_array(value: Mapping[str, Any], field: str, path: str) -> tuple[str, ...]:
    if field not in value:
        return ()
    items = value[field]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError(f"{path}.{field} must be an array of strings")
    return tuple(items)


def _weight_key(weight: float) -> str:
    return str(int(weight)) if weight.is_integer() else format(weight, ".15g")


def _parsed_weight(value: Any, path: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a numeric cue weight")
    try:
        weight = float(value)
    except ValueError as exc:
        raise ValueError(f"{path} must be a numeric cue weight") from exc
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError(f"{path} must be a finite positive cue weight")
    return weight


@dataclass(frozen=True, slots=True)
class Cue:
    """One normalized runtime token and its maximum evidence weight."""

    token: str
    weight: float

    def __post_init__(self) -> None:
        if not isinstance(self.token, str):
            raise ValueError("cue.token must be a string")
        token = normalize_word(self.token)
        if not token or tokens(token) != (token,):
            raise ValueError("cue.token must be one non-empty normalized token")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise ValueError("cue.weight must be a finite positive number")
        weight = float(self.weight)
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("cue.weight must be a finite positive number")
        from .compile import EVIDENCE_WEIGHTS

        if weight not in set(EVIDENCE_WEIGHTS.values()):
            raise ValueError("cue.weight is not defined by the Policy B scoring policy")
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "weight", weight)


@dataclass(frozen=True, slots=True)
class ReadingProfile:
    """Lean runtime profile for one pronunciation and its compiled lexical cues."""

    word: str
    pos: str
    reading_id: str
    ipa: str
    sense_ids: tuple[str, ...] = ()
    cues: tuple[Cue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.word, str) or not normalize_word(self.word):
            raise ValueError("profile.word must be a non-empty string")
        if not isinstance(self.pos, str) or not self.pos.strip():
            raise ValueError("profile.pos must be a non-empty string")
        if not isinstance(self.reading_id, str) or not self.reading_id.strip():
            raise ValueError("profile.reading_id must be a non-empty string")
        if not isinstance(self.ipa, str):
            raise ValueError("profile.ipa must be a non-empty scalar string")
        ipa = normalize_ipa(self.ipa)
        if not ipa:
            raise ValueError("profile.ipa must be a non-empty scalar string")
        if not isinstance(self.sense_ids, tuple) or any(
            not isinstance(item, str) for item in self.sense_ids
        ):
            raise ValueError("profile.sense_ids must be a tuple of strings")
        if not isinstance(self.cues, tuple) or any(not isinstance(item, Cue) for item in self.cues):
            raise ValueError("profile.cues must be a tuple of Cue values")
        tokens_seen = [cue.token for cue in self.cues]
        if len(tokens_seen) != len(set(tokens_seen)):
            raise ValueError("profile.cues must not contain duplicate tokens")
        object.__setattr__(self, "word", normalize_word(self.word))
        object.__setattr__(self, "pos", normalize_pos(self.pos))
        object.__setattr__(self, "reading_id", self.reading_id.strip())
        object.__setattr__(self, "ipa", ipa)
        object.__setattr__(self, "sense_ids", tuple(sorted(set(self.sense_ids))))
        object.__setattr__(self, "cues", tuple(sorted(self.cues, key=lambda cue: cue.token)))

    def to_dict(self) -> dict[str, Any]:
        grouped: dict[str, list[str]] = {}
        for cue in self.cues:
            grouped.setdefault(_weight_key(cue.weight), []).append(cue.token)
        return {
            "id": self.reading_id,
            "ipa": self.ipa,
            "sense_ids": list(self.sense_ids),
            "cues": {weight: sorted(values) for weight, values in sorted(grouped.items())},
        }


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
        if not isinstance(self.language, str) or not normalize_word(self.language):
            raise ValueError("index.language must be a non-empty string")
        if self.locale is not None and (
            not isinstance(self.locale, str) or not self.locale.strip()
        ):
            raise ValueError("index.locale must be a non-empty string or null")
        if not isinstance(self.profiles, tuple) or any(
            not isinstance(profile, ReadingProfile) for profile in self.profiles
        ):
            raise ValueError("index.profiles must be a tuple of ReadingProfile values")
        object.__setattr__(self, "language", normalize_word(self.language))
        if self.locale is not None:
            object.__setattr__(self, "locale", self.locale.strip())
        object.__setattr__(
            self,
            "profiles",
            tuple(
                sorted(
                    self.profiles,
                    key=lambda profile: (
                        profile.word,
                        profile.pos,
                        profile.ipa,
                        profile.reading_id,
                    ),
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        entries: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for profile in self.profiles:
            grouped_profiles = entries.setdefault(profile.word, {}).setdefault(profile.pos, [])
            grouped_profiles.append(profile.to_dict())
        return {
            "schema_version": INDEX_SCHEMA_VERSION,
            "language": self.language,
            "locale": self.locale,
            "entries": {
                word: {pos: profiles for pos, profiles in sorted(groups.items())}
                for word, groups in sorted(entries.items())
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AmbiguityIndex:
        if not isinstance(value, Mapping):
            raise ValueError("ambiguity index root must be a JSON object")
        version = value.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("schema_version must be an integer")
        if version != INDEX_SCHEMA_VERSION:
            raise ValueError(f"unsupported ambiguity index schema {version}")
        language = _required_string(value, "language", "index")
        if "locale" not in value:
            raise ValueError("index.locale is required")
        locale = value["locale"]
        if locale is not None and (not isinstance(locale, str) or not locale.strip()):
            raise ValueError("index.locale must be a non-empty string or null")
        entries = value.get("entries")
        if not isinstance(entries, Mapping):
            raise ValueError("index.entries must be a JSON object")

        profiles: list[ReadingProfile] = []
        seen_ids: set[str] = set()
        seen_words: set[str] = set()
        for raw_word, raw_groups in entries.items():
            if not isinstance(raw_word, str) or not normalize_word(raw_word):
                raise ValueError("index.entries contains an empty or invalid word key")
            word = normalize_word(raw_word)
            if word in seen_words:
                raise ValueError(f"index.entries contains duplicate normalized word {word!r}")
            seen_words.add(word)
            if not isinstance(raw_groups, Mapping) or not raw_groups:
                raise ValueError(f"entries[{raw_word!r}] must be a non-empty POS object")
            seen_pos: set[str] = set()
            for raw_pos, raw_candidates in raw_groups.items():
                if not isinstance(raw_pos, str) or not raw_pos.strip():
                    raise ValueError(f"entries[{raw_word!r}] contains an empty POS key")
                pos = normalize_pos(raw_pos)
                if pos in seen_pos:
                    raise ValueError(
                        f"entries[{raw_word!r}] contains duplicate normalized POS {pos!r}"
                    )
                seen_pos.add(pos)
                if not isinstance(raw_candidates, list) or len(raw_candidates) < 2:
                    raise ValueError(
                        f"entries[{raw_word!r}][{raw_pos!r}] must contain at least two candidates"
                    )
                for position, raw_profile in enumerate(raw_candidates):
                    path = f"entries[{raw_word!r}][{raw_pos!r}][{position}]"
                    if not isinstance(raw_profile, Mapping):
                        raise ValueError(f"{path} must be a JSON object")
                    reading_id = _required_string(raw_profile, "id", path)
                    if reading_id in seen_ids:
                        raise ValueError(f"{path}.id duplicates reading ID {reading_id!r}")
                    seen_ids.add(reading_id)
                    ipa = _required_string(raw_profile, "ipa", path)
                    sense_ids = _string_array(raw_profile, "sense_ids", path)
                    raw_cues = raw_profile.get("cues")
                    if not isinstance(raw_cues, Mapping):
                        raise ValueError(f"{path}.cues must be a JSON object")
                    from .compile import EVIDENCE_WEIGHTS

                    allowed_weights = set(EVIDENCE_WEIGHTS.values())
                    cue_values: list[Cue] = []
                    seen_tokens: set[str] = set()
                    for raw_weight, raw_tokens in raw_cues.items():
                        weight = _parsed_weight(raw_weight, f"{path}.cues weight")
                        if weight not in allowed_weights:
                            raise ValueError(f"{path}.cues has unsupported weight {raw_weight!r}")
                        if not isinstance(raw_tokens, list):
                            raise ValueError(f"{path}.cues[{raw_weight!r}] must be an array")
                        for raw_token in raw_tokens:
                            if not isinstance(raw_token, str) or not raw_token.strip():
                                raise ValueError(
                                    f"{path}.cues contains a non-string or empty token"
                                )
                            token = normalize_word(raw_token)
                            if tokens(token) != (token,):
                                raise ValueError(
                                    f"{path}.cues contains invalid cue token {raw_token!r}"
                                )
                            if token in seen_tokens:
                                raise ValueError(
                                    f"{path}.cues assigns token {token!r} more than once"
                                )
                            seen_tokens.add(token)
                            cue_values.append(Cue(token, weight))
                    profiles.append(
                        ReadingProfile(
                            word=word,
                            pos=pos,
                            reading_id=reading_id,
                            ipa=ipa,
                            sense_ids=sense_ids,
                            cues=tuple(cue_values),
                        )
                    )
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
    ipa: str
    sense_ids: tuple[str, ...]
    score: float
    margin: float
    evidence_terms: tuple[str, ...]
    candidates: tuple[CandidateScore, ...]

    @property
    def selector(self) -> str:
        return f"READING:{self.reading_id}"
