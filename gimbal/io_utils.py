"""gimbal.io_utils — shared low-level I/O helpers.

Consolidates duplicate NDJSON-line readers previously scattered across
prism/state.py, prism/core.py, prism/convert.py, prism/doc2model.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def iter_ndjson_lines(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each non-empty line of an NDJSON file as a parsed dict.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if file is empty (no events).
        json.JSONDecodeError: propagated from json.loads for malformed lines.
    """
    if not path.exists():
        raise FileNotFoundError(f"ndjson not found: {path}")
    found_any = False
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                found_any = True
                yield json.loads(line)
    if not found_any:
        raise ValueError(f"ndjson has no events: {path}")