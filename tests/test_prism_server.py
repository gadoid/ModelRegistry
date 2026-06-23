"""FastAPI server 集成测试 (痛点 11 lifespan 验证)。"""
import json
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


def test_lifespan_initializes_app_state(temp_gimbal_home):
    """痛点 11: 启动后 app.state 应有 home / sessions / capture_reader / capture_watcher。"""
    # 强制 reimport (lifespan 用 env var 解析 home)
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert "sessions" in body
        assert "captures_active" in body


def test_captures_file_roundtrip(temp_gimbal_home):
    """captures 走文件: append → read → truncate。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        # inject
        ev = {"ts": 1.0, "method": "GET", "scheme": "https", "host": "x", "port": 443,
              "path": "/api/foo", "query": {}, "headers": {}, "body": "",
              "response": {"status": 200, "headers": {}, "body": "{}"}}
        r = client.post("/api/captures/inject", params={"sid": "s1"}, json=ev)
        assert r.status_code == 200
        # list
        r = client.get("/api/captures", params={"sid": "s1"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["events"][0]["path"] == "/api/foo"
        # delete (truncate)
        r = client.delete("/api/captures", params={"sid": "s1"})
        assert r.status_code == 200
        r = client.get("/api/captures", params={"sid": "s1"})
        assert r.json()["count"] == 0


def test_export_yaml_422_on_empty_meta_name(temp_gimbal_home):
    """空 name → 422 + 字段错误 (痛点 5 行为保留)。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        payload = {
            "scenario_id": "sc_x", "name": "",
            "description": "", "module": "default", "priority": 1,
            "author": "x", "owner": "x", "tags": ["smoke"], "version": "1.0.0",
            "expire": False, "requirement_ref": [],
            "services": {}, "users": [],
            "time_policy_kind": "record", "time_policy_seconds": 60,
            "retry_enabled": False, "retry_max_attempts": 3,
            "retry_backoff_seconds": 20.0, "retry_on": [],
            "setup_refs": [], "teardown_refs": [],
            "resources": [], "step_ids": [],
        }
        r = client.post("/api/draft/test-sid/export", json=payload)
        assert r.status_code == 422
        body = r.json()
        assert "schema_errors" in body["detail"]
        assert any("name" in str(err.get("loc", "")) for err in body["detail"]["schema_errors"])


def test_export_yaml_writes_to_scenarios_dir(temp_gimbal_home):
    """合法 draft → 写 $GIMBAL_HOME/scenarios/{sid}.yaml。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        # inject 一条 capture
        ev = {"ts": 1.0, "method": "GET", "scheme": "https", "host": "a.example.com",
              "port": 443, "path": "/api/foo", "query": {}, "headers": {},
              "body": "", "response": {"status": 200, "headers": {}, "body": "{}"}}
        client.post("/api/captures/inject", params={"sid": "ok-sid"}, json=ev)
        payload = {
            "scenario_id": "ok-sid", "name": "合法用例",
            "description": "d", "module": "m", "priority": 1,
            "author": "a", "owner": "o", "tags": ["smoke"], "version": "1.0.0",
            "expire": False, "requirement_ref": [],
            "services": {"a.example.com": "https://a.example.com/"},
            "users": [],
            "time_policy_kind": "record", "time_policy_seconds": 60,
            "retry_enabled": False, "retry_max_attempts": 3,
            "retry_backoff_seconds": 20.0, "retry_on": [],
            "setup_refs": [], "teardown_refs": [],
            "resources": [], "step_ids": ["0"],
        }
        r = client.post("/api/draft/ok-sid/export", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        out = Path(body["path"])
        assert out.exists()
        assert out.parent.parent == temp_gimbal_home
        # 文件内容
        text = out.read_text(encoding="utf-8")
        assert "scenarioId" in text
        assert "合法用例" in text


def test_no_module_level_singletons():
    """痛点 11: 启动前不应有 module-level mutable 单例 (recorder / ws_clients / _loop / sessions)。"""
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    forbidden = ["recorder", "ws_clients", "_loop"]
    for name in forbidden:
        assert not hasattr(server_mod, name), (
            f"痛点 11 未修: server.py 仍有模块级单例 {name!r}"
        )
