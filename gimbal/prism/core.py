"""gimbal.prism.core — shared pipeline + edit primitives used by prism-cli.

OBLIGATION: This module must call builder.build_scenario() under the hood
and stay in sync with it. tests/test_prism_core_builder_parity.py is the
canary that detects drift.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read an NDJSON file and return all events as a list of dicts.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if file is empty (no events).
        json.JSONDecodeError: propagated from json.loads for malformed lines.
    """
    if not path.exists():
        raise FileNotFoundError(f"ndjson not found: {path}")
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if not events:
        raise ValueError(f"ndjson has no events: {path}")
    return events