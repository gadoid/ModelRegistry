"""gimbal.prism.convert — pure NDJSON capture-record → step-fragment helpers.

This module is intentionally I/O-free; readers should use
gimbal.io_utils.iter_ndjson_lines for file access and call convert_record
in a loop. The legacy convert_file helper has been removed — callers
should compose these two primitives directly (see core.ndjson_to_step_fragments).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RULES: dict[str, Any] = {
    "services": {},
    "headers": {"keep": ["Authorization"]},
    "defaults": {"timeout": 30},
}


def load_rules(path: Path | None) -> dict[str, Any]:
    if path is None:
        # Return a deep copy so callers can mutate the result (e.g.
        # `rules["services"].update(...)`) without leaking into the
        # module-level singleton.
        return copy.deepcopy(DEFAULT_RULES)
    rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "services": rules.get("services") or {},
        "headers": {"keep": (rules.get("headers") or {}).get("keep") or []},
        "defaults": {"timeout": (rules.get("defaults") or {}).get("timeout", 30)},
    }


def convert_record(record: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Single capture record → one step fragment. Pure function, no IO."""
    keep = {name.lower() for name in rules["headers"]["keep"]}
    headers = {
        name: value
        for name, value in record["headers"].items()
        if name.lower() in keep
    }

    body: Any = None
    raw_body = record.get("body")
    if raw_body:
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body

    step: dict[str, Any] = {
        "api": {
            "kind": "api",
            "service": rules["services"].get(record["host"], record["host"]),
            "method": record["method"],
            "path": record["path"],
            "headers": headers,
            "timeout": rules["defaults"]["timeout"],
        },
        "request": {
            "kind": "request",
            "body": body,
        },
        "_captured_response": {
            "status": record["response"]["status"],
        },
    }
    if record.get("query"):
        step["request"]["params"] = record["query"]
    return step
