"""prism doc2model — 从存储的请求/响应样本推断 Pydantic 模型代码。

输入格式(任选其一):
- ``--in ndjson_path``:NDJSON,每行一条 capture(同 prism/capture.py 输出)
- ``--in json_path``:JSON 数组,每项一条 capture
- ``--in-dir dir``:目录下所有 ``*.json`` 文件,每个文件当一个"响应体样本"

输出:
- 默认写到 ``--out-dir``(独立 generated 目录)
- ``--into-registry`` 时直接写到 ``ModelRegistry/<service>/<endpoint_slug>.py``
  (格式遵循 ModelRegistry 的 EndpointSpec 契约,model_config=ConfigDict(extra='forbid'))

类型推断规则(简易、保守):
- 数字:
    - 出现小数 → float
    - 否则 → int
- bool:所有出现值都在 {true, false} 且至少出现过一次 true / false → bool
- null:记成 Optional(必须)
- str:其它
- dict:递归生成嵌套 BaseModel(类名 ``<父>_<key>Model``)
- list:list[<elem>],空列表记为 ``list[Any]``

字段是否必填:出现率 ≥ ``--required-ratio``(默认 0.8)算必填,否则 Optional。
字段名清洗:非 [A-Za-z0-9_] → ``_``,开头数字加 ``f_`` 前缀。
"""
from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

# 复用 ModelRegistry 的契约常量
REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_REGISTRY_DIRNAME = "ModelRegistry"
PY_INDENT = "    "


# ────────────────────────────────────────────────────────────────────────────
# 数据加载
# ────────────────────────────────────────────────────────────────────────────


def load_samples(source: Path, source_dir: Path | None) -> list[dict[str, Any]]:
    """从文件/目录读出 N 个样本,每个样本形如::

        {"method": str, "path": str, "body": dict | None, "response": {"status": int, "body": dict | None}}

    适配 prism/capture.py 输出的 NDJSON 格式;若只给目录,自动尝试当响应体读。
    """
    samples: list[dict[str, Any]] = []
    if source and source.is_file():
        if source.suffix == ".ndjson":
            with source.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    samples.append(_adapt_capture(json.loads(line)))
        else:
            data = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    samples.append(_adapt_capture(item) if "response" in item else {"body": item, "response": {"status": 200, "body": None}, "method": "GET", "path": "/"})
            else:
                samples.append(_adapt_capture(data) if "response" in data else {"body": data, "response": {"status": 200, "body": None}, "method": "GET", "path": "/"})
    if source_dir and source_dir.is_dir():
        for p in sorted(source_dir.glob("*.json")):
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, list):
                for it in obj:
                    samples.append({"body": it, "response": {"status": 200, "body": None}, "method": "GET", "path": "/"})
            else:
                samples.append({"body": obj, "response": {"status": 200, "body": None}, "method": "GET", "path": "/"})
    return samples


def _adapt_capture(d: dict[str, Any]) -> dict[str, Any]:
    """把 capture 行(``{method, path, headers, body, response: {status, headers, body}}``)
    标准化为下游函数期望的形状。"""
    resp = d.get("response") or {}
    body = d.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass  # 非 JSON,留给生成时使用 Any
    resp_body = resp.get("body")
    if isinstance(resp_body, str):
        try:
            resp_body = json.loads(resp_body)
        except json.JSONDecodeError:
            pass
    return {
        "method": d.get("method", "GET"),
        "path": d.get("path", "/"),
        "body": body if isinstance(body, (dict, list)) else None,
        "response": {"status": resp.get("status", 0), "body": resp_body if isinstance(resp_body, (dict, list)) else None},
    }


# ────────────────────────────────────────────────────────────────────────────
# 类型推断
# ────────────────────────────────────────────────────────────────────────────


