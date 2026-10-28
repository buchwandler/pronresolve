"""Immutable runtime data models and schema-v2 conversion."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .normalization import (
    _is_pronunciation_candidate,
    normalize_ipa,
    normalize_pos,
    normalize_word,
    tokens,
)

INDEX_SCHEMA_VERSION = 3

READING_ID_VERSION = 2
_R2_ID_RE = re.compile(r"r2-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{24}")


def is_reading_id_v2(value: object) -> bool:
    """Return whether value is a well-formed semantic reading ID."""
    return isinstance(value, str) and _R2_ID_RE.fullmatch(value) is not None


def _opaque_identity_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"semantic anchor {field} values must be strings")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError(f"semantic anchor {field} values must be non-empty")
    return normalized


@dataclass(frozen=True, slots=True)
class SemanticAnchor:
    """Stable semantic identity for one pronunciation-resolution class."""

    namespace: str
    keys: tuple[str, ...]

    def __post_init__(self) -> None:
        namespace = _opaque_identity_text(self.namespace, "namespace")
        if not isinstance(self.keys, tuple) or any(not isinstance(key, str) for key in self.keys):
            raise ValueError("semantic anchor keys must be a tuple of strings")
        keys = tuple(sorted({_opaque_identity_text(key, "key") for key in self.keys}))
        if not keys:
            raise ValueError("semantic anchor requires at least one key")
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "keys", keys)

    def to_dict(self) -> dict[str, object]:
        return {"namespace": self.namespace, "keys": list(self.keys)}


@dataclass(frozen=True, slots=True)
class SemanticIdentity:
    """Build-time provenance explaining the semantic identity of an r2 class."""

    reading_id: str
    word: str
    pos: str
    semantic_anchor: SemanticAnchor
    sense_ids: tuple[str, ...]
    source_ipas: tuple[str, ...]
    anchor_ipa: str

    def __post_init__(self) -> None:
        if not is_reading_id_v2(self.reading_id):
            raise ValueError("semantic identity reading_id must be a well-formed r2 ID")
        if not isinstance(self.word, str) or not normalize_word(self.word):
            raise ValueError("semantic identity word must be non-empty")
        if not isinstance(self.pos, str) or not self.pos.strip():
            raise ValueError("semantic identity POS must be non-empty")
        if not isinstance(self.semantic_anchor, SemanticAnchor):
            raise ValueError("semantic identity requires a SemanticAnchor")
        if not isinstance(self.sense_ids, tuple):
            raise ValueError("semantic identity sense_ids must be a tuple")
        sense_ids = tuple(
            sorted({_opaque_identity_text(item, "sense_id") for item in self.sense_ids})
        )
        if not isinstance(self.source_ipas, tuple) or any(
            not isinstance(item, str) for item in self.source_ipas
        ):
            raise ValueError("semantic identity source_ipas must be a tuple of strings")
        source_ipas = tuple(sorted({normalize_ipa(item) for item in self.source_ipas} - {""}))
        if not source_ipas or any(not _is_pronunciation_candidate(item) for item in source_ipas):
            raise ValueError("semantic identity requires valid source IPA values")
        anchor_ipa = normalize_ipa(self.anchor_ipa) if isinstance(self.anchor_ipa, str) else ""
        if anchor_ipa != source_ipas[0]:
            raise ValueError("semantic identity anchor_ipa must be the first sorted source IPA")
        object.__setattr__(self, "reading_id", self.reading_id.strip())
        object.__setattr__(self, "word", normalize_word(self.word))
        object.__setattr__(self, "pos", normalize_pos(self.pos))
        object.__setattr__(self, "sense_ids", sense_ids)
        object.__setattr__(self, "source_ipas", source_ipas)
        object.__setattr__(self, "anchor_ipa", anchor_ipa)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.reading_id,
            "word": self.word,
            "pos": self.pos,
            "semantic_anchor": self.semantic_anchor.to_dict(),
            "sense_ids": list(self.sense_ids),
            "source_ipas": list(self.source_ipas),
            "anchor_ipa": self.anchor_ipa,
        }


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


@dataclass(frozen=True, slots=True, init=False)
class ReadingProfile:
    """Lean runtime profile for one semantic resolution class."""

    word: str
    pos: str
    reading_id: str
    anchor_ipa: str
    sense_ids: tuple[str, ...] = ()
    cues: tuple[Cue, ...] = ()

    def __init__(
        self,
        word: str,
        pos: str,
        reading_id: str,
        anchor_ipa: str | None = None,
        sense_ids: tuple[str, ...] = (),
        cues: tuple[Cue, ...] = (),
        *,
        ipa: str | None = None,
    ) -> None:
        if anchor_ipa is None:
            anchor_ipa = ipa
        elif ipa is not None and ipa != anchor_ipa:
            raise ValueError("ipa and anchor_ipa compatibility arguments disagree")
        object.__setattr__(self, "word", word)
        object.__setattr__(self, "pos", pos)
        object.__setattr__(self, "reading_id", reading_id)
        object.__setattr__(self, "anchor_ipa", anchor_ipa)
        object.__setattr__(self, "sense_ids", sense_ids)
        object.__setattr__(self, "cues", cues)
        self.__post_init__()

    @property
    def ipa(self) -> str:
        """Deprecated compatibility alias for the diagnostic anchor IPA."""
        return self.anchor_ipa

    def __post_init__(self) -> None:
        if not isinstance(self.word, str) or not normalize_word(self.word):
            raise ValueError("profile.word must be a non-empty string")
        if not isinstance(self.pos, str) or not self.pos.strip():
            raise ValueError("profile.pos must be a non-empty string")
        if not isinstance(self.reading_id, str) or not self.reading_id.strip():
            raise ValueError("profile.reading_id must be a non-empty string")
        if not isinstance(self.anchor_ipa, str):
            raise ValueError("profile.anchor_ipa must be a non-empty scalar string")
        anchor_ipa = normalize_ipa(self.anchor_ipa)
        if not anchor_ipa:
            raise ValueError("profile.anchor_ipa must be a non-empty scalar string")
        if not _is_pronunciation_candidate(anchor_ipa):
            raise ValueError("profile.anchor_ipa must contain a segment-like Unicode letter")
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
        object.__setattr__(self, "anchor_ipa", anchor_ipa)
        if self.reading_id.startswith("r2-") and not is_reading_id_v2(self.reading_id):
            raise ValueError("profile.reading_id must be a well-formed r2 ID")
        object.__setattr__(self, "sense_ids", tuple(sorted(set(self.sense_ids))))
        object.__setattr__(self, "cues", tuple(sorted(self.cues, key=lambda cue: cue.token)))

    def to_dict(self) -> dict[str, Any]:
        grouped: dict[str, list[str]] = {}
        for cue in self.cues:
            grouped.setdefault(_weight_key(cue.weight), []).append(cue.token)
        return {
            "id": self.reading_id,
            "anchor_ipa": self.anchor_ipa,
            "cues": {weight: sorted(values) for weight, values in sorted(grouped.items())},
        }

    def to_v2_dict(self) -> dict[str, Any]:
        grouped = self.to_dict()["cues"]
        return {
            "id": self.reading_id,
            "ipa": self.anchor_ipa,
            "sense_ids": list(self.sense_ids),
            "cues": grouped,
        }


@dataclass(frozen=True, slots=True)
class AmbiguityIndex:
    language: str
    locale: str | None
    profiles: tuple[ReadingProfile, ...]
    schema_version: int = INDEX_SCHEMA_VERSION
    rules_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in (2, INDEX_SCHEMA_VERSION):
            raise ValueError(f"unsupported ambiguity index schema {self.schema_version}")
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
        if self.schema_version == INDEX_SCHEMA_VERSION:
            if any(not is_reading_id_v2(profile.reading_id) for profile in self.profiles):
                raise ValueError("schema-v3 profiles must use well-formed r2 reading IDs")
            rules_id = self.rules_id
            if rules_id is None:
                rules_id = normalize_word(self.locale or self.language)
            if not isinstance(rules_id, str) or not rules_id.strip():
                raise ValueError("schema-v3 rules_id must be a non-empty string")
            object.__setattr__(self, "rules_id", rules_id.strip())
        elif self.rules_id is not None and (
            not isinstance(self.rules_id, str) or not self.rules_id.strip()
        ):
            raise ValueError("index.rules_id must be a non-empty string or null")
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
                        profile.anchor_ipa,
                        profile.reading_id,
                    ),
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        entries: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for profile in self.profiles:
            grouped_profiles = entries.setdefault(profile.word, {}).setdefault(profile.pos, [])
            grouped_profiles.append(
                profile.to_v2_dict() if self.schema_version == 2 else profile.to_dict()
            )
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "language": self.language,
            "locale": self.locale,
            "entries": {
                word: {pos: profiles for pos, profiles in sorted(groups.items())}
                for word, groups in sorted(entries.items())
            },
        }
        if self.schema_version == INDEX_SCHEMA_VERSION:
            result["id_version"] = READING_ID_VERSION
            result["rules_id"] = self.rules_id
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AmbiguityIndex:
        if not isinstance(value, Mapping):
            raise ValueError("ambiguity index root must be a JSON object")
        version = value.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("schema_version must be an integer")
        if version not in (2, INDEX_SCHEMA_VERSION):
            raise ValueError(f"unsupported ambiguity index schema {version}")
        rules_id = None
        if version == INDEX_SCHEMA_VERSION:
            id_version = value.get("id_version")
            if (
                isinstance(id_version, bool)
                or not isinstance(id_version, int)
                or id_version != READING_ID_VERSION
            ):
                raise ValueError("schema-v3 id_version must be 2")
            rules_id = _required_string(value, "rules_id", "index")
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
        ipa_field = "ipa" if version == 2 else "anchor_ipa"
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
                    if version == INDEX_SCHEMA_VERSION and not is_reading_id_v2(reading_id):
                        raise ValueError(f"{path}.id must be a well-formed r2 reading ID")
                    anchor_ipa = _required_string(raw_profile, ipa_field, path)
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
                            anchor_ipa=anchor_ipa,
                            sense_ids=sense_ids,
                            cues=tuple(cue_values),
                        )
                    )
        return cls(
            language=language,
            locale=locale,
            profiles=tuple(profiles),
            schema_version=version,
            rules_id=rules_id,
        )


@dataclass(frozen=True, slots=True)
class UnresolvedAmbiguity:
    """A detected word/POS pronunciation ambiguity that was not safely published."""

    word: str
    pos: str
    reason: str
    pronunciations: tuple[str, ...] = ()
    sense_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.word, str) or not normalize_word(self.word):
            raise ValueError("unresolved ambiguity word must be non-empty")
        if not isinstance(self.pos, str) or not self.pos.strip():
            raise ValueError("unresolved ambiguity POS must be non-empty")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("unresolved ambiguity reason must be non-empty")
        if not isinstance(self.pronunciations, tuple) or any(
            not isinstance(value, str) for value in self.pronunciations
        ):
            raise ValueError("unresolved ambiguity pronunciations must be a tuple of strings")
        if not isinstance(self.sense_ids, tuple) or any(
            not isinstance(value, str) for value in self.sense_ids
        ):
            raise ValueError("unresolved ambiguity sense_ids must be a tuple of strings")
        if self.details is not None and not isinstance(self.details, Mapping):
            raise ValueError("unresolved ambiguity details must be a mapping or null")
        object.__setattr__(self, "word", normalize_word(self.word))
        object.__setattr__(self, "pos", normalize_pos(self.pos))
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(
            self,
            "pronunciations",
            tuple(sorted({normalize_ipa(value) for value in self.pronunciations} - {""})),
        )
        object.__setattr__(
            self,
            "sense_ids",
            tuple(sorted({_opaque_identity_text(value, "sense_id") for value in self.sense_ids})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "pos": self.pos,
            "reason": self.reason,
            "pronunciations": list(self.pronunciations),
            "sense_ids": list(self.sense_ids),
            "details": dict(self.details) if self.details is not None else None,
        }


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
    invalid_pronunciation_values: int = 0
    equivalent_pronunciation_keys: int = 0
    equivalence_comparisons: int = 0
    equivalence_errors: int = 0
    equivalence_unsafe_keys: int = 0
    missing_semantic_anchor_keys: int = 0
    semantic_overlap_keys: int = 0
    non_discriminative_keys: int = 0
    runtime_profile_count: int = 0
    runtime_cue_count: int = 0
    unresolved_reason_counts: tuple[tuple[str, int], ...] = ()

    @property
    def raw_ambiguous_keys(self) -> int:
        return self.ambiguous_keys

    @property
    def word_pos_keys_scanned(self) -> int:
        return self.keys_scanned

    @property
    def equivalent_only_keys(self) -> int:
        return self.equivalent_pronunciation_keys

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries_scanned": self.entries_scanned,
            "word_pos_keys_scanned": self.keys_scanned,
            "raw_ambiguous_keys": self.ambiguous_keys,
            "keys_scanned": self.keys_scanned,
            "ambiguous_keys": self.ambiguous_keys,
            "resolvable_keys": self.resolvable_keys,
            "unlinked_ambiguity_keys": self.unlinked_ambiguity_keys,
            "unlinked_keys": list(self.unlinked_keys),
            "non_ambiguous_keys": self.non_ambiguous_keys,
            "entries_without_pronunciation": self.entries_without_pronunciation,
            "entries_without_pos": self.entries_without_pos,
            "invalid_pronunciation_values": self.invalid_pronunciation_values,
            "equivalent_pronunciation_keys": self.equivalent_pronunciation_keys,
            "equivalent_only_keys": self.equivalent_pronunciation_keys,
            "equivalence_comparisons": self.equivalence_comparisons,
            "equivalence_errors": self.equivalence_errors,
            "equivalence_unsafe_keys": self.equivalence_unsafe_keys,
            "missing_semantic_anchor_keys": self.missing_semantic_anchor_keys,
            "semantic_overlap_keys": self.semantic_overlap_keys,
            "non_discriminative_keys": self.non_discriminative_keys,
            "runtime_profile_count": self.runtime_profile_count,
            "runtime_cue_count": self.runtime_cue_count,
            "unresolved_reason_counts": dict(self.unresolved_reason_counts),
        }


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    index: AmbiguityIndex
    report: DiscoveryReport
    equivalence_audit: tuple[dict[str, Any], ...] = ()
    unresolved: tuple[UnresolvedAmbiguity, ...] = ()
    identity_audit: tuple[SemanticIdentity, ...] = ()


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
    anchor_ipa: str
    sense_ids: tuple[str, ...]
    score: float
    margin: float
    evidence_terms: tuple[str, ...]
    candidates: tuple[CandidateScore, ...]

    @property
    def ipa(self) -> str:
        """Deprecated compatibility alias for the diagnostic anchor IPA."""
        return self.anchor_ipa

    @property
    def selector(self) -> str:
        return f"READING:{self.reading_id}"
