"""Fix #10: ``/api/captures/import-from-path`` 必须沙箱化。

痛点: path 必须落在 CWD 内 (默认), 否则返回 403。
v0 改造: 走 gimbal.prism.server, lifespan 内 capture_reader,
/api/captures/import-from-path 端点用 CWD 校验。

注: 因 Windows 上 watchdog Observer 在 teardown 时可能仍持 file handle,
本测试用 `os.chdir` 手动改 + fixture 结束时还原, 而不是 monkeypatch.chdir +
TemporaryDirectory 嵌套 (避免清理冲突)。
"""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app as fastapi_app


@pytest.fixture
def client_with_cwd(monkeypatch):
    """临时工作目录 + 一份合法 captures.ndjson。"""
    # 保留原 CWD, 结束时还原
    original_cwd = os.getcwd()
    tmp_dir = tempfile.mkdtemp(prefix="gimbal_test_")
    tmp_path = Path(tmp_dir)
    # 配 GIMBAL_HOME
    home = tmp_path / ".gimbal"
    home.mkdir()
    monkeypatch.setenv("GIMBAL_HOME", str(home))
    # 切 CWD
    os.chdir(tmp_path)
    # 合法 captures.ndjson 在 CWD 内
    nd = tmp_path / "captures.ndjson"
    nd.write_text(
        '{"ts":1.0,"method":"GET","scheme":"http","host":"x","port":80,"path":"/","query":{},"headers":{},"body":"","response":{"status":200,"headers":{},"body":"{}"}}\n',
        encoding="utf-8",
    )
    client = TestClient(fastapi_app)
    # 触发 lifespan (startup)
    client.__enter__()
    try:
        yield client, tmp_path, nd
    finally:
        # 先关 client (触发 lifespan teardown, 停 watchdog Observer)
        try:
            client.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        # 还原 CWD
        os.chdir(original_cwd)
        # 清理临时目录
        import shutil
        try:
            shutil.rmtree(tmp_path, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


def test_import_from_path_accepts_cwd_relative(client_with_cwd):
    """CWD 相对路径应被接受。"""
    client, tmp_path, nd = client_with_cwd
    r = client.post("/api/captures/import-from-path", params={"sid": "import-test"}, json={"path": "captures.ndjson"})
    assert r.status_code == 200
    assert r.json()["imported"] == 1


def test_import_from_path_rejects_absolute_outside_cwd(client_with_cwd):
    """CWD 之外的绝对路径应被 403 拒绝。"""
    client, tmp_path, _ = client_with_cwd
    r = client.post("/api/captures/import-from-path", params={"sid": "x"}, json={"path": "C:\\Windows\\System32\\drivers\\etc\\hosts"})
    assert r.status_code == 403


def test_import_from_path_rejects_path_traversal(client_with_cwd):
    """``../../etc/passwd`` 穿越应被 403 拒绝。"""
    client, tmp_path, _ = client_with_cwd
    r = client.post("/api/captures/import-from-path", params={"sid": "x"}, json={"path": "../../etc/passwd"})
    assert r.status_code == 403


def test_import_from_path_missing_path_returns_404(client_with_cwd):
    """path 不存在应返回 404 (不绕过沙箱检查)。"""
    client, tmp_path, _ = client_with_cwd
    r = client.post("/api/captures/import-from-path", params={"sid": "x"}, json={"path": "nope.ndjson"})
    assert r.status_code == 404
