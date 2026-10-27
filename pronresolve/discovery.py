"""Discover resolvable same-spelling, same-POS pronunciation differences."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from itertools import combinations
from collections.abc import Iterable, Mapping
from typing import Any

from .compile import compile_cues
from .equivalence import PronunciationEquivalence
from .models import AmbiguityIndex, DiscoveryReport, DiscoveryResult, ReadingProfile
from .normalization import (
    _is_pronunciation_candidate,
    normalize_ipa,
    normalize_pos,
    normalize_word,
)

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
    return tuple(sorted(result))


def _related_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "word", "") or "")


def _example_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_field(value, "text", "") or "")


def _pronunciations(entry: Any) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], int]:
    raw = _field(entry, "pronunciations")
    if raw is None:
        raw = _field(entry, "sounds", ())
    result: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    invalid_values = 0
    for item in _as_sequence(raw):
        ipa = normalize_ipa(str(_field(item, "ipa", "") or ""))
        if not _is_pronunciation_candidate(ipa):
            invalid_values += 1
            continue
        if ipa in seen:
            continue
        seen.add(ipa)
        tags = _unique_text(_as_sequence(_field(item, "tags", ())))
        result.append((ipa, tags))
    return tuple(result), invalid_values


def _comparison_audit_record(
    word: str,
    pos: str,
    left: str,
    right: str,
    comparison: Any = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "word": word,
        "pos": pos,
        "ipa_left": left,
        "ipa_right": right,
    }
    if comparison is None:
        if error is not None:
            record["error"] = f"{type(error).__name__}: {error}"
        return record

    def event_dict(event: Any) -> dict[str, Any] | None:
        if event is None:
            return None
        return {"kind": event.kind, "anchor": event.anchor}

    record["distance"] = comparison.segmental.distance
    record["classification"] = comparison.classification
    record["stress_operations"] = [
        {
            "kind": operation.kind,
            "source": event_dict(operation.source),
            "target": event_dict(operation.target),
        }
        for operation in comparison.stress_operations
    ]
    record["alignment_operations"] = [
        {
            "kind": operation.kind,
            "source": list(operation.source),
            "target": list(operation.target),
            "cost": operation.cost,
            "reason": operation.reason,
        }
        for operation in comparison.segmental.operations
    ]
    return record


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
    pronunciation_equivalence: PronunciationEquivalence | None = None,
    include_equivalence_audit: bool = False,
) -> DiscoveryResult:
    """Scan dictionary-entry objects and create profiles only when sense linkage is safe.

    Entries can be Lexhint ``DictionaryEntry`` instances or mappings with the same
    fields. Entries are consumed once, so generators and streaming iterators work.
    """
    if include_equivalence_audit and pronunciation_equivalence is None:
        raise ValueError("equivalence audit requires a pronunciation equivalence policy")
    if include_equivalence_audit and not callable(
        getattr(pronunciation_equivalence, "evaluate", None)
    ):
        raise ValueError("equivalence audit requires a policy that exposes comparison details")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    entries_scanned = 0
    entries_without_pronunciation = 0
    invalid_pronunciation_values = 0
    entries_without_pos = 0

    for entry in entries:
        entries_scanned += 1
        raw_word = str(_field(entry, "word", "") or "").strip()
        if not raw_word:
            continue
        word = normalize_word(raw_word)
        raw_pos = str(_field(entry, "pos", "") or "").strip()
        if not raw_pos:
            entries_without_pos += 1
            continue
        pos = normalize_pos(raw_pos)
        pronunciations, invalid_values = _pronunciations(entry)
        invalid_pronunciation_values += invalid_values
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
    equivalence_comparisons = 0
    equivalence_errors = 0
    equivalent_pronunciation_keys = 0
    audit_rows: list[dict[str, Any]] = []

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

        group_audit: list[dict[str, Any]] = []
        if pronunciation_equivalence is not None:
            pair_results: list[bool] = []
            evaluate = getattr(pronunciation_equivalence, "evaluate", None)
            for left, right in combinations(sorted(by_ipa), 2):
                equivalence_comparisons += 1
                comparison = None
                try:
                    if callable(evaluate):
                        pair_equivalent, comparison = evaluate(left, right)
                    else:
                        pair_equivalent = pronunciation_equivalence.equivalent(left, right)
                except Exception as exc:
                    equivalence_errors += 1
                    pair_equivalent = False
                    if include_equivalence_audit:
                        group_audit.append(
                            _comparison_audit_record(normalized_word, pos, left, right, error=exc)
                        )
                else:
                    pair_equivalent = bool(pair_equivalent)
                    if include_equivalence_audit:
                        group_audit.append(
                            _comparison_audit_record(
                                normalized_word, pos, left, right, comparison=comparison
                            )
                        )
                pair_results.append(pair_equivalent)
            if pair_results and all(pair_results):
                equivalent_pronunciation_keys += 1
                non_ambiguous_keys += 1
                continue
            audit_rows.extend(group_audit)
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
                    ipa=ipa,
                    sense_ids=unique["sense_ids"],
                    cues=compile_cues(unique),
                )
            )

    profiles.sort(
        key=lambda profile: (
            normalize_word(profile.word),
            profile.pos,
            profile.ipa,
            profile.reading_id,
        )
    )
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
        entries_without_pos=entries_without_pos,
        unlinked_keys=tuple(unlinked_keys),
        invalid_pronunciation_values=invalid_pronunciation_values,
        equivalent_pronunciation_keys=equivalent_pronunciation_keys,
        equivalence_comparisons=equivalence_comparisons,
        equivalence_errors=equivalence_errors,
    )
    audit_rows.sort(
        key=lambda item: (
            item.get("distance", float("inf")),
            item["word"],
            item["pos"],
            item["ipa_left"],
            item["ipa_right"],
        )
    )
    return DiscoveryResult(
        index=index,
        report=report,
        equivalence_audit=tuple(audit_rows),
    )
