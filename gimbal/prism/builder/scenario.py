"""gimbal.prism.builder.scenario — Top-level build_scenario + auxiliary helpers.

Composes a ScenarioDraft into a validated scenario dict using:
  - builder.steps._build_step (per-step construction)
  - builder.resources.build_resource (resource dispatch)
  - schema.Meta / Config / Scenario (Pydantic)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from gimbal.prism.builder.drafts import ScenarioDraft
from gimbal.prism.builder.resources import build_resource
from gimbal.prism.builder.steps import _build_step
from gimbal.schema import (
    AuthSession,
    Config as ScenarioConfig,
    Meta,
    RecordPolicy,
    RefBase,
    ResourceUnion,
    RetryPolicy,
    Scenario,
    Setup,
    SetupRef,
    Teardown,
    TeardownRef,
    TimePolicy,
    TimeoutPolicy,
)


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

    steps: list[Any] = []
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
        name: build_resource(rd) for name, rd in (draft.resources or {}).items()
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


__all__ = ["build_scenario", "_time_policy", "_retry", "_setup_teardown"]