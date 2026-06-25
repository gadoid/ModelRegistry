"""gimbal.prism.doc2model.cli — argparse entry point + sample loader.

The argparse-driven `main()` is invoked via:
  python -m gimbal.prism.doc2model --in <ndjson> --service <name> ...

Or programmatically via `main(argv)`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from gimbal.io_utils import iter_ndjson_lines
from gimbal.prism.doc2model.codegen import (
    build_endpoint_module,
    generate_models,
    write_registry_file,
)
from gimbal.prism.doc2model.infer import safe_name

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_REGISTRY_DIRNAME = "ModelRegistry"


def _adapt_capture(d: dict[str, Any]) -> dict[str, Any]:
    """把 capture 行(``{method, path, headers, body, response: {status, headers, body}}``)
    标准化为下游函数期望的形状。"""
    resp = d.get("response") or {}
    body = d.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
    resp_body = resp.get("body")
    if isinstance(resp_body, str):
        try:
            resp_body = json.loads(resp_body)
        except json.JSONDecodeError:
            pass
    out = dict(d)
    out["body"] = body
    if resp:
        out["response"] = {**resp, "body": resp_body}
    return out


def load_samples(source: Path, source_dir: Path | None) -> list[dict[str, Any]]:
    """从文件/目录读出 N 个样本,每个样本形如::

        {"method": str, "path": str, "body": dict | None, "response": {"status": int, "body": dict | None}}

    适配 prism/capture.py 输出的 NDJSON 格式;若只给目录,自动尝试当响应体读。
    """
    samples: list[dict[str, Any]] = []
    if source and source.is_file():
        if source.suffix == ".ndjson":
            try:
                events = list(iter_ndjson_lines(source))
            except ValueError:
                events = []
            for line in events:
                samples.append(_adapt_capture(line))
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
        ep_path = (base / safe_name(args.service) / args.endpoint_file)
        ep_path.write_text(ep_code, encoding="utf-8")
        print(f"[doc2model] -> {out_path}")
        print(f"[doc2model] -> {ep_path}")
    else:
        out_dir = args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / safe_name(args.service) / args.models_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(src, encoding="utf-8")
        print(f"[doc2model] -> {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["main", "load_samples"]