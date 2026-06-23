"""Fix #8: ``_step_key`` must survive ``Step.model_dump()``。

背景: docx §4.4.4 要求 step 的建议 key (形如 ``1-call_login``) 进入导出 JSON。
原版用 ``setattr(step, '_step_key', ...)`` 在 Pydantic v2 下不进 ``model_dump``。
本测试锁定修复后行为: Step 应有显式 ``key`` 字段, 且 builder 写入后能 dump 出来。
"""
import json
import pytest
from pydantic import ValidationError

from gimbal.schema import Step, Api, Request
from gimbal.prism.builder import build_scenario, ScenarioDraft, StepDraft
from gimbal.capture.recorder import event_from_dict


def _capture(path: str = "/api/call_login", status: int = 200) -> dict:
    return {
        "ts": 1.0, "method": "GET", "scheme": "https", "host": "a.example.com",
        "port": 443, "path": path, "query": {}, "headers": {}, "body": "",
        "response": {"status": status, "headers": {}, "body": "{}"},
    }


def test_step_key_field_exists_and_default_none():
    """Step 应有可选 key 字段, 默认 None。"""
    s = Step(
        api=Api(service="s", method="GET", path="/x"),
        request=Request(kind="request", body={}),
        strategy=[],
    )
    assert s.key is None


def test_step_key_survives_model_dump():
    """显式赋值后, model_dump 必须包含 key (不能只活在 __pydantic_extra__)。"""
    s = Step(
        api=Api(service="s", method="GET", path="/x"),
        request=Request(kind="request", body={}),
        strategy=[],
        key="1-x",
    )
    dumped = s.model_dump()
    assert dumped.get("key") == "1-x"


def test_step_key_omitted_when_none_in_dump():
    """key=None 时, model_dump(exclude_none=True) 应不出现 key 字段。"""
    s = Step(
        api=Api(service="s", method="GET", path="/x"),
        request=Request(kind="request", body={}),
        strategy=[],
    )
    dumped = s.model_dump(exclude_none=True)
    assert "key" not in dumped


def test_builder_emits_step_key_in_scenario_dict():
    """builder 应在导出 dict 中放入 ``key`` 字段 (形如 ``1-<path-slug>``)。"""
    ev = event_from_dict(_capture("/api/call_login"))
    draft = ScenarioDraft(
        scenario_id="sc_x", name="t",
        services={"a.example.com": "https://a.example.com/"},
        steps=[StepDraft(capture=ev.__dict__)],
    )
    out = build_scenario(draft)
    assert len(out["steps"]) == 1
    # _PATH_SLUG_RE 把非 [A-Za-z0-9_] 全替成 _, 首尾 _ 去掉
    # /api/call_login → api_call_login → "1-api_call_login"
    assert out["steps"][0]["key"] == "1-api_call_login"


def test_step_key_honors_explicit_hint():
    """``key_hint`` 优先于 path slug。"""
    ev = event_from_dict(_capture("/api/call_login"))
    draft = ScenarioDraft(
        scenario_id="sc_x", name="t",
        services={"a.example.com": "https://a.example.com/"},
        steps=[StepDraft(capture=ev.__dict__, key_hint="my_login")],
    )
    out = build_scenario(draft)
    assert out["steps"][0]["key"] == "1-my_login"


def test_step_rejects_setattr_for_key_after_fix():
    """修复后, setattr 注入 _step_key 不应被 model_dump 接受 (防止回归到黑魔法)。"""
    s = Step(
        api=Api(service="s", method="GET", path="/x"),
        request=Request(kind="request", body={}),
        strategy=[],
    )
    # 显式 key 字段是合法 API
    s.key = "1-x"
    # setattr _step_key 是设计外行为, 不应污染 dump
    s._step_key = "1-LEGACY-SETATTR"
    dumped = s.model_dump()
    assert dumped.get("key") == "1-x"
    # _step_key 在 Pydantic v2 模型本就不应被 export
    assert dumped.get("_step_key", "absent") == "absent"
