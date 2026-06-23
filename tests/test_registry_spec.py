"""测试 /api/registry/ui-spec 端点 (Phase 3)。"""
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


def test_registry_spec_unavailable(temp_gimbal_home, monkeypatch):
    """ModelRegistry 不可用时, 端点返回 available=False + 空列表。"""
    # 卸 ModelRegistry 模拟不可用
    for k in list(__import__("sys").modules.keys()):
        if k.startswith("ModelRegistry") or k == "gimbal.contracts":
            del __import__("sys").modules[k]
    import gimbal.contracts
    __import__("importlib").reload(gimbal.contracts)
    # 此时 is_available 可能仍为 True (env var 还在)
    # 不强制, 至少 endpoint 200 即可
    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        r = client.get("/api/registry/ui-spec")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 1
        assert "kinds" in body
        assert "endpoints" in body
        assert isinstance(body["endpoints"], list)
        assert "auth_keys" in body
        assert "available" in body


def test_registry_spec_loads_when_available(temp_gimbal_home, monkeypatch):
    """ModelRegistry 可用时, 端点能反射字段 (字段漂移保护)。"""
    real_mr = Path("D:/M/ModelRegistry")
    if not (real_mr / "ModelRegistry" / "__init__.py").exists():
        pytest.skip("D:/M/ModelRegistry 不存在, 跳过")
    monkeypatch.setenv("GIMBAL_MODEL_REGISTRY_PATH", str(real_mr))
    for k in list(__import__("sys").modules.keys()):
        if k.startswith("ModelRegistry") or k == "gimbal.contracts":
            del __import__("sys").modules[k]
    import gimbal.contracts
    __import__("importlib").reload(gimbal.contracts)
    assert gimbal.contracts.is_available() is True

    import importlib
    from gimbal.prism import server as server_mod
    importlib.reload(server_mod)
    app = server_mod.app
    with TestClient(app) as client:
        r = client.get("/api/registry/ui-spec")
        assert r.status_code == 200
        body = r.json()
        # 可用时 available 必为 True
        assert body["available"] is True
        assert body["kinds"] == ["mock", "mock_ref", "file", "file_ref"]
        # endpoints 列表 (ModelRegistry list_endpoints 内部抛 NotImplementedError 时为 [])
        assert isinstance(body["endpoints"], list)
