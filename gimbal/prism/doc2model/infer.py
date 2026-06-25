"""gimbal.prism.doc2model.infer — type inference from sample values.

Heuristic-based inference of Pydantic field types from observed sample
data. Used by codegen to emit type annotations.
"""
from __future__ import annotations

import keyword
import re
from collections import Counter
from typing import Any


def safe_name(raw: str) -> str:
    """Sanitize a raw identifier for use as a Python class/field name."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if not s or s[0].isdigit():
        s = "f_" + s
    if keyword.iskeyword(s):
        s += "_"
    return s


def classify_value(v: Any) -> str:
    """Classify a single sample value into a primitive type tag."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return "unknown"


def merge_types(types: set[str]) -> str:
    """把同字段观察到的所有原始类型,合并成一个 typing 表达式。"""
    if "unknown" in types:
        return "Any"
    types = types - {"null"}
    if not types:
        return "Any"
    if types == {"bool"}:
        return "bool"
    if types == {"int"}:
        return "int"
    if types == {"float"}:
        return "float"
    if types == {"str"}:
        return "str"
    if types <= {"int", "float"}:
        return "float"
    if types <= {"str", "int", "float"}:
        return "str"
    if types == {"list"}:
        return "list[Any]"
    if types == {"dict"}:
        return "dict[str, Any]"
    return "Any"


def collect_field_stats(
    samples: list[dict[str, Any]], key: str | None = None,
) -> dict[str, Counter]:
    """从 N 个样本中,统计每个字段观察到的 type 分布。"""
    stats: dict[str, Counter] = {}
    for s in samples:
        obj = s.get(key) if key else s
        if not isinstance(obj, dict):
            continue
        for fname, fval in obj.items():
            t = classify_value(fval)
            stats.setdefault(fname, Counter())[t] += 1
    return stats


__all__ = ["safe_name", "classify_value", "merge_types", "collect_field_stats"]