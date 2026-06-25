"""gimbal.prism.server.conversions — DraftIn wire -> ScenarioDraft domain.

Single conversion helper plus the password-redaction helper used by the
export endpoint.
"""
from __future__ import annotations

from typing import Any

from gimbal.prism.builder import (
    AuthDraft,
    ResourceDraft,
    ScenarioDraft,
    StepDraft,
)
from gimbal.prism.state import CaptureReader, DraftIn, UserIn


def _redact_user(u: UserIn) -> AuthDraft:
    """password 默认走 <REDACTED>, 仅 confirm_password=True 才落明文。"""
    pw = u.password or ""
    if not u.confirm_password and pw and pw != "<REDACTED>":
        pw = "<REDACTED>"
    return AuthDraft(
        url=u.url, username=u.username, password=pw,
        expires_in=u.expires_in, token_type=u.token_type, token=u.token,
    )


def _draft_from_in(
    payload: DraftIn, capture_reader: CaptureReader, session_id: str,
) -> ScenarioDraft:
    users = {u.key: _redact_user(u) for u in payload.users}
    resources: dict[str, ResourceDraft] = {}
    for r in payload.resources:
        resources[r["name"]] = ResourceDraft(
            name=r["name"], kind=r.get("kind", "mock"), image=r.get("image", ""),
            config=r.get("config") or {},
            port_mapping={str(k): v for k, v in (r.get("port_mapping") or {}).items()},
            path=r.get("path", ""), ref=r.get("ref", ""), value=r.get("value"),
        )
    # v0.5.1 (P0 修复): 优先用 payload.steps 携带的完整自定义
    # fallback: step_ids 索引 captures 文件 (旧客户端兼容, 但不带自定义)
    if payload.steps:
        steps = [
            StepDraft(
                capture=s["capture"],
                enabled=s.get("enabled", True),
                add_status_assertion=s.get("add_status_assertion", True),
                extracts=s.get("extracts") or [],
                assigns=s.get("assigns") or [],
                assertions=s.get("assertions") or [],
                key_hint=s.get("key_hint") or "",
                note=s.get("note") or "",
                api_override=s.get("api_override"),
                req_override=s.get("req_override"),
            )
            for s in payload.steps
        ]
    else:
        # 旧路径: 从 capture 文件读所有事件, 用 step_ids 索引
        all_events = capture_reader.read(session_id, limit=None)
        id_to_event = {str(i): e for i, e in enumerate(all_events)}
        steps = []
        for sid in payload.step_ids:
            if sid in id_to_event:
                steps.append(StepDraft(capture=id_to_event[sid]))
    return ScenarioDraft(
        scenario_id=payload.scenario_id, name=payload.name,
        description=payload.description, module=payload.module,
        priority=payload.priority, author=payload.author, owner=payload.owner,
        tags=payload.tags or ["smoke"], version=payload.version,
        expire=payload.expire, requirement_ref=payload.requirement_ref,
        services=payload.services, users=users,
        time_policy_kind=payload.time_policy_kind,
        time_policy_seconds=payload.time_policy_seconds,
        retry_enabled=payload.retry_enabled,
        retry_max_attempts=payload.retry_max_attempts,
        retry_backoff_seconds=payload.retry_backoff_seconds,
        retry_on=payload.retry_on,
        setup_refs=payload.setup_refs, teardown_refs=payload.teardown_refs,
        resources=resources, steps=steps,
    )