"""doc2model 迁移测试 (v0.2.2)。"""
import json
import os
import tempfile
from pathlib import Path


def test_doc2model_imports():
    """gimbal.prism.doc2model 独立可 import。"""
    from gimbal.prism import doc2model
    assert callable(doc2model.main)
    assert callable(doc2model.load_samples)


def test_doc2model_load_samples():
    """从 NDJSON 读 capture 样本。"""
    from gimbal.prism.doc2model import load_samples
    with tempfile.TemporaryDirectory() as td:
        nd = Path(td) / "captures.ndjson"
        lines = [
            {
                "ts": 1.0, "method": "POST", "scheme": "https", "host": "x", "port": 443,
                "path": "/api/orders", "query": {}, "headers": {"content-type": "application/json"},
                "body": json.dumps({"name": "x", "qty": 1}),
                "response": {"status": 201, "headers": {}, "body": json.dumps({"id": 1})},
            },
            {
                "ts": 2.0, "method": "POST", "scheme": "https", "host": "x", "port": 443,
                "path": "/api/orders", "query": {}, "headers": {"content-type": "application/json"},
                "body": json.dumps({"name": "y", "qty": 2}),
                "response": {"status": 201, "headers": {}, "body": json.dumps({"id": 2})},
            },
        ]
        nd.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        samples = load_samples(nd, None)
        assert len(samples) == 2
        assert samples[0]["method"] == "POST"
        assert samples[0]["path"] == "/api/orders"
        assert samples[0]["body"] == {"name": "x", "qty": 1}


def test_doc2model_into_registry_requires_modelregistry(tmp_path, monkeypatch):
    """--into-registry + ModelRegistry 不可用 → 退出码 3 + 友好提示。"""
    import importlib
    import sys

    # 卸掉 ModelRegistry 模拟不可用
    for k in list(sys.modules.keys()):
        if k.startswith("ModelRegistry") or k == "gimbal.contracts":
            del sys.modules[k]

    # 卸 contracts 让 is_available() 重新计算
    if "gimbal.contracts" in sys.modules:
        importlib.reload(sys.modules["gimbal.contracts"])
    # 此时没有 env var, 应 False
    from gimbal.contracts import is_available
    # 强制 False (兼容某些平台已装 model-registry-local)
    if is_available():
        import pytest
        pytest.skip("ModelRegistry 已装, 跳过不可用降级测试")

    # 准备一个 NDJSON 文件
    nd = tmp_path / "captures.ndjson"
    nd.write_text(json.dumps({
        "ts": 1.0, "method": "GET", "scheme": "https", "host": "x", "port": 443,
        "path": "/a", "query": {}, "headers": {}, "body": "",
        "response": {"status": 200, "headers": {}, "body": "{}"},
    }) + "\n", encoding="utf-8")

    from gimbal.prism.doc2model import main
    rc = main([
        "--in", str(nd),
        "--service", "test_svc",
        "--method", "GET",
        "--path", "/a",
        "--into-registry",
    ])
    assert rc == 3


def test_doc2model_out_dir_default(tmp_path, monkeypatch):
    """默认 --out-dir 模式应正常生成 models.py。"""
    nd = tmp_path / "captures.ndjson"
    nd.write_text(json.dumps({
        "ts": 1.0, "method": "GET", "scheme": "https", "host": "x", "port": 443,
        "path": "/a", "query": {}, "headers": {}, "body": "",
        "response": {"status": 200, "headers": {}, "body": json.dumps({"id": 1, "name": "x"})},
    }) + "\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    from gimbal.prism.doc2model import main
    rc = main([
        "--in", str(nd),
        "--service", "test_svc",
        "--method", "GET",
        "--path", "/a",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    # 生成的 models.py 存在
    assert (out_dir / "test_svc" / "models.py").exists()
    text = (out_dir / "test_svc" / "models.py").read_text(encoding="utf-8")
    assert "BaseModel" in text
    assert "ConfigDict" in text
    assert "extra='forbid'" in text
    assert "AutoRequest" in text
    assert "AutoResponse" in text
