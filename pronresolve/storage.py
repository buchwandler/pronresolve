"""Versioned JSON codecs and compact persistence for ambiguity indexes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .compile import compile_cues
from .models import AmbiguityIndex, INDEX_SCHEMA_VERSION, ReadingProfile
from .normalization import normalize_ipa


def _required_string(value: Mapping[str, Any], field: str, path: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{path}.{field} must be a non-empty string")
    return item.strip()


def _string_array(
    value: Mapping[str, Any], field: str, path: str, *, required: bool = False
) -> tuple[str, ...]:
    if field not in value:
        if required:
            raise ValueError(f"{path}.{field} is required")
        return ()
    items = value[field]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError(f"{path}.{field} must be an array of strings")
    return tuple(items)


def encode_v2(index: AmbiguityIndex) -> dict[str, Any]:
    """Encode an internal index using the compact grouped schema-v2 wire format."""
    if not isinstance(index, AmbiguityIndex):
        raise TypeError("encode_v2 expects an AmbiguityIndex")
    payload = index.to_dict()
    # Reuse the strict decoder to enforce emitted-group and ID/cue invariants.
    decode_v2(payload)
    return payload


def decode_v2(value: Mapping[str, Any]) -> AmbiguityIndex:
    """Validate and decode a schema-v2 payload into canonical runtime models."""
    return AmbiguityIndex.from_dict(value)


def decode_v1(value: Mapping[str, Any]) -> AmbiguityIndex:
    """Decode rich v1 profiles, compiling Policy B cues and dropping raw evidence."""
    if not isinstance(value, Mapping):
        raise ValueError("ambiguity index root must be a JSON object")
    version = value.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("schema_version must be an integer")
    if version != 1:
        raise ValueError(f"unsupported ambiguity index schema {version}; expected schema 1")

    language = _required_string(value, "language", "index")
    if "locale" not in value:
        raise ValueError("index.locale is required")
    locale = value["locale"]
    if locale is not None and (not isinstance(locale, str) or not locale.strip()):
        raise ValueError("index.locale must be a non-empty string or null")
    raw_profiles = value.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("index.profiles must be a JSON array")

    profiles: list[ReadingProfile] = []
    seen_ids: set[str] = set()
    evidence_fields = ("synonyms", "glosses", "topics", "tags", "antonyms")
    legacy_array_fields = (
        "sense_ids",
        "etymology_numbers",
        "glosses",
        "topics",
        "tags",
        "examples",
        "synonyms",
        "antonyms",
    )
    for position, raw_profile in enumerate(raw_profiles):
        path = f"profiles[{position}]"
        if not isinstance(raw_profile, Mapping):
            raise ValueError(f"{path} must be a JSON object")
        word = _required_string(raw_profile, "word", path)
        pos = _required_string(raw_profile, "pos", path)
        reading_id = _required_string(raw_profile, "reading_id", path)
        if reading_id in seen_ids:
            raise ValueError(f"{path}.reading_id duplicates reading ID {reading_id!r}")
        seen_ids.add(reading_id)

        raw_ipa = _string_array(raw_profile, "ipa", path, required=True)
        if not raw_ipa or any(not item.strip() for item in raw_ipa):
            raise ValueError(f"{path}.ipa must be a non-empty array of non-empty strings")
        ipa_values = tuple(sorted({normalize_ipa(item) for item in raw_ipa} - {""}))
        if len(ipa_values) != 1:
            raise ValueError(f"{path}.ipa must identify exactly one non-empty pronunciation")

        legacy_evidence = {
            field: _string_array(raw_profile, field, path) for field in legacy_array_fields
        }
        cues = compile_cues({field: legacy_evidence[field] for field in evidence_fields})
        profiles.append(
            ReadingProfile(
                word=word,
                pos=pos,
                reading_id=reading_id,
                ipa=ipa_values[0],
                sense_ids=legacy_evidence["sense_ids"],
                cues=cues,
            )
        )

    return AmbiguityIndex(language=language, locale=locale, profiles=tuple(profiles))


def save_index(index: AmbiguityIndex, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    payload = encode_v2(index)
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_index(path: str | Path) -> AmbiguityIndex:
    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ambiguity index root must be a JSON object")
    version = value.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("schema_version must be an integer")
    if version == 1:
        return decode_v1(value)
    if version == INDEX_SCHEMA_VERSION:
        return decode_v2(value)
    raise ValueError(f"unsupported ambiguity index schema {version}")
