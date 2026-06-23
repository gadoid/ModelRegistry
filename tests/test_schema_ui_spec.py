"""测试 gimbal.schema + /api/schema/ui-spec + /api/schema/dot-paths 端点 (Phase 2 SSOT)。"""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_gimbal_home(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / ".gimbal"
        home.mkdir()
        monkeypatch.setenv("GIMBAL_HOME", str(home))
        yield home


def test_schema_imports():
    """gimbal.schema 各模块独立可 import, 无循环依赖。"""
    from gimbal.schema import (
        Scenario, Meta, Config, Step, Api, Request,
        Resource, Mock, File, MockRef, FileRef, ResourceUnion,
        AuthSession, RetryPolicy, TimePolicy, RecordPolicy, TimeoutPolicy,
        StepUnion, StrategyUnion, ApiUnion, RequestUnion,
        Scope, AssertOperator, StrategyPhase, FailurePolicy,
    )
    assert Scenario is not None
    assert Step is not None
    assert len(list(Scope)) == 5
    # AssertOperator: EQ/NE/GT/GTE/LT/LTE/IN/NOT_IN/CONTAINS/NOT_CONTAINS/EXISTS/EMPTY/LENGTH_EQ/SCHEMA = 14
    assert len(list(AssertOperator)) == 14


def test_field_wrapper_merges_ui():
    """包装版 Field 把 ui 字典塞进 json_schema_extra。"""
    from gimbal.schema import Field
    from pydantic import BaseModel

    class M(BaseModel):
        x: str = Field("d", ui={"widget": "input", "label": "X"})

    f = M.model_fields["x"]
    assert f.json_schema_extra == {"ui": {"widget": "input", "label": "X"}}
    # 不进入 model_dump
    assert M(x="v").model_dump() == {"x": "v"}


def test_meta_name_blank_rejected():
    """Meta.name 空/纯空白 → ValidationError (M2.5 行为保留)。"""
    from pydantic import ValidationError
    from gimbal.schema import Meta
    with pytest.raises(ValidationError) as exc:
        Meta(name="")
    assert any("name" in str(e["loc"]) for e in exc.value.errors())
    with pytest.raises(ValidationError):
        Meta(name="   ")


def test_meta_name_with_valid_value():
    from gimbal.schema import Meta
    m = Meta(name="  下单  ")  # strip 由 validator 处理
    assert m.name == "  下单  "  # validator 只校验空白, 不 strip


def test_step_key_roundtrip():
    """Step.key 字段存在 + 可 dump。"""
    from gimbal.schema import Step, Api, Request
    s = Step(api=Api(service="s", method="GET", path="/x"),
             request=Request(body={}), strategy=[], key="1-x")
    assert s.key == "1-x"
    d = s.model_dump()
    assert d["key"] == "1-x"


def test_request_has_params():
    """v0.1 补: Request.params 字段。"""
    from gimbal.schema import Request
    r = Request(body={"a": 1}, params={"q": "abc"})
    assert r.params == {"q": "abc"}


def test_build_ui_spec_meta_group():
    from gimbal.prism.render import build_ui_spec
    from gimbal.schema import Scenario
    spec = build_ui_spec(Scenario)
    assert spec["version"] == 1
    group_ids = [g["id"] for g in spec["groups"]]
    # 至少 meta 在, 且排在前面
    assert "meta" in group_ids
    meta = next(g for g in spec["groups"] if g["id"] == "meta")
    # Meta 字段都带 ui
    paths = {f["path"] for f in meta["fields"]}
    assert "meta.name" in paths
    assert "meta.priority" in paths
    assert "meta.tags" in paths
    # name 必填
    name_field = next(f for f in meta["fields"] if f["path"] == "meta.name")
    assert name_field["required"] is True
    assert name_field["widget"] == "input"
    # priority 是 select
    prio = next(f for f in meta["fields"] if f["path"] == "meta.priority")
    assert prio["widget"] == "select"
    assert {o["value"] for o in prio["options"]} == {1, 2, 3}


def test_walk_fields_yields_dot_paths():
    from gimbal.prism.render import walk_fields
    from gimbal.schema import Scenario
    paths = [p for p, _fi, _m in walk_fields(Scenario)]
    # 至少包含关键路径
    assert "scenarioId" in paths
    assert "meta.name" in paths
    assert "meta.priority" in paths
    assert "config.services" in paths
    assert "steps" in paths


def test_schema_ui_spec_endpoint(temp_gimbal_home):
    """GET /api/schema/ui-spec 端点可用。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        r = client.get("/api/schema/ui-spec")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 1
        assert any(g["id"] == "meta" for g in body["groups"])
        # 二次调用应命中缓存 (app.state.ui_spec_cache)
        r2 = client.get("/api/schema/ui-spec")
        assert r2.status_code == 200
        assert r2.json() == body


def test_schema_dot_paths_endpoint(temp_gimbal_home):
    """GET /api/schema/dot-paths 端点返回 paths 列表。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        r = client.get("/api/schema/dot-paths")
        assert r.status_code == 200
        body = r.json()
        assert "paths" in body
        assert "count" in body
        assert body["count"] == len(body["paths"])
        assert "meta.name" in body["paths"]
        assert "config.services" in body["paths"]