def _safe_name(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if not s or s[0].isdigit():
        s = "f_" + s
    if keyword.iskeyword(s):
        s += "_"
    return s


def _classify_value(v: Any) -> str:
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


def _merge_types(types: set[str]) -> str:
    """把同字段观察到的所有原始类型,合并成一个 typing 表达式。"""
    if "unknown" in types:
        return "Any"
    types = types - {"null"}
    if not types:
        return "Any"
    if types == {"bool"}:
        return "bool"
    if types <= {"int", "float"}:
        return "float" if "float" in types else "int"
    if types == {"str"}:
        return "str"
    if types == {"list"}:
        return "list[Any]"
    if types == {"dict"}:
        return "dict[str, Any]"
    if "dict" in types and len(types) > 1:
        return "Any"
    if "list" in types and len(types) > 1:
        return "Any"
    if types <= {"str", "int", "float", "bool"}:
        return "Any"
    return "Any"


def _collect_field_stats(samples: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """对 samples[*][key] 收集每个子字段的:观察类型集合、出现次数、是否 null。"""
    counter: dict[str, Counter] = defaultdict(Counter)
    for s in samples:
        obj = s.get(key)
        if not isinstance(obj, dict):
            continue
        for k, v in obj.items():
            counter[k][_classify_value(v)] += 1
    return dict(counter)


def _infer_inner_type(counter: Counter) -> str:
    return _merge_types(set(counter.keys()))


# ────────────────────────────────────────────────────────────────────────────
# 代码生成
# ────────────────────────────────────────────────────────────────────────────


def _emit_model(
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
        tname = _merge_types(set(type_counter.keys()))

        # list[dict] → list[SubModel]
        if tname == "list[Any]":
            elem_types: set[str] = set()
            elem_field_stats: dict[str, Counter] = defaultdict(Counter)
            for s in parent_samples or []:
                obj = (s.get(key) or {}) if key else {}
                v = obj.get(fname)
                if isinstance(v, list) and v:
                    for item in v:
                        elem_types.add(_classify_value(item))
                        if isinstance(item, dict):
                            for k, vv in item.items():
                                elem_field_stats[k][_classify_value(vv)] += 1
            if elem_types == {"dict"} and elem_field_stats:
                sub_name = class_name + _safe_name(fname).title() + "Item"
                nested_classes.append(_emit_model(
                    sub_name, elem_field_stats, required_ratio=required_ratio,
                    parent_samples=parent_samples, key=key, indent=indent,
                ).rstrip("\n"))
                tname = f"list[{sub_name}]"
            elif elem_types:
                tname = f"list[{_merge_types(elem_types)}]"

        # dict[any,any] 字段 → SubModel
        if tname == "dict[str, Any]":
            sub_stats: dict[str, Counter] = defaultdict(Counter)
            for s in parent_samples or []:
                obj = (s.get(key) or {}) if key else {}
                v = obj.get(fname)
                if isinstance(v, dict):
                    for k, vv in v.items():
                        sub_stats[k][_classify_value(vv)] += 1
            if sub_stats:
                sub_name = class_name + _safe_name(fname).title() + "Field"
                nested_classes.append(_emit_model(
                    sub_name, sub_stats, required_ratio=required_ratio,
                    parent_samples=parent_samples, key=key, indent=indent,
                ).rstrip("\n"))
                tname = sub_name

        if not required:
            tname = f"Optional[{tname}]"
            has_optional = True
        elif "null" in type_counter:
            tname = f"Optional[{tname}]"
            has_optional = True
        default = "" if required else " = None"
        safe_fname = _safe_name(fname)
        lines.append(f"{inner_pad}{safe_fname}: {tname}{default}")

    if has_optional:
        lines.insert(2, f"{inner_pad}# (字段出现率 < {required_ratio:.0%} 时,默认标为 Optional)")

    if nested_classes:
        lines.append("")
        lines.extend(nested_classes)
    return "\n".join(lines) + "\n"


def generate_models(
    samples: list[dict[str, Any]],
    *,
    class_prefix: str = "Auto",
    required_ratio: float = 0.8,
) -> str:
    """生成完整的模块源码:``Request`` / ``Response`` / ``Endpoint``。"""
    req_stats = _collect_field_stats(samples, "body")
    resp_stats: dict[str, Counter] = defaultdict(Counter)
    for s in samples:
        r = s.get("response") or {}
        b = r.get("body")
        if isinstance(b, dict):
            for k, v in b.items():
                resp_stats[k][_classify_value(v)] += 1
    resp_stats = dict(resp_stats)

    req_code = _emit_model(f"{class_prefix}Request", req_stats, required_ratio, samples, "body", indent=0)
    resp_code = _emit_model(f"{class_prefix}Response", resp_stats, required_ratio, samples, "response", indent=0)

    header = [
        '"""auto-generated by prism doc2model — do not edit manually."""',
        "from __future__ import annotations",
        "from typing import Any, Optional, List, Dict, Tuple",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "",
    ]
    body = "\n".join(header) + req_code + "\n" + resp_code
    # 触发子模型的 forward-ref 解析
    body += "\n\n# resolve forward refs (list[SubModel] 写在父 class 之后)\n"
    for cls_name in {class_prefix + "Request", class_prefix + "Response"}:
        body += f"{cls_name}.model_rebuild()\n"
    return body


# ────────────────────────────────────────────────────────────────────────────
# 落盘
# ────────────────────────────────────────────────────────────────────────────


def write_registry_file(
    out_dir: Path,
    service: str,
    endpoint_filename: str,
    src: str,
) -> Path:
    """把生成的源码写到 ``<out_dir>/<service>/<filename>.py``。"""
    svc_dir = out_dir / _safe_name(service)
    svc_dir.mkdir(parents=True, exist_ok=True)
    target = svc_dir / endpoint_filename
    target.write_text(src, encoding="utf-8")
    return target


def build_endpoint_module(
    service: str,
    method: str,
    path: str,
    request_class: str,
    response_class: str,
    summary: str = "",
) -> str:
    """生成 ModelRegistry 的 endpoint 文件,导出 EndpointSpec。"""
    code = f'''"""auto-generated endpoint for {method} {path}"""
from __future__ import annotations

from gimbal.contracts import EndpointSpec
from .{request_class} import {request_class}
from .{response_class} import {response_class}


SPEC = EndpointSpec(
    method="{method}",
    path="{path}",
    request={request_class},
    responses={{200: {response_class}}},
    summary="{summary}",
)
'''
    return code


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="prism-doc2model", description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--in", dest="in_file", type=Path, help="输入 NDJSON / JSON 文件")
    g.add_argument("--in-dir", dest="in_dir", type=Path, help="输入目录(每个 JSON 文件一个样本)")
    p.add_argument("--service", required=True, help="service 名(用于 ModelRegistry 目录)")
    p.add_argument("--method", default="GET")
    p.add_argument("--path", default="/")
    p.add_argument("--out-dir", type=Path, default=Path("generated"),
                   help="生成文件输出目录(默认 ./generated)")
    p.add_argument("--into-registry", action="store_true",
                   help="直接写到 ModelRegistry/<service>/(慎用,会污染源仓库)")
    p.add_argument("--required-ratio", type=float, default=0.8,
                   help="字段出现率 ≥ 此值视为必填(默认 0.8)")
    p.add_argument("--dry-run", action="store_true", help="只打印到 stdout,不写盘")
    p.add_argument("--endpoint-file", type=str, default="endpoint.py",
                   help="ModelRegistry 下 endpoint 文件名(默认 endpoint.py)")
    p.add_argument("--models-file", type=str, default="models.py",
                   help="ModelRegistry 下 models 文件名(默认 models.py)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from gimbal.contracts import is_available
    args = _parse_args(argv)
    samples = load_samples(args.in_file, args.in_dir)
    if not samples:
        print("[doc2model] no samples loaded", file=sys.stderr)
        return 2
    src = generate_models(samples, required_ratio=args.required_ratio)
    if args.dry_run:
        print(src)
        return 0

    if args.into_registry:
        # ModelRegistry 不可用时给出友好提示
        if not is_available():
            print(
                "[doc2model] ModelRegistry 不可用, --into-registry 需要装 model-registry-local:\n"
                "  pip install -e '.[model-registry]'\n"
                "  或: export GIMBAL_MODEL_REGISTRY_PATH=/path/to/D:/M/ModelRegistry",
                file=sys.stderr,
            )
            return 3
        base = REPO_ROOT / MODEL_REGISTRY_DIRNAME
        out_path = write_registry_file(
            base, args.service, args.models_file, src,
        )
        # endpoint 文件单独写
        ep_code = build_endpoint_module(
            args.service, args.method, args.path,
            request_class="AutoRequest", response_class="AutoResponse",
            summary=f"{args.method} {args.path}",
        )
        ep_path = (base / _safe_name(args.service) / args.endpoint_file)
        ep_path.write_text(ep_code, encoding="utf-8")
        print(f"[doc2model] -> {out_path}")
        print(f"[doc2model] -> {ep_path}")
    else:
        out_dir = args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / _safe_name(args.service) / args.models_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(src, encoding="utf-8")
        print(f"[doc2model] -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
