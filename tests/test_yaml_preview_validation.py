"""Regression test: ``POST /api/draft/{session_id}/yaml`` 必须在 ``meta.name`` 为空时
返回 **422**, 而不是 500。

复现路径
---------
启动 ``prism.ui serve`` → 浏览器打开 ``/configure?session=foo`` → 不填 name 直接点
"只读 YAML"。修复前的 stack::

    File "D:\\PRISMB\\prism\\server.py", line 363, in preview_yaml
        scenario = build_scenario(draft)
    File "D:\\PRISMB\\prism\\builder.py", line 357, in build_scenario
        meta = Meta(name=draft.name, ...)
    pydantic_core._pydantic_core.ValidationError: 1 validation error for Meta
    name
      String should have at least 1 character [type=string_too_short,
      input_value='', input_type=str]

修复后, ``preview_yaml`` 应与 ``/api/build``、``/api/draft/{sid}/export`` 行为一致:
空 name → 422 + ``detail="meta.name 必填"``, 而不是裸 500。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app as fastapi_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / ".gimbal"
        home.mkdir()
        os.environ["GIMBAL_HOME"] = str(home)
        with TestClient(fastapi_app) as c:
            yield c


def _empty_draft_payload() -> dict:
    """最小 DraftIn 负载 — name 故意为空。"""
    return {
        "scenario_id": "sc_test",
        "name": "",  # ← 触发 schema 校验失败
        "description": "",
        "module": "default",
        "priority": 1,
        "author": "prism",
        "owner": "prism",
        "tags": ["smoke"],
        "version": "1.0.0",
        "expire": False,
        "requirement_ref": [],
        "services": {},
        "users": [],
        "time_policy_kind": "record",
        "time_policy_seconds": 60,
        "retry_enabled": False,
        "retry_max_attempts": 3,
        "retry_backoff_seconds": 20.0,
        "retry_on": [],
        "setup_refs": [],
        "teardown_refs": [],
        "resources": [],
        "step_ids": [],
    }


def test_yaml_preview_with_empty_name_returns_422_not_500(client) -> None:
    """回归: 空 name 不能让 /yaml 端点返回 500。"""
    r = client.post("/api/draft/repro_yaml/yaml", json=_empty_draft_payload())
    assert r.status_code == 422, (
        f"expected 422 (validation error), got {r.status_code} body={r.text!r}"
    )
    # 错误体应明确告诉用户哪个字段错了; 不应是裸 500
    body = r.json()
    detail = body.get("detail") or body.get("errors") or ""
    assert "name" in str(detail), f"error body should mention 'name', got {body!r}"


def test_yaml_preview_with_valid_name_returns_yaml(client) -> None:
    """冒烟: 合法 name 仍能正常返回 YAML 字符串。"""
    payload = _empty_draft_payload()
    payload["name"] = "订单到应收"
    r = client.post("/api/draft/repro_yaml/yaml", json=payload)
    assert r.status_code == 200, r.text
    yaml_text = r.json()["yaml"]
    assert "scenarioId" in yaml_text
    assert "订单到应收" in yaml_text
