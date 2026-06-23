"""gimbal.prism.builder — 把捕获记录 + 用户配置合成为 GIMBAL Scenario。

Phase 1.3 期间临时 import prism._schema,Phase 2 期间改 import gimbal.schema (v0.3: prism/ 顶层包已删)。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from gimbal.schema import (  # v0.1: 迁到 gimbal.schema (Phase 2)
    Api,
    AssertOperator,
    Assertion,
    Assign,
    Config as ScenarioConfig,
    Extract,
    File,
    Meta,
    Mock,
    MockRef,
    FileRef,
    RecordPolicy,
    RefBase,
    Request,
    Resource,
    ResourceUnion,
    Scenario,
    Scope,
    Setup,
    SetupRef,
    Step,
    StrategyPhase,
    Teardown,
    TeardownRef,
    TimePolicy,
    TimeoutPolicy,
    AuthSession,
    RetryPolicy,
)


# ────────────────────────────────────────────────────────────────────────────
# 用户可编辑草稿
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class AuthDraft:
    url: str = ""
    username: str = ""
    password: str = ""
    expires_in: int = 7200
    token_type: str = "Authorization"
    token: Optional[str] = None
    confirm_password: bool = False


@dataclass
class ResourceDraft:
    name: str
    kind: str = "mock"
    image: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    port_mapping: dict[str, int] = field(default_factory=dict)
    path: str = ""
    ref: str = ""
    value: Any = None


@dataclass
class StepDraft:
    capture: dict[str, Any]
    enabled: bool = True
    add_status_assertion: bool = True
    extracts: list[dict[str, Any]] = field(default_factory=list)
    assigns: list[dict[str, Any]] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    key_hint: str = ""
    note: str = ""
    # v0.5.1 (P0 修复): 用户在 step 卡片里编辑的方法/路径/请求覆盖
    # 缺省 = None, _build_step 走 capture 兜底
    api_override: Optional[dict[str, Any]] = None
    req_override: Optional[dict[str, Any]] = None


@dataclass
class ScenarioDraft:
    # Meta
    scenario_id: str = "sc_new"
    name: str = ""
    description: str = ""
    module: str = "default"
    priority: int = 1
    author: str = "prism"
    owner: str = "prism"
    tags: list[str] = field(default_factory=lambda: ["smoke"])
    version: str = "1.0.0"
    expire: bool = False
    requirement_ref: list[str] = field(default_factory=list)

    # Config
    services: dict[str, str] = field(default_factory=dict)
    users: dict[str, AuthDraft] = field(default_factory=dict)
    time_policy_kind: str = "record"
    time_policy_seconds: int = 60
    retry_enabled: bool = False
    retry_max_attempts: int = 3
    retry_backoff_seconds: float = 20.0
    retry_on: list[str] = field(default_factory=list)
    setup_refs: list[str] = field(default_factory=list)
    teardown_refs: list[str] = field(default_factory=list)

    # Resource
    resources: dict[str, ResourceDraft] = field(default_factory=dict)

    # Steps
    steps: list[StepDraft] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
# 工具
# ────────────────────────────────────────────────────────────────────────────


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


# 痛点 12: 资源 kind 派发表(原 if/elif 串行收敛)
_RESOURCE_KIND_DISPATCH: dict[str, Any] = {}


def _build_resource(rd: ResourceDraft) -> ResourceUnion:
    """按 rd.kind 派发表构造 schema.ResourceUnion 之一。

    痛点 12 (Phase 1.3): 替代 if/elif 串行, 便于加新 kind 不用改 builder。
    """
    name = rd.name
    if rd.kind not in _RESOURCE_KIND_DISPATCH:
        _RESOURCE_KIND_DISPATCH.setdefault("__kinds__", set()).add(rd.kind)
        raise ValueError(f"未知 resource kind: {rd.kind!r}; 支持: mock/mock_ref/file/file_ref")
    return _RESOURCE_KIND_DISPATCH[rd.kind](rd, name)


def _make_mock(rd: ResourceDraft, name: str) -> ResourceUnion:
    return Mock(
        kind="mock", name=name, image=rd.image or "nginx:latest",
        config=rd.config or {},
        portMapping={int(k): int(v) for k, v in (rd.port_mapping or {}).items()},
    )


def _make_mock_ref(rd: ResourceDraft, name: str) -> ResourceUnion:
    return MockRef(ref=rd.ref)


def _make_file(rd: ResourceDraft, name: str) -> ResourceUnion:
    return File(kind="file", name=name, path=rd.path or "")


def _make_file_ref(rd: ResourceDraft, name: str) -> ResourceUnion:
    return FileRef(ref=rd.ref)


_RESOURCE_KIND_DISPATCH["mock"] = _make_mock
_RESOURCE_KIND_DISPATCH["mock_ref"] = _make_mock_ref
_RESOURCE_KIND_DISPATCH["file"] = _make_file
_RESOURCE_KIND_DISPATCH["file_ref"] = _make_file_ref


# ────────────────────────────────────────────────────────────────────────────
# Step / Config / Scenario 构造
# ────────────────────────────────────────────────────────────────────────────


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


def _time_policy(draft: ScenarioDraft) -> TimePolicy:
    if draft.time_policy_kind == "timeout":
        return TimeoutPolicy(kind="timeout", seconds=draft.time_policy_seconds)
    # freeze 没有 schema 支持, 落到 record
    return RecordPolicy(kind="record")


def _retry(draft: ScenarioDraft):
    if not draft.retry_enabled:
        return None
    return RetryPolicy(
        kind="retry_policy",
        maxAttempts=draft.retry_max_attempts,
        backoffSeconds=draft.retry_backoff_seconds,
        retryOn=draft.retry_on,
    )


def _setup_teardown(refs: list[str], kind: str) -> list[Any]:
    out: list[Any] = []
    for r in refs:
        if not r:
            continue
        if kind == "setup":
            out.append(Setup(kind="setup"))
            out.append(SetupRef(kind="setup_ref", ref=r))
        else:
            out.append(Teardown(kind="teardown"))
            out.append(TeardownRef(kind="teardown_ref", ref=r))
    return out


def build_scenario(draft: ScenarioDraft) -> dict[str, Any]:
    default_user_key = next(iter(draft.users), None) if draft.users else None

    steps: list[Step] = []
    for i, sd in enumerate(draft.steps, start=1):
        if not sd.enabled:
            continue
        steps.append(_build_step(sd.capture, draft.services, default_user_key, sd, i))

    users_payload: dict[str, AuthSession] = {}
    for k, v in draft.users.items():
        if v.password and v.password != "<REDACTED>" and not v.confirm_password:
            pw = "<REDACTED>"
        else:
            pw = v.password
        users_payload[k] = AuthSession(
            url=v.url, username=v.username, password=pw,
            expires_in=v.expires_in, token_type=v.token_type, token=v.token,
        )

    sc_cfg = ScenarioConfig(
        setup=_setup_teardown(draft.setup_refs, "setup"),
        teardown=_setup_teardown(draft.teardown_refs, "teardown"),
        services=draft.services or {}, users=users_payload,
        timePolicy=_time_policy(draft), retry=_retry(draft),
    )

    resource_payload: dict[str, ResourceUnion] = {
        name: _build_resource(rd) for name, rd in (draft.resources or {}).items()
    }

    meta = Meta(
        name=draft.name, description=draft.description or draft.name,
        module=draft.module, priority=draft.priority,
        author=draft.author, owner=draft.owner,
        tags=draft.tags or ["smoke"],
        version=draft.version,
        createTime=datetime.now(), expire=draft.expire,
        requirementRef=[RefBase(ref=r) for r in draft.requirement_ref],
    )

    scenario = Scenario(
        scenarioId=draft.scenario_id, meta=meta, config=sc_cfg,
        resource=resource_payload, steps=steps,
    )
    return scenario.model_dump(mode="json")
