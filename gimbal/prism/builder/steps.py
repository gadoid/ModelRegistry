"""gimbal.prism.builder.steps — _build_step + helpers for step construction.

Builds a single schema.Step from a StepDraft + capture event + service map.
Strategy construction (assertion / extract / assign) is included here as
it's tightly coupled to step building.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from gimbal.prism.builder.drafts import StepDraft
from gimbal.schema import (
    Api,
    AssertOperator,
    Assertion,
    Assign,
    Extract,
    Request,
    Scope,
    Step,
    StrategyPhase,
)


def _service_name_for(host: str, services: dict[str, str]) -> str:
    for svc, url in services.items():
        if host and host in (url or ""):
            return svc
    return (host or "service").split(".")[0] or "service"


def _auth_header_template(user_key: str) -> str:
    return f"${{auth.{user_key}.token}}"


_PATH_SLUG_RE = re.compile(r"[^A-Za-z0-9_]+")


def _step_key(idx: int, path: str, hint: str = "") -> str:
    """docx §4.4.4: ``1-call_login`` 形式。hint 优先, 否则用 path slug。"""
    if hint:
        slug = _PATH_SLUG_RE.sub("_", hint).strip("_") or "step"
    else:
        slug = _PATH_SLUG_RE.sub("_", path or "step").strip("_") or "step"
    return f"{idx}-{slug}"


def _build_step(
    capture: dict[str, Any],
    services: dict[str, str],
    default_user_key: Optional[str],
    draft: StepDraft,
    index: int,
) -> Step:
    host = capture.get("host", "")
    method = (capture.get("method") or "GET").upper()
    path = capture.get("path", "/")
    service = _service_name_for(host, services)

    # v0.5.1 (P0 修复): 用户在 step 卡片里覆盖 method / path / service
    # api_override 缺省字段 = 走 capture 兜底
    if draft.api_override:
        method = (draft.api_override.get("method") or method).upper()
        path = draft.api_override.get("path") or path
        if draft.api_override.get("service"):
            service = draft.api_override["service"]

    keep: dict[str, str] = {}
    for name, value in (capture.get("headers") or {}).items():
        if name.lower() == "authorization":
            if default_user_key:
                keep["Authorization"] = _auth_header_template(default_user_key)
            else:
                keep[name] = value

    api = Api(
        kind="api", service=service, method=method, path=path,
        headers=keep, timeout=30,
    )

    # v0.5.1: req_override 替换 params/body (headers 不在 Request schema, 走 api.headers)
    if draft.req_override:
        request_dict: dict[str, Any] = {
            "kind": "request",
            "params": draft.req_override.get("params", {}),
            "body": draft.req_override.get("body", {}),
        }
    else:
        # body
        raw = capture.get("body") or ""
        body: dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    body = parsed
                else:
                    body = {"_value": parsed}
            except json.JSONDecodeError:
                body = {"_raw": raw}

        # query → params
        request_dict = {"kind": "request", "body": body}
        if capture.get("query"):
            request_dict["params"] = capture["query"]

    request = Request(**request_dict)

    # strategy — 痛点 13: 可复现 name
    strategies: list[Any] = []
    if draft.add_status_assertion:
        status = capture.get("response", {}).get("status", 200)
        strategies.append(
            Assertion(
                kind="assertion",
                name=f"assert_status_{index}",  # ← 痛点 13: 用 idx 替代 hash(path)
                phase=StrategyPhase.VERIFYING, order=0,
                target="response_status", operator=AssertOperator.EQ,
                expected=status, message=f"{method} {path} 应返回 {status}",
                soft=False,
            )
        )
    for i, ex in enumerate(draft.extracts):
        strategies.append(
            Extract(
                kind="extract",
                name=ex.get("name") or f"extract_{i}",
                phase=StrategyPhase.AFTER_REQUEST, order=i + 1,
                expression=ex.get("expression") or "$",
                target=ex.get("target") or f"var_{i}",
                scope=Scope(ex.get("scope", "scenario")),
                required=ex.get("required", True),
            )
        )
    for i, asg in enumerate(draft.assigns):
        strategies.append(
            Assign(
                kind="assign",
                name=asg.get("name") or f"assign_{i}",
                phase=StrategyPhase.BEFORE_REQUEST, order=i,
                source=asg.get("source"),
                target=asg.get("target") or f"var_{i}",
                scope=Scope(asg.get("scope", "scenario")),
                required=asg.get("required", True),
            )
        )
    for i, asn in enumerate(draft.assertions):
        strategies.append(
            Assertion(
                kind="assertion",
                name=asn.get("name") or f"assert_user_{i}",
                phase=StrategyPhase(asn.get("phase", "verifying")),
                order=len(strategies) + i,
                target=asn.get("target") or "response_status",
                operator=AssertOperator(asn.get("operator", "eq")),
                expected=asn.get("expected"),
                message=asn.get("message"),
                soft=asn.get("soft", False),
            )
        )

    step = Step(
        kind="step", api=api, request=request, strategy=strategies,
        key=_step_key(index, path, draft.key_hint),
    )
    return step


__all__ = ["_build_step", "_step_key", "_service_name_for"]