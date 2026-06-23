"""端到端集成测试: capture NDJSON → prism 读 → 编辑 draft → 导出 YAML → 校验。"""
import json
import os
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gimbal_home(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / ".gimbal"
        home.mkdir()
        monkeypatch.setenv("GIMBAL_HOME", str(home))
        yield home


def test_e2e_capture_to_export(gimbal_home):
    """端到端: capture 写 NDJSON → prism 读 → 导出 YAML → 校验通过。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app

    with TestClient(app) as client:
        sid = "e2e-sid"

        # 1. inject 3 个 capture
        for i, (method, path, status) in enumerate([
            ("GET", "/api/users", 200),
            ("POST", "/api/users", 201),
            ("GET", "/api/users/1", 200),
        ]):
            ev = {
                "ts": float(i), "method": method, "scheme": "https",
                "host": "api.example.com", "port": 443, "path": path,
                "query": {}, "headers": {},
                "body": json.dumps({"name": "x"}) if method == "POST" else "",
                "response": {"status": status, "headers": {}, "body": "{}"},
            }
            r = client.post("/api/captures/inject", params={"sid": sid}, json=ev)
            assert r.status_code == 200, r.text

        # 2. prism 读 captures
        r = client.get("/api/captures", params={"sid": sid})
        assert r.status_code == 200
        assert r.json()["count"] == 3

        # 3. 构造 draft, 引用全部 3 step
        payload = {
            "scenario_id": sid, "name": "e2e 测试",
            "description": "端到端", "module": "test", "priority": 1,
            "author": "a", "owner": "o", "tags": ["e2e"], "version": "1.0.0",
            "expire": False, "requirement_ref": [],
            "services": {"api.example.com": "https://api.example.com/"},
            "users": [],
            "time_policy_kind": "record", "time_policy_seconds": 60,
            "retry_enabled": False, "retry_max_attempts": 3,
            "retry_backoff_seconds": 20.0, "retry_on": [],
            "setup_refs": [], "teardown_refs": [],
            "resources": [],
            "step_ids": ["0", "1", "2"],
        }
        r = client.post(f"/api/draft/{sid}/export", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        out_path = Path(body["path"])
        assert out_path.exists()
        # 文件位置: $GIMBAL_HOME/scenarios/{sid}.yaml
        assert out_path.parent == gimbal_home / "scenarios"
        assert out_path.name == f"{sid}.yaml"

        # 4. YAML 内容
        text = out_path.read_text(encoding="utf-8")
        assert "scenarioId" in text
        assert "e2e 测试" in text
        assert "/api/users" in text

        # 5. 重新加载 YAML 为 Scenario, 校验通过
        import yaml
        from gimbal.schema import Scenario
        loaded = yaml.safe_load(text)
        s = Scenario.model_validate(loaded)
        assert s.scenarioId == sid
        assert s.meta.name == "e2e 测试"
        assert len(s.steps) == 3

        # 6. 痛点 13 验证: assertion name 是 assert_status_{idx}
        assertion_names = [
            st.strategy[0].name
            for st in s.steps
            if st.strategy and st.strategy[0].kind == "assertion"
        ]
        assert "assert_status_1" in assertion_names
        assert "assert_status_2" in assertion_names
        assert "assert_status_3" in assertion_names

        # 7. 痛点 12 验证: resources 留空 (没填)
        assert s.resource == {}


def test_e2e_schema_validation_blocks_export(gimbal_home):
    """端到端反向: 空 name → 422 + 字段错误。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app

    with TestClient(app) as client:
        sid = "invalid"
        # 1 capture
        client.post("/api/captures/inject", params={"sid": sid}, json={
            "ts": 1.0, "method": "GET", "scheme": "https", "host": "x", "port": 443,
            "path": "/a", "query": {}, "headers": {}, "body": "",
            "response": {"status": 200, "headers": {}, "body": "{}"},
        })
        # 空 name draft
        payload = {
            "scenario_id": sid, "name": "",
            "description": "", "module": "m", "priority": 1,
            "author": "a", "owner": "o", "tags": [], "version": "1.0.0",
            "expire": False, "requirement_ref": [],
            "services": {}, "users": [],
            "time_policy_kind": "record", "time_policy_seconds": 60,
            "retry_enabled": False, "retry_max_attempts": 3,
            "retry_backoff_seconds": 20.0, "retry_on": [],
            "setup_refs": [], "teardown_refs": [],
            "resources": [], "step_ids": ["0"],
        }
        r = client.post(f"/api/draft/{sid}/export", json=payload)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "schema_errors" in detail
        assert any("name" in str(e.get("loc", "")) for e in detail["schema_errors"])


def test_e2e_ui_spec_drive_meta_form(gimbal_home):
    """端到端 schema 驱动: /api/schema/ui-spec 返回 meta 字段, name 必填。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app

    with TestClient(app) as client:
        r = client.get("/api/schema/ui-spec")
        assert r.status_code == 200
        spec = r.json()
        # meta group 存在
        meta = next((g for g in spec["groups"] if g["id"] == "meta"), None)
        assert meta is not None
        # name 字段必填
        name_field = next((f for f in meta["fields"] if f["path"] == "meta.name"), None)
        assert name_field is not None
        assert name_field["required"] is True
        # priority 是 select 1-3
        priority = next((f for f in meta["fields"] if f["path"] == "meta.priority"), None)
        assert priority["widget"] == "select"
        assert {o["value"] for o in priority["options"]} == {1, 2, 3}
