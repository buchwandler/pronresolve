"""Discover resolvable same-spelling, same-POS pronunciation differences."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .compile import compile_contrastive_cues, compile_cues
from .equivalence import (
    EquivalencePartition,
    PronunciationClass,
    PronunciationEquivalence,
    partition_pronunciations,
)
from .models import (
    AmbiguityIndex,
    Cue,
    DiscoveryReport,
    DiscoveryResult,
    ReadingProfile,
    SemanticAnchor,
    SemanticIdentity,
    UnresolvedAmbiguity,
)
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
    """Return a stable r1 realization ID for legacy schema compatibility."""
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


def reading_id_v2(
    language: str,
    word: str,
    pos: str,
    anchor: SemanticAnchor,
) -> str:
    """Return the deterministic semantic pronunciation-class ID (r2)."""
    if not isinstance(anchor, SemanticAnchor):
        raise TypeError("anchor must be a SemanticAnchor")
    if not isinstance(language, str):
        raise ValueError("language must be a non-empty string")
    if not isinstance(word, str):
        raise ValueError("word must be a non-empty string")
    normalized_language = normalize_word(language)
    normalized_word = normalize_word(word)
    if not normalized_language:
        raise ValueError("language must be non-empty")
    if not normalized_word:
        raise ValueError("word must be non-empty")
    if not isinstance(pos, str) or not pos.strip():
        raise ValueError("POS must be non-empty")
    normalized_pos = normalize_pos(pos)
    lang = _LANG_RE.sub("-", normalized_language).strip("-") or "und"
    payload = json.dumps(
        [
            "pronresolve-reading-v2",
            normalized_language,
            normalized_word,
            normalized_pos,
            anchor.namespace,
            list(anchor.keys),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.blake2s(payload, digest_size=12, person=b"prnrs2").hexdigest()
    return f"r2-{lang}-{digest}"


def _parse_semantic_anchor(value: Any) -> SemanticAnchor:
    if isinstance(value, SemanticAnchor):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("semantic_anchor must be an object with namespace and keys")
    namespace = value.get("namespace")
    keys = value.get("keys")
    if not isinstance(keys, (list, tuple)):
        raise ValueError("semantic_anchor.keys must be an array of strings")
    return SemanticAnchor(namespace, tuple(keys))


def _curated_anchor_overrides(
    records: Iterable[Mapping[str, Any]] | None,
) -> dict[tuple[str, str, str], SemanticAnchor]:
    overrides: dict[tuple[str, str, str], SemanticAnchor] = {}
    for position, record in enumerate(records or ()):
        if not isinstance(record, Mapping):
            raise ValueError(f"curated semantic anchor {position} must be an object")
        raw_word = record.get("word")
        raw_pos = record.get("pos")
        raw_source_id = record.get("source_id")
        if (
            not isinstance(raw_word, str)
            or not raw_word.strip()
            or not isinstance(raw_pos, str)
            or not raw_pos.strip()
            or not isinstance(raw_source_id, str)
            or not raw_source_id.strip()
        ):
            raise ValueError(
                f"curated semantic anchor {position} requires word, POS, and stable source_id"
            )
        word = normalize_word(raw_word)
        pos = normalize_pos(raw_pos)
        source_id = unicodedata.normalize("NFC", raw_source_id).strip()
        key = (word, pos, source_id)
        anchor = _parse_semantic_anchor(record.get("semantic_anchor"))
        previous = overrides.get(key)
        if previous is not None and previous != anchor:
            raise ValueError(f"conflicting curated semantic anchors for {key!r}")
        overrides[key] = anchor
    return overrides


def _semantic_anchor_for(
    rows: list[dict[str, Any]], *, language: str
) -> tuple[SemanticAnchor | None, str | None]:
    curated = [row["curated_anchor"] for row in rows if row.get("curated_anchor") is not None]
    if curated:
        namespaces = {anchor.namespace for anchor in curated}
        if len(namespaces) != 1:
            return None, "semantic_anchor_namespace_conflict"
        keys = tuple(key for anchor in curated for key in anchor.keys)
        return SemanticAnchor(next(iter(namespaces)), keys), None
    sense_ids = _unique_text(sense_id for row in rows for sense_id in row["evidence"]["sense_ids"])
    if not sense_ids:
        return None, "missing_semantic_anchor"
    namespace = f"lexhint:{normalize_word(language)}:dictionary"
    return SemanticAnchor(namespace, sense_ids), None


def _merged_class_evidence(rows: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    field_names = (
        "sense_ids",
        "etymology_numbers",
        "glosses",
        "topics",
        "tags",
        "examples",
        "synonyms",
        "antonyms",
    )
    merged: dict[str, list[str]] = {name: [] for name in field_names}
    for row in rows:
        for name in field_names:
            merged[name].extend(row["evidence"][name])
    return {name: _unique_text(values) for name, values in merged.items()}


def discover_ambiguities(
    entries: Iterable[Any],
    *,
    language: str,
    locale: str | None = None,
    rules_id: str | None = None,
    pronunciation_equivalence: PronunciationEquivalence | None = None,
    include_equivalence_audit: bool = False,
    curated_anchors: Iterable[Mapping[str, Any]] | None = None,
) -> DiscoveryResult:
    """Discover safe semantic choices among same-word, same-POS readings.

    ``curated_anchors`` is a data overlay of records containing ``word``, ``pos``,
    stable ``source_id``, and ``semantic_anchor: {namespace, keys}``. The source ID
    selects the input row; the semantic keys, never IPA or prose, determine identity.
    """
    if include_equivalence_audit and pronunciation_equivalence is None:
        raise ValueError("equivalence audit requires a pronunciation equivalence policy")
    if include_equivalence_audit and not callable(
        getattr(pronunciation_equivalence, "evaluate", None)
    ):
        raise ValueError("equivalence audit requires a policy that exposes comparison details")
    overrides = _curated_anchor_overrides(curated_anchors)
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
        evidence = _entry_evidence(entry)
        raw_source_id = _field(entry, "source_id", _field(entry, "entry_id", _field(entry, "id")))
        source_id = (
            unicodedata.normalize("NFC", raw_source_id).strip()
            if isinstance(raw_source_id, str)
            else ""
        )
        curated_anchor = overrides.get((word, pos, source_id)) if source_id else None
        direct_anchor = _field(entry, "semantic_anchor")
        if direct_anchor is not None:
            parsed_anchor = _parse_semantic_anchor(direct_anchor)
            if curated_anchor is not None and parsed_anchor != curated_anchor:
                raise ValueError(
                    f"conflicting inline and overlay semantic anchors for {word}/{pos}"
                )
            curated_anchor = parsed_anchor
        grouped[(word, pos)].append(
            {
                "word": raw_word,
                "pronunciations": pronunciations,
                "evidence": evidence,
                "curated_anchor": curated_anchor,
            }
        )

    profiles: list[ReadingProfile] = []
    identities: list[SemanticIdentity] = []
    unresolved: list[UnresolvedAmbiguity] = []
    ambiguous_keys = 0
    resolvable_keys = 0
    unlinked_ambiguity_keys = 0
    non_ambiguous_keys = 0
    unlinked_keys: list[str] = []
    equivalence_comparisons = 0
    equivalence_errors = 0
    equivalence_unsafe_keys = 0
    equivalent_pronunciation_keys = 0
    missing_semantic_anchor_keys = 0
    semantic_overlap_keys = 0
    non_discriminative_keys = 0
    audit_rows: list[dict[str, Any]] = []
    unresolved_counts: dict[str, int] = defaultdict(int)
    identity_by_id: dict[str, tuple[str, str, str, str, tuple[str, ...]]] = {}

    def add_unresolved(
        word: str,
        pos: str,
        reason: str,
        rows: list[dict[str, Any]],
        *,
        pronunciations: Iterable[str] = (),
        details: Mapping[str, Any] | None = None,
    ) -> None:
        sense_ids = _unique_text(
            sense_id for row in rows for sense_id in row["evidence"]["sense_ids"]
        )
        unresolved.append(
            UnresolvedAmbiguity(
                word=word,
                pos=pos,
                reason=reason,
                pronunciations=tuple(pronunciations),
                sense_ids=sense_ids,
                details=dict(details) if details is not None else None,
            )
        )
        unresolved_counts[reason] += 1

    for (normalized_word, pos), entry_rows in sorted(grouped.items()):
        all_ipa = tuple(sorted({ipa for row in entry_rows for ipa, _tags in row["pronunciations"]}))
        if len(all_ipa) <= 1:
            non_ambiguous_keys += 1
            continue

        ambiguous_keys += 1
        if any(len(row["pronunciations"]) != 1 for row in entry_rows):
            unlinked_ambiguity_keys += 1
            unlinked_keys.append(f"{normalized_word}/{pos}")
            add_unresolved(
                normalized_word,
                pos,
                "multiple_pronunciations_without_sense_link",
                entry_rows,
                pronunciations=all_ipa,
            )
            continue

        by_ipa: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in entry_rows:
            ipa, _tags = row["pronunciations"][0]
            by_ipa[ipa].append(row)

        if pronunciation_equivalence is None:
            partition_classes = tuple(PronunciationClass((ipa,)) for ipa in sorted(by_ipa))
            partition = EquivalencePartition(partition_classes)
        else:
            partition = partition_pronunciations(
                by_ipa,
                policy=pronunciation_equivalence,
            )
            equivalence_comparisons += len(partition.pairwise_audit)
            equivalence_errors += sum(pair.error is not None for pair in partition.pairwise_audit)
            if include_equivalence_audit:
                for pair in partition.pairwise_audit:
                    if pair.error is not None:
                        record = {
                            "word": normalized_word,
                            "pos": pos,
                            "ipa_left": pair.left,
                            "ipa_right": pair.right,
                            "equivalent": None,
                            "error": pair.error,
                        }
                    else:
                        record = _comparison_audit_record(
                            normalized_word,
                            pos,
                            pair.left,
                            pair.right,
                            comparison=pair.comparison,
                        )
                        record["equivalent"] = pair.equivalent
                    audit_rows.append(record)

        if partition.unsafe:
            equivalence_unsafe_keys += 1
            add_unresolved(
                normalized_word,
                pos,
                partition.reason or "equivalence_error",
                entry_rows,
                pronunciations=all_ipa,
                details={
                    "comparison_errors": sum(
                        pair.error is not None for pair in partition.pairwise_audit
                    )
                },
            )
            continue
        if len(partition.classes) < 2:
            equivalent_pronunciation_keys += 1
            non_ambiguous_keys += 1
            continue

        class_records: list[
            tuple[
                PronunciationClass,
                list[dict[str, Any]],
                SemanticIdentity,
                tuple[Cue, ...],
            ]
        ] = []
        failed = False
        for pronunciation_class in partition.classes:
            class_rows = [row for ipa in pronunciation_class.pronunciations for row in by_ipa[ipa]]
            anchor, anchor_error = _semantic_anchor_for(class_rows, language=language)
            if anchor is None:
                missing_semantic_anchor_keys += 1
                add_unresolved(
                    normalized_word,
                    pos,
                    anchor_error or "missing_semantic_anchor",
                    class_rows,
                    pronunciations=pronunciation_class.pronunciations,
                )
                failed = True
                break
            evidence = _merged_class_evidence(class_rows)
            source_ipas = pronunciation_class.pronunciations
            anchor_ipa = min(source_ipas)
            reading_id = reading_id_v2(language, normalized_word, pos, anchor)
            identity = SemanticIdentity(
                reading_id=reading_id,
                word=normalized_word,
                pos=pos,
                semantic_anchor=anchor,
                sense_ids=evidence["sense_ids"],
                source_ipas=source_ipas,
                anchor_ipa=anchor_ipa,
            )
            identity_key = (
                normalize_word(language),
                normalized_word,
                pos,
                anchor.namespace,
                anchor.keys,
            )
            previous_identity = identity_by_id.get(reading_id)
            if previous_identity is not None and previous_identity != identity_key:
                raise ValueError(f"r2 reading ID collision for {reading_id}")
            identity_by_id[reading_id] = identity_key
            class_records.append(
                (pronunciation_class, class_rows, identity, compile_cues(evidence))
            )

        if failed:
            continue

        key_owners: dict[str, str] = {}
        overlap: set[str] = set()
        for _pronunciation_class, _class_rows, identity, _cues in class_records:
            for key in identity.semantic_anchor.keys:
                if key in key_owners:
                    overlap.add(key)
                else:
                    key_owners[key] = identity.reading_id
        if overlap:
            semantic_overlap_keys += 1
            add_unresolved(
                normalized_word,
                pos,
                "semantic_anchor_overlap",
                entry_rows,
                pronunciations=all_ipa,
                details={"overlapping_keys": sorted(overlap)},
            )
            continue

        cue_compilation = compile_contrastive_cues(
            cues for _pronunciation_class, _class_rows, _identity, cues in class_records
        )
        if not cue_compilation.selectable:
            if cue_compilation.reason == "non_discriminative_rules":
                non_discriminative_keys += 1
            add_unresolved(
                normalized_word,
                pos,
                cue_compilation.reason or "insufficient_contrastive_evidence",
                entry_rows,
                pronunciations=all_ipa,
                details={"shared_tokens": list(cue_compilation.shared_tokens)},
            )
            continue
        class_records = [
            (pronunciation_class, class_rows, identity, cue_compilation.cue_sets[position])
            for position, (pronunciation_class, class_rows, identity, _cues) in enumerate(
                class_records
            )
        ]

        for _pronunciation_class, _class_rows, identity, cues in class_records:
            identities.append(identity)
            profiles.append(
                ReadingProfile(
                    word=identity.word,
                    pos=identity.pos,
                    reading_id=identity.reading_id,
                    anchor_ipa=identity.anchor_ipa,
                    sense_ids=identity.sense_ids,
                    cues=cues,
                )
            )
        resolvable_keys += 1

    profiles.sort(
        key=lambda profile: (
            normalize_word(profile.word),
            profile.pos,
            profile.ipa,
            profile.reading_id,
        )
    )
    identities.sort(key=lambda identity: (identity.word, identity.pos, identity.reading_id))
    index = AmbiguityIndex(
        language=normalize_word(language),
        locale=locale,
        rules_id=rules_id,
        profiles=tuple(profiles),
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
    report = DiscoveryReport(
        entries_scanned=entries_scanned,
        keys_scanned=len(grouped),
        ambiguous_keys=ambiguous_keys,
        resolvable_keys=resolvable_keys,
        unlinked_ambiguity_keys=unlinked_ambiguity_keys,
        non_ambiguous_keys=non_ambiguous_keys,
        entries_without_pronunciation=entries_without_pronunciation,
        entries_without_pos=entries_without_pos,
        unlinked_keys=tuple(sorted(unlinked_keys)),
        invalid_pronunciation_values=invalid_pronunciation_values,
        equivalent_pronunciation_keys=equivalent_pronunciation_keys,
        equivalence_comparisons=equivalence_comparisons,
        equivalence_errors=equivalence_errors,
        equivalence_unsafe_keys=equivalence_unsafe_keys,
        missing_semantic_anchor_keys=missing_semantic_anchor_keys,
        semantic_overlap_keys=semantic_overlap_keys,
        non_discriminative_keys=non_discriminative_keys,
        runtime_profile_count=len(profiles),
        runtime_cue_count=sum(len(profile.cues) for profile in profiles),
        unresolved_reason_counts=tuple(sorted(unresolved_counts.items())),
    )
    return DiscoveryResult(
        index=index,
        report=report,
        equivalence_audit=tuple(audit_rows),
        unresolved=tuple(unresolved),
        identity_audit=tuple(identities),
    )
