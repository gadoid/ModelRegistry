"""Smoke test for gimbal.prism.builder (痛点 12 + 13)。"""
import tempfile
import time
from pathlib import Path

from gimbal.prism.builder import (
    ScenarioDraft,
    StepDraft,
    build_scenario,
    _build_resource,
)
from gimbal.schema import Mock, MockRef, File, FileRef, ResourceUnion


def _capture(path: str = "/api/call_login", status: int = 200) -> dict:
    return {
        "ts": 1.0, "method": "GET", "scheme": "https", "host": "a.example.com",
        "port": 443, "path": path, "query": {}, "headers": {}, "body": "",
        "response": {"status": status, "headers": {}, "body": "{}"},
    }


def test_痛点13_reproducible_assertion_name():
    """痛点 13: 默认 assertion name 用 idx, 跨运行可复现。"""
    cap = _capture("/api/foo")
    draft = ScenarioDraft(
        scenario_id="sc_x", name="t",
        services={"a.example.com": "https://a.example.com/"},
        steps=[StepDraft(capture=cap)],
    )
    out = build_scenario(draft)
    # 进程内 idx 从 1 起
    assert out["steps"][0]["strategy"][0]["name"] == "assert_status_1"
    # 第二次跑同 draft, name 一致 (可复现)
    out2 = build_scenario(draft)
    assert out2["steps"][0]["strategy"][0]["name"] == "assert_status_1"
    print("1. 痛点 13 可复现 name OK (assert_status_1)")


def test_痛点12_resource_kind_dispatch():
    """痛点 12: 资源 kind 用 dispatch 表 (而非 if/elif 串行)。"""
    from gimbal.prism.builder import ResourceDraft
    # mock
    rd = ResourceDraft(name="r1", kind="mock", image="nginx:1", port_mapping={"80": 8080})
    r = _build_resource(rd)
    assert isinstance(r, Mock)
    assert r.image == "nginx:1"
    assert r.portMapping == {80: 8080}
    # mock_ref
    rd2 = ResourceDraft(name="r2", kind="mock_ref", ref="ref-1")
    r2 = _build_resource(rd2)
    assert isinstance(r2, MockRef)
    assert r2.ref == "ref-1"
    # file
    rd3 = ResourceDraft(name="r3", kind="file", path="/tmp/x")
    r3 = _build_resource(rd3)
    assert isinstance(r3, File)
    # file_ref
    rd4 = ResourceDraft(name="r4", kind="file_ref", ref="ref-2")
    r4 = _build_resource(rd4)
    assert isinstance(r4, FileRef)
    # 未知 kind → ValueError
    rd_bad = ResourceDraft(name="rb", kind="unknown_xyz")
    try:
        _build_resource(rd_bad)
        assert False, "should have raised"
    except ValueError as e:
        assert "未知 resource kind" in str(e)
    print("2. 痛点 12 dispatch 表 OK")


def test_step_key_survives_dump():
    """M2.5 已做: Step.key 字段进入 scenario dict。"""
    draft = ScenarioDraft(
        scenario_id="sc_x", name="t",
        services={"a.example.com": "https://a.example.com/"},
        steps=[StepDraft(capture=_capture("/api/call_login"))],
    )
    out = build_scenario(draft)
    assert out["steps"][0]["key"] == "1-api_call_login"
    print("3. Step.key 进入 dump OK")


def test_meta_name_blank_rejected_at_export():
    """M2.5 已做: 空 / 纯空白 name → Scenario 校验失败。"""
    from pydantic import ValidationError
    draft = ScenarioDraft(
        scenario_id="sc_x", name="",  # 空
        steps=[StepDraft(capture=_capture())],
    )
    from gimbal.schema import Scenario as Scen
    try:
        out = build_scenario(draft)
        Scen.model_validate(out)
        assert False, "should have raised"
    except ValidationError as e:
        assert any("name" in str(err["loc"]) for err in e.errors())
    print("4. Meta.name blank 校验 OK")


if __name__ == "__main__":
    test_痛点13_reproducible_assertion_name()
    test_痛点12_resource_kind_dispatch()
    test_step_key_survives_dump()
    test_meta_name_blank_rejected_at_export()
    print("\nAll builder tests passed")
