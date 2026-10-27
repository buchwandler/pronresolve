"""JSON persistence for generated ambiguity indexes."""

from __future__ import annotations

import json
from pathlib import Path

from .models import AmbiguityIndex


def save_index(index: AmbiguityIndex, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(index.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_index(path: str | Path) -> AmbiguityIndex:
    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ambiguity index root must be a JSON object")
    return AmbiguityIndex.from_dict(value)
