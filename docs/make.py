#!/usr/bin/env python3
"""Build pronresolve documentation with Sphinx."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run Sphinx for the selected documentation target."""
    docs_dir = Path(__file__).resolve().parent
    build_dir = docs_dir / "_build"
    target = sys.argv[1] if len(sys.argv) > 1 else "html"
    if target == "clean":
        shutil.rmtree(build_dir, ignore_errors=True)
        return 0
    if target not in {"html", "dirhtml", "text", "doctest", "linkcheck"}:
        print(f"Unknown documentation target: {target}", file=sys.stderr)
        return 2
    output_dir = build_dir / target
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-W",
            "--keep-going",
            "-b",
            target,
            str(docs_dir),
            str(output_dir),
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
