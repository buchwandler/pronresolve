"""Command-line tools for building and inspecting ambiguity indexes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .discovery import discover_ambiguities
from .equivalence import PhonodistEquivalence
from .normalization import normalize_word
from .storage import load_index, save_index


def _jsonl_entries(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each JSONL record must be an object")
            yield value


def _json_object_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{path}: expected a JSON array of objects")
    return value


def _source_schema_version(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value.get("schema_version") if isinstance(value, dict) else None


def _index_summary(index, source_schema_version: Any) -> dict[str, Any]:
    profiles = index.profiles
    groups = {(profile.word, profile.pos) for profile in profiles}
    cue_count = sum(len(profile.cues) for profile in profiles)
    word_count = len({profile.word for profile in profiles})
    return {
        "valid": True,
        "schema_version": source_schema_version,
        "runtime_schema_version": index.schema_version,
        "language": index.language,
        "locale": index.locale,
        "id_version": 2 if index.schema_version == 3 else None,
        "rules_id": index.rules_id,
        "resolution_class_count": len(profiles),
        "ambiguous_word_count": word_count,
        "ambiguous_words": word_count,
        "word_pos_group_count": len(groups),
        "profile_count": len(profiles),
        "cue_count": cue_count,
        "average_cues_per_profile": round(cue_count / len(profiles), 3) if profiles else 0.0,
    }


def _weighted_cues(profile) -> dict[str, list[str]]:
    return profile.to_dict()["cues"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pronresolve")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build an ambiguity index from JSONL entries")
    build.add_argument("--input-jsonl", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--language", required=True)
    build.add_argument("--locale")
    build.add_argument("--rules-id", help="shared ruleset identifier (defaults to locale/language)")
    build.add_argument(
        "--curated-anchors",
        type=Path,
        help="JSON array of reviewed semantic-anchor overrides",
    )
    build.add_argument(
        "--pronunciation-equivalence",
        choices=("exact", "phonodist"),
        default="exact",
        help="build-time IPA equivalence policy (default: exact)",
    )
    build.add_argument(
        "--stress-policy",
        choices=("all", "primary"),
        default="all",
        help="stress required by phonodist equivalence (default: all)",
    )
    build.add_argument(
        "--strict-equivalence",
        action="store_true",
        help="fail the build if any phonodist comparisons cannot be evaluated",
    )
    build.add_argument(
        "--audit-output",
        type=Path,
        help="write sorted structural comparisons for remaining ambiguity pairs",
    )
    build.add_argument(
        "--identity-audit-output",
        type=Path,
        help="write semantic identity provenance separately from the runtime index",
    )

    inspect = subparsers.add_parser("inspect", help="print index summary and optional word details")
    inspect.add_argument("index", type=Path)
    inspect.add_argument("--word", help="show readings and weighted cues for one word")

    validate = subparsers.add_parser("validate", help="validate a v1, v2, or v3 index schema")
    validate.add_argument("index", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            equivalence = None
            if args.pronunciation_equivalence == "phonodist":
                equivalence = PhonodistEquivalence(
                    language=args.language,
                    stress_policy=args.stress_policy,
                )
            if args.audit_output is not None and equivalence is None:
                raise ValueError("--audit-output requires --pronunciation-equivalence phonodist")
            result = discover_ambiguities(
                _jsonl_entries(args.input_jsonl),
                language=args.language,
                rules_id=args.rules_id,
                curated_anchors=(
                    _json_object_array(args.curated_anchors)
                    if args.curated_anchors is not None
                    else None
                ),
                locale=args.locale,
                pronunciation_equivalence=equivalence,
                include_equivalence_audit=args.audit_output is not None,
            )
            report_path = args.output.with_name(args.output.name + ".report.json")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(result.report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            if args.audit_output is not None:
                args.audit_output.parent.mkdir(parents=True, exist_ok=True)
                args.audit_output.write_text(
                    json.dumps(
                        list(result.equivalence_audit),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            if args.identity_audit_output is not None:
                args.identity_audit_output.parent.mkdir(parents=True, exist_ok=True)
                identity_records = [identity.to_dict() for identity in result.identity_audit]
                args.identity_audit_output.write_text(
                    json.dumps(
                        identity_records,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            if args.strict_equivalence and result.report.equivalence_errors:
                raise ValueError(
                    f"phonodist comparison errors occurred: {result.report.equivalence_errors}"
                )
            save_index(result.index, args.output)
            output = {
                "index": str(args.output),
                "schema_version": result.index.schema_version,
                "report": str(report_path),
                **result.report.as_dict(),
            }
            if args.audit_output is not None:
                output["equivalence_audit"] = str(args.audit_output)
            if args.identity_audit_output is not None:
                output["identity_audit"] = str(args.identity_audit_output)
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

        source_schema_version = _source_schema_version(args.index)
        index = load_index(args.index)
        summary = _index_summary(index, source_schema_version)
        if args.command == "inspect" and args.word is not None:
            word = normalize_word(args.word)
            summary["word"] = word
            summary["readings"] = [
                {
                    "word": profile.word,
                    "pos": profile.pos,
                    "reading_id": profile.reading_id,
                    "anchor_ipa": profile.anchor_ipa,
                    "ipa": profile.ipa,
                    "sense_ids": list(profile.sense_ids),
                    "weighted_cues": _weighted_cues(profile),
                }
                for profile in index.profiles
                if profile.word == word
            ]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"pronresolve: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
