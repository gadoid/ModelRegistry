"""gimbal.prism.builder.drafts — Pydantic-style dataclasses for user-editable drafts.

These mirror the wire forms from the prism web UI / CLI but are
domain-level (not HTTP-shaped). They are the input to build_scenario().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


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


__all__ = ["AuthDraft", "ResourceDraft", "StepDraft", "ScenarioDraft"]