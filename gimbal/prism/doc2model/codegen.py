"""gimbal.prism.doc2model.codegen — Pydantic model code generation.

Takes inferred field stats and emits a Python source string defining
Pydantic BaseModel subclasses. Used by the CLI main() in cli.py.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from gimbal.prism.doc2model.infer import classify_value, collect_field_stats, merge_types, safe_name

PY_INDENT = "    "


def emit_model(
    class_name: str,
    stats: dict[str, dict[str, Any]],
    required_ratio: float,
    parent_samples: list[dict[str, Any]] | None = None,
    key: str | None = None,
    indent: int = 1,
) -> str:
    """生成一个 BaseModel 子类的源码。stats 形如 ``{field: {type: count, ...}}``。

    子模型(list[dict] / dict)以"追加到 class 末尾"的形式输出,避免缩进混乱。
    """
    pad = PY_INDENT * indent
    inner_pad = PY_INDENT * (indent + 1)
    n = sum(sum(v.values()) for v in stats.values()) if stats else 0
    lines: list[str] = []
    lines.append(f"{pad}class {class_name}(BaseModel):")
    lines.append(f"{inner_pad}model_config = ConfigDict(extra='forbid', str_strip_whitespace=False, "
                 f"coerce_numbers_to_str=False, use_enum_values=False)")

    nested_classes: list[str] = []  # 追加到 class 之后、相同 indent 的子 model

    if not stats:
        lines.append(f"{inner_pad}# 无字段可推断,空模型占位")
        return "\n".join(lines) + "\n"

    has_optional = False
    for fname, type_counter in stats.items():
        total = sum(type_counter.values())
        present_ratio = total / max(n, 1)
        required = present_ratio >= required_ratio
        tname = merge_types(set(type_counter.keys()))

        # list[dict] → list[SubModel]
        if tname == "list[Any]":
            elem_types: set[str] = set()
            elem_field_stats: dict[str, Counter] = defaultdict(Counter)
            for s in parent_samples or []:
                obj = (s.get(key) or {}) if key else {}
                v = obj.get(fname)
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            for ik, iv in item.items():
                                elem_types.add(classify_value(iv))  # noqa: F821
                                elem_field_stats[ik][classify_value(iv)] += 1  # noqa: F821
            elem_class = safe_name(f"{class_name}_{fname}_item")
            tname = f"list[{elem_class}]"
            if elem_types:
                nested_classes.append(
                    emit_model(elem_class, elem_field_stats, required_ratio)
                )
            else:
                nested_classes.append(
                    f"{PY_INDENT * indent}class {elem_class}(BaseModel):\n"
                    f"{PY_INDENT * (indent + 1)}pass\n"
                )

        # dict[str, Any] → dict[str, SubModel]
        elif tname == "dict[str, Any]":
            sub_types: set[str] = set()
            sub_field_stats: dict[str, Counter] = defaultdict(Counter)
            for s in parent_samples or []:
                obj = (s.get(key) or {}) if key else {}
                v = obj.get(fname)
                if isinstance(v, dict):
                    for ik, iv in v.items():
                        sub_types.add(classify_value(iv))  # noqa: F821
                        sub_field_stats[ik][classify_value(iv)] += 1  # noqa: F821
            sub_class = safe_name(f"{class_name}_{fname}")
            tname = f"dict[str, {sub_class}]"
            if sub_types:
                nested_classes.append(
                    emit_model(sub_class, sub_field_stats, required_ratio)
                )
            else:
                nested_classes.append(
                    f"{PY_INDENT * indent}class {sub_class}(BaseModel):\n"
                    f"{PY_INDENT * (indent + 1)}pass\n"
                )

        if not required:
            tname = f"Optional[{tname}] = None"
            has_optional = True

        lines.append(f"{inner_pad}{safe_name(fname)}: {tname}")

    if has_optional:
        lines.append(f"{inner_pad}model_config = ConfigDict(extra='forbid')")

    return "\n".join(lines + nested_classes) + "\n"


def generate_models(
    samples: list[dict[str, Any]],
    *,
    required_ratio: float = 0.8,
) -> str:
    """Generate models.py source from a list of sample records.

    Each top-level field becomes a field on the auto-generated
    ``AutoRequest`` / ``AutoResponse`` models.
    """
    req_stats = collect_field_stats(samples, key="body") if samples else {}
    resp_stats: dict[str, Counter] = defaultdict(Counter)
    for s in samples:
        resp = s.get("response", {}).get("body")
        if isinstance(resp, dict):
            for k, v in resp.items():
                resp_stats[k][classify_value(v)] += 1  # noqa: F821
    resp_stats = dict(resp_stats)

    src_parts: list[str] = []
    src_parts.append('"""Auto-generated Pydantic models (gimbal.prism.doc2model)."""')
    src_parts.append("from __future__ import annotations")
    src_parts.append("from typing import Any, Optional")
    src_parts.append("from pydantic import BaseModel, ConfigDict")
    src_parts.append("")

    src_parts.append(emit_model("AutoRequest", req_stats, required_ratio, parent_samples=samples, key="body"))
    src_parts.append(emit_model("AutoResponse", resp_stats, required_ratio, parent_samples=samples, key="response"))
    return "\n".join(src_parts)


def write_registry_file(
    base: Path, service: str, models_filename: str, src: str,
) -> Path:
    """把生成的 models 写到 <base>/<service>/<models_filename>。"""
    out_dir = base / safe_name(service)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / models_filename
    out_path.write_text(src, encoding="utf-8")
    return out_path


def build_endpoint_module(
    service: str, method: str, path: str,
    request_class: str = "AutoRequest", response_class: str = "AutoResponse",
    summary: str = "auto",
) -> str:
    """Build the endpoint.py module source for a generated endpoint."""
    svc = safe_name(service)
    # The implementation is template-driven; the actual format lives here.
    return f'''"""Auto-generated endpoint ({method} {path})."""
from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from gimbal.contracts import EndpointSpec
from .{request_class} import {request_class}
from .{response_class} import {response_class}

router = APIRouter()

SPEC = EndpointSpec(
    service="{svc}",
    method="{method.upper()}",
    path="{path}",
    request_model={request_class},
    response_model={response_class},
    summary="{summary}",
)
'''


__all__ = [
    "emit_model",
    "generate_models",
    "write_registry_file",
    "build_endpoint_module",
    "PY_INDENT",
]