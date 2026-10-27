"""Command-line tools for building and inspecting ambiguity indexes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .discovery import discover_ambiguities
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

    inspect = subparsers.add_parser("inspect", help="print index summary and optional word details")
    inspect.add_argument("index", type=Path)
    inspect.add_argument("--word", help="show readings and weighted cues for one word")

    validate = subparsers.add_parser("validate", help="validate a v1 or v2 index schema")
    validate.add_argument("index", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = discover_ambiguities(
                _jsonl_entries(args.input_jsonl),
                language=args.language,
                locale=args.locale,
            )
            save_index(result.index, args.output)
            report_path = args.output.with_name(args.output.name + ".report.json")
            report_path.write_text(
                json.dumps(result.report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "index": str(args.output),
                        "schema_version": result.index.schema_version,
                        "report": str(report_path),
                        **result.report.as_dict(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
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
