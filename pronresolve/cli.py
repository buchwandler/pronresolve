"""Command-line tools for building and inspecting ambiguity indexes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from collections.abc import Iterable

from .discovery import discover_ambiguities
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pronresolve")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build an ambiguity index from JSONL entries")
    build.add_argument("--input-jsonl", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--language", required=True)
    build.add_argument("--locale")

    inspect = subparsers.add_parser("inspect", help="print index summary")
    inspect.add_argument("index", type=Path)

    validate = subparsers.add_parser("validate", help="validate an index schema")
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
                        "report": str(report_path),
                        **result.report.as_dict(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        index = load_index(args.index)
        summary = {
            "valid": True,
            "schema_version": index.schema_version,
            "language": index.language,
            "locale": index.locale,
            "profile_count": len(index.profiles),
            "ambiguous_words": len({profile.word.casefold() for profile in index.profiles}),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"pronresolve: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
