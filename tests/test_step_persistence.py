"""gimbal.prism — Step 自定义字段持久化 (P0 修复 v0.5.1)。

覆盖 (审计报告 §3.2):
  - StepDraft 接受 api_override / req_override
  - DraftIn 接受 steps 字段 (新)
  - _draft_from_in 优先用 payload.steps, fallback 到 step_ids
  - build_scenario 把 api_override 应用于 api.method / api.path / api.service
  - build_scenario 把 req_override 完全替换 request.params/headers/body
  - Round-trip: PUT steps → GET draft → build_scenario
  - assertions / extracts / assigns / key_hint / note 全部落 YAML
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gimbal.prism.builder import (
    ScenarioDraft,
    StepDraft,
    build_scenario,
)
from gimbal.prism.server import DraftIn, UserIn


# ─── StepDraft 新字段 (P0-1) ──────────────────────────────────────────────


def test_stepdraft_accepts_api_override():
    s = StepDraft(
        capture={"method": "GET", "path": "/old"},
        api_override={"method": "PUT", "path": "/new", "service": "my-svc"},
    )
    assert s.api_override == {"method": "PUT", "path": "/new", "service": "my-svc"}


def test_stepdraft_accepts_req_override():
    """req_override 只覆盖 params/body (headers 在 api 上, 走 api_override 路径)。"""
    s = StepDraft(
        capture={"method": "POST", "body": '{"x":1}'},
        req_override={
            "params": {"p": "1"},
            "body": {"replaced": True},
        },
    )
    assert s.req_override["params"] == {"p": "1"}
    assert s.req_override["body"] == {"replaced": True}


def test_stepdraft_api_override_optional():
    s = StepDraft(capture={"method": "GET", "path": "/a"})
    assert s.api_override is None


def test_stepdraft_existing_fields_preserved():
    """P0 修复不能破坏现有字段 (assertions/extracts/assigns/key_hint/note/enabled)。"""
    s = StepDraft(
        capture={"method": "GET", "path": "/a"},
        assertions=[{"target": "response_status", "operator": "eq", "expected": 200}],
        extracts=[{"target": "var1", "expression": "$.token"}],
        assigns=[{"target": "var2", "source": "$.user"}],
        key_hint="login",
        note="用户登录",
        enabled=True,
    )
    assert len(s.assertions) == 1
    assert len(s.extracts) == 1
    assert len(s.assigns) == 1
    assert s.key_hint == "login"
    assert s.note == "用户登录"


# ─── DraftIn 新字段 (P0-2) ────────────────────────────────────────────────


def test_draftin_accepts_steps_field():
    d = DraftIn(
        scenario_id="sc1",
        name="test",
        steps=[
            {
                "capture": {"method": "GET", "path": "/a"},
                "key_hint": "step_a",
                "assertions": [{"target": "x", "operator": "eq", "expected": 1}],
            }
        ],
    )
    assert len(d.steps) == 1
    assert d.steps[0]["key_hint"] == "step_a"


def test_draftin_legacy_step_ids_still_accepted():
    """向后兼容: 旧客户端只发 step_ids 仍能过 Pydantic 校验。"""
    d = DraftIn(step_ids=["0", "1"])
    assert d.step_ids == ["0", "1"]
    assert d.steps == []


def test_draftin_default_steps_empty():
    d = DraftIn()
    assert d.steps == []
    assert d.step_ids == []


# ─── _draft_from_in 行为 (P0-2) ────────────────────────────────────────────


def test_draft_from_in_prefers_payload_steps():
    """payload.steps 非空时, 优先用之, 不读 captures 文件。"""
    from gimbal.prism.server import _draft_from_in
    from gimbal.prism.state import CaptureReader

    reader = CaptureReader(Path("/tmp/no_such"))  # 空 reader, 任何读都返回 []
    steps_data = [
        {
            "capture": {"method": "PUT", "path": "/override"},
            "key_hint": "custom",
            "assertions": [{"target": "x", "operator": "eq", "expected": 200}],
            "extracts": [],
            "assigns": [],
            "api_override": {"method": "PATCH", "path": "/new", "service": "svc"},
        }
    ]
    payload = DraftIn(steps=steps_data, step_ids=["999"])  # step_ids 应被忽略
    draft = _draft_from_in(payload, reader, "sess1")

    assert len(draft.steps) == 1
    sd = draft.steps[0]
    assert sd.api_override == {"method": "PATCH", "path": "/new", "service": "svc"}
    assert sd.key_hint == "custom"
    assert sd.assertions[0]["expected"] == 200


def test_draft_from_in_fallback_to_step_ids(tmp_path):
    """payload.steps 为空时, 走旧的 step_ids 路径 (从 captures 文件读)。"""
    from gimbal.prism.server import _draft_from_in
    from gimbal.prism.state import CaptureReader

    # 模拟 captures 文件: tmp_path/captures/active/sess.ndjson
    sess = "fallback_sess"
    active = tmp_path / "captures" / "active"
    active.mkdir(parents=True)
    (active / f"{sess}.ndjson").write_text(
        '{"method":"GET","path":"/a"}\n{"method":"POST","path":"/b"}\n',
        encoding="utf-8",
    )
    reader = CaptureReader(tmp_path)
    payload = DraftIn(step_ids=["0", "1"])
    draft = _draft_from_in(payload, reader, sess)

    assert len(draft.steps) == 2
    assert draft.steps[0].capture["path"] == "/a"
    assert draft.steps[1].capture["method"] == "POST"


# ─── build_scenario 消费自定义 (P0-3) ────────────────────────────────────


def test_build_scenario_applies_api_override():
    sd = StepDraft(
        capture={"method": "GET", "path": "/old", "host": "api.example.com"},
        api_override={"method": "PUT", "path": "/new", "service": "custom-svc"},
    )
    draft = ScenarioDraft(name="t", steps=[sd], services={"custom-svc": "https://api.example.com"})
    sc = build_scenario(draft)

    step = sc["steps"][0]
    assert step["api"]["method"] == "PUT"
    assert step["api"]["path"] == "/new"
    assert step["api"]["service"] == "custom-svc"


def test_build_scenario_api_override_partial():
    """api_override 只覆盖部分字段时, 其余从 capture 兜底。"""
    sd = StepDraft(
        capture={"method": "GET", "path": "/orig", "host": "api.example.com"},
        api_override={"method": "POST"},  # 只改 method
    )
    draft = ScenarioDraft(name="t", steps=[sd])
    sc = build_scenario(draft)
    step = sc["steps"][0]
    assert step["api"]["method"] == "POST"
    assert step["api"]["path"] == "/orig"  # 走 capture 兜底


def test_build_scenario_applies_req_override():
    """req_override 替换 request.params / body (headers 不在 Request schema)。"""
    sd = StepDraft(
        capture={"method": "POST", "body": '{"original":true}', "query": {"old": "1"}},
        req_override={
            "params": {"new": "1"},
            "body": {"replaced": True},
        },
    )
    draft = ScenarioDraft(name="t", steps=[sd])
    sc = build_scenario(draft)
    req = sc["steps"][0]["request"]
    assert req["params"] == {"new": "1"}
    assert req["body"] == {"replaced": True}
    # 旧 capture 字段完全不出现
    assert "old" not in req.get("params", {})


def test_build_scenario_assertions_in_yaml():
    """用户加的 assertion 必须落进 scenario YAML。"""
    sd = StepDraft(
        capture={"method": "GET", "path": "/a"},
        assertions=[
            {"target": "response_status", "operator": "eq", "expected": 200, "message": "should be 200"},
            {"target": "response_body.code", "operator": "eq", "expected": 0, "message": "code should be 0"},
        ],
    )
    draft = ScenarioDraft(name="t", steps=[sd])
    sc = build_scenario(draft)
    strategy = sc["steps"][0]["strategy"]
    # 第一条是 add_status_assertion 自动加的, 第二三条是用户加的
    user_asserts = [s for s in strategy if s["kind"] == "assertion" and "user" in s["name"]]
    assert len(user_asserts) == 2
    assert user_asserts[0]["expected"] == 200
    assert user_asserts[1]["target"] == "response_body.code"


def test_build_scenario_extracts_in_yaml():
    sd = StepDraft(
        capture={"method": "POST", "path": "/login", "response": {"body": '{"token":"abc"}'}},
        extracts=[{"target": "auth_token", "expression": "$.token", "scope": "scenario"}],
    )
    draft = ScenarioDraft(name="t", steps=[sd])
    sc = build_scenario(draft)
    strategy = sc["steps"][0]["strategy"]
    extracts = [s for s in strategy if s["kind"] == "extract"]
    assert len(extracts) == 1
    assert extracts[0]["target"] == "auth_token"
    assert extracts[0]["expression"] == "$.token"


def test_build_scenario_key_hint_in_yaml():
    sd = StepDraft(
        capture={"method": "GET", "path": "/api/v1/users"},
        key_hint="list_users",
    )
    draft = ScenarioDraft(name="t", steps=[sd])
    sc = build_scenario(draft)
    # key 格式: "{idx}-{slug}", 优先级: hint > path
    assert sc["steps"][0]["key"] == "1-list_users"


# ─── Round-trip (P0 整体) ────────────────────────────────────────────────


def test_roundtrip_draft_via_draftin():
    """DraftIn 接受所有 step 自定义字段, 序列化后不丢。"""
    payload = DraftIn(
        scenario_id="sc_roundtrip",
        name="roundtrip test",
        steps=[
            {
                "capture": {"method": "POST", "path": "/login", "response": {"status": 200}},
                "api_override": {"method": "POST", "path": "/v2/login"},
                "req_override": {"params": {}, "body": {"user": "u"}},
                "assertions": [{"target": "response_status", "operator": "eq", "expected": 200}],
                "extracts": [{"target": "tok", "expression": "$.token"}],
                "assigns": [],
                "key_hint": "login_step",
                "note": "登录",
                "enabled": True,
            }
        ],
    )
    # 序列化为 dict
    d = payload.model_dump()
    assert d["steps"][0]["key_hint"] == "login_step"
    assert d["steps"][0]["api_override"]["path"] == "/v2/login"
    assert d["steps"][0]["req_override"]["body"]["user"] == "u"

    # 反序列化
    p2 = DraftIn.model_validate(d)
    assert p2.steps[0]["assertions"][0]["expected"] == 200
