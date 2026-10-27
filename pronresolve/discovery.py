"""Discover resolvable same-spelling, same-POS pronunciation differences."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .models import AmbiguityIndex, DiscoveryReport, DiscoveryResult, ReadingProfile
from .normalization import normalize_ipa, normalize_pos, normalize_word

_LANG_RE = re.compile(r"[^a-z0-9]+")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,) if value else ()
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _unique_text(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = unicodedata.normalize("NFC", str(value or "")).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _related_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "word", "") or "")


def _example_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "text", "") or "")


def _pronunciations(entry: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    raw = _field(entry, "pronunciations")
    if raw is None:
        raw = _field(entry, "sounds", ())
    result: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for item in _as_sequence(raw):
        ipa = normalize_ipa(str(_field(item, "ipa", "") or ""))
        if not ipa or ipa in seen:
            continue
        seen.add(ipa)
        tags = _unique_text(_as_sequence(_field(item, "tags", ())))
        result.append((ipa, tags))
    return tuple(result)


def _entry_evidence(entry: Any) -> dict[str, tuple[str, ...]]:
    sense_ids: list[str] = []
    glosses: list[str] = []
    topics: list[str] = []
    tags: list[str] = []
    examples: list[str] = []
    synonyms: list[str] = []
    antonyms: list[str] = []

    for sense in _as_sequence(_field(entry, "senses", ())):
        sense_id = _field(sense, "sense_id")
        if sense_id:
            sense_ids.append(str(sense_id))
        glosses.extend(_as_sequence(_field(sense, "glosses", ())))
        topics.extend(_as_sequence(_field(sense, "topics", ())))
        tags.extend(_as_sequence(_field(sense, "tags", ())))
        examples.extend(_example_text(item) for item in _as_sequence(_field(sense, "examples", ())))
        synonyms.extend(_related_text(item) for item in _as_sequence(_field(sense, "synonyms", ())))
        antonyms.extend(_related_text(item) for item in _as_sequence(_field(sense, "antonyms", ())))

    return {
        "sense_ids": _unique_text(sense_ids),
        "etymology_numbers": _unique_text((_field(entry, "etymology_number"),)),
        "glosses": _unique_text(glosses),
        "topics": _unique_text(topics),
        "tags": _unique_text(tags),
        "examples": _unique_text(examples),
        "synonyms": _unique_text(synonyms),
        "antonyms": _unique_text(antonyms),
    }


def reading_id_for(language: str, word: str, pos: str, ipa: str) -> str:
    """Return a stable ID for a reading, independent of input order."""
    lang = _LANG_RE.sub("-", normalize_word(language)).strip("-") or "und"
    payload = json.dumps(
        [
            normalize_word(language),
            normalize_word(word),
            normalize_pos(pos),
            normalize_ipa(ipa),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.blake2s(payload, digest_size=8, person=b"prnrs1").hexdigest()
    return f"r1-{lang}-{digest}"


def discover_ambiguities(
    entries: Iterable[Any],
    *,
    language: str,
    locale: str | None = None,
) -> DiscoveryResult:
    """Scan dictionary-entry objects and create profiles only when sense linkage is safe.

    Entries can be Lexhint ``DictionaryEntry`` instances or mappings with the same
    fields. Entries are consumed once, so generators and streaming iterators work.
    """
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    entries_scanned = 0
    entries_without_pronunciation = 0

    for entry in entries:
        entries_scanned += 1
        raw_word = str(_field(entry, "word", "") or "").strip()
        if not raw_word:
            continue
        word = normalize_word(raw_word)
        pos = normalize_pos(str(_field(entry, "pos", "") or "ENTRY"))
        pronunciations = _pronunciations(entry)
        if not pronunciations:
            entries_without_pronunciation += 1
            continue
        grouped[(word, pos)].append(
            {
                "word": raw_word,
                "pronunciations": pronunciations,
                "evidence": _entry_evidence(entry),
            }
        )

    profiles: list[ReadingProfile] = []
    ambiguous_keys = 0
    resolvable_keys = 0
    unlinked_ambiguity_keys = 0
    non_ambiguous_keys = 0
    unlinked_keys: list[str] = []

    for (normalized_word, pos), entry_rows in sorted(grouped.items()):
        all_ipa = {ipa for row in entry_rows for ipa, _tags in row["pronunciations"]}
        if len(all_ipa) <= 1:
            non_ambiguous_keys += 1
            continue

        ambiguous_keys += 1

        # An entry carrying multiple IPA values does not tell us which sense maps
        # to which IPA. Do not silently attach all its senses to every reading.
        if any(len(row["pronunciations"]) != 1 for row in entry_rows):
            unlinked_ambiguity_keys += 1
            unlinked_keys.append(f"{normalized_word}/{pos}")
            continue

        by_ipa: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in entry_rows:
            ipa, _tags = row["pronunciations"][0]
            by_ipa[ipa].append(row)

        if len(by_ipa) < 2:
            non_ambiguous_keys += 1
            continue

        resolvable_keys += 1
        # The index key is normalized; using it as the profile word keeps output
        # deterministic even when the source contains case variants in different orders.
        display_word = normalized_word

        for ipa, ipa_rows in sorted(by_ipa.items()):
            merged: dict[str, list[str]] = {
                "sense_ids": [],
                "etymology_numbers": [],
                "glosses": [],
                "topics": [],
                "tags": [],
                "examples": [],
                "synonyms": [],
                "antonyms": [],
            }
            for row in ipa_rows:
                for field_name, values in row["evidence"].items():
                    merged[field_name].extend(values)
            unique = {name: _unique_text(values) for name, values in merged.items()}
            profiles.append(
                ReadingProfile(
                    word=display_word,
                    pos=pos,
                    reading_id=reading_id_for(language, normalized_word, pos, ipa),
                    ipa=(ipa,),
                    sense_ids=unique["sense_ids"],
                    etymology_numbers=unique["etymology_numbers"],
                    glosses=unique["glosses"],
                    topics=unique["topics"],
                    tags=unique["tags"],
                    examples=unique["examples"],
                    synonyms=unique["synonyms"],
                    antonyms=unique["antonyms"],
                )
            )

    profiles.sort(key=lambda profile: (normalize_word(profile.word), profile.pos, profile.ipa))
    index = AmbiguityIndex(
        language=normalize_word(language),
        locale=locale,
        profiles=tuple(profiles),
    )
    report = DiscoveryReport(
        entries_scanned=entries_scanned,
        keys_scanned=len(grouped),
        ambiguous_keys=ambiguous_keys,
        resolvable_keys=resolvable_keys,
        unlinked_ambiguity_keys=unlinked_ambiguity_keys,
        non_ambiguous_keys=non_ambiguous_keys,
        entries_without_pronunciation=entries_without_pronunciation,
        unlinked_keys=tuple(unlinked_keys),
    )
    return DiscoveryResult(index=index, report=report)
