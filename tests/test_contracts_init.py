"""测试 gimbal.contracts (Phase 3 ModelRegistry 引入) 三种状态。"""
import importlib
import os
import sys
from pathlib import Path

import pytest


def test_contracts_unavailable_when_nothing(monkeypatch):
    """未装 + 未设环境变量 → is_available() False。"""
    # 移除 sys.modules 中可能的缓存, 然后用干净环境 reload
    monkeypatch.delenv("GIMBAL_MODEL_REGISTRY_PATH", raising=False)
    # 卸掉已 import 的 ModelRegistry
    for k in list(sys.modules.keys()):
        if k.startswith("ModelRegistry") or k == "gimbal.contracts":
            del sys.modules[k]
    import gimbal.contracts
    importlib.reload(gimbal.contracts)
    # 如果 build venv 已装 model-registry-local, 这里会是 True (跳过此测试)
    # 没装时才 False
    if "ModelRegistry" not in sys.modules:
        assert gimbal.contracts.is_available() is False
        assert gimbal.contracts.registry is None
    else:
        pytest.skip("model-registry-local 已装, 跳过不可用状态测试")


def test_contracts_loads_via_env_path(monkeypatch, tmp_path):
    """未装 + 环境变量指向正确路径 → 加载成功。"""
    monkeypatch.delenv("GIMBAL_MODEL_REGISTRY_PATH", raising=False)
    # 模拟 D:/M/ModelRegistry 结构
    fake_mr = tmp_path / "fake_mr" / "ModelRegistry"
    fake_mr.mkdir(parents=True)
    (fake_mr / "__init__.py").write_text(
        "registry = None\n"
        "class BootstrapError(Exception): pass\n"
    )
    (fake_mr / "spec.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class EndpointSpec:\n"
        "    method: str\n"
        "    path: str\n"
        "    host: str = ''\n"
        "    id: str = ''\n"
        "class MockHook: pass\n"
        "class ValidateHook: pass\n"
        "class BuildRequestHook: pass\n"
    )
    (fake_mr / "core.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class EndpointKey:\n"
        "    service: str\n"
        "    method: str\n"
        "    path: str\n"
    )
    monkeypatch.setenv("GIMBAL_MODEL_REGISTRY_PATH", str(tmp_path / "fake_mr"))

    # 卸掉缓存 + reload
    for k in list(sys.modules.keys()):
        if k.startswith("ModelRegistry") or k == "gimbal.contracts":
            del sys.modules[k]
    import gimbal.contracts
    importlib.reload(gimbal.contracts)
    assert gimbal.contracts.is_available() is True
    assert gimbal.contracts.EndpointSpec.__name__ == "EndpointSpec"


def test_contracts_endpoint_key_dataclass():
    """EndpointKey 是 frozen dataclass, 可作 dict key。"""
    from gimbal.contracts import EndpointKey
    k1 = EndpointKey(service="s1", method="GET", path="/a")
    k2 = EndpointKey(service="s1", method="GET", path="/a")
    assert k1 == k2
    d = {k1: "v"}
    assert d[k2] == "v"


def test_contracts_via_real_d_mirror():
    """直接用 D:/M/ModelRegistry 真实路径验证 (假设开发环境有这路径)。"""
    import dataclasses
    real_mr = Path("D:/M/ModelRegistry")
    if not (real_mr / "ModelRegistry" / "__init__.py").exists():
        pytest.skip("D:/M/ModelRegistry 不存在, 跳过")
    os.environ["GIMBAL_MODEL_REGISTRY_PATH"] = str(real_mr)
    for k in list(sys.modules.keys()):
        if k.startswith("ModelRegistry") or k == "gimbal.contracts":
            del sys.modules[k]
    import gimbal.contracts
    importlib.reload(gimbal.contracts)
    assert gimbal.contracts.is_available() is True
    from gimbal.contracts import EndpointSpec
    # Pydantic v2 dataclass: 用 dataclasses.fields 检查字段
    fields = {f.name for f in dataclasses.fields(EndpointSpec)}
    assert "method" in fields
    assert "path" in fields
    assert "request" in fields
