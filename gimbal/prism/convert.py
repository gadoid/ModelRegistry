"""gimbal.prism.convert — NDJSON 捕获记录 → GYMAL step 片段(只整理字段, 不校验)。

Phase 1.3 期间先沿用 prism.convert 的逻辑, Phase 2 期间视需要重写。
"""
from __future__ import annotations

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
        return DEFAULT_RULES
    rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "services": rules.get("services") or {},
        "headers": {"keep": (rules.get("headers") or {}).get("keep") or []},
        "defaults": {"timeout": (rules.get("defaults") or {}).get("timeout", 30)},
    }


def convert_record(record: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """单条捕获记录 → 单个 step 片段。纯函数, 无 IO。"""
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


def convert_file(ndjson_path: Path, rules: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    with ndjson_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                steps.append(convert_record(json.loads(line), rules))
    return steps
