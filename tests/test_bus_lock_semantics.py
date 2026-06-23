"""gimbal.capture.bus — v0.5.2 锁语义回归测试。

修复前 (v0.5.1): msvcrt.locking 是 mandatory lock, 锁住 NDJSON 后其他进程
读任何字节都 PermissionError. prism CaptureReader.read() 必失败.

修复后: 用 .lock 哨兵文件 (O_CREAT|O_EXCL) 做 session 互斥, NDJSON 本身
无锁, 多读单写安全.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from gimbal.capture.bus import FileBus, SessionLockedError
from gimbal.capture.recorder import CaptureEvent
from gimbal.prism.state import CaptureReader, CaptureWatcher


def _make_event(method="GET", path="/api/test", **kw):
    return CaptureEvent(
        ts=kw.get("ts", time.time()),
        method=method, scheme="https", host="x.com", port=443,
        path=path, query={}, headers={}, body="",
        response_status=kw.get("response_status", 200),
        response_headers={}, response_body=kw.get("response_body", "ok"),
    )


# ─── 核心回归: capture 持锁, prism 同时读 (Windows 必过) ────────────────


def test_capture_writer_does_not_block_prism_reader(tmp_path):
    """v0.5.2 修复: capture FileBus 持有 .lock 哨兵, 但 NDJSON 文件本身可读.

    修复前: PermissionError [Errno 13] on Windows.
    """
    bus = FileBus(tmp_path, "reg1")
    bus.write(_make_event(path="/api/a"))
    bus.write(_make_event(path="/api/b"))

    reader = CaptureReader(tmp_path)
    events = reader.read("reg1", limit=None)  # 修复前 PermissionError, 修复后正常
    assert len(events) == 2
    assert events[0]["path"] == "/api/a"
    assert events[1]["path"] == "/api/b"


def test_capture_writer_does_not_block_prism_watcher_register(tmp_path):
    """watchdog 注册本身不要求文件被独占."""
    bus = FileBus(tmp_path, "reg2")
    bus.write(_make_event(path="/api/x"))

    watcher = CaptureWatcher(tmp_path)
    received = []
    handle = watcher.watch("reg2", lambda ev: received.append(ev))
    # 注册成功即 OK, 不需要再读文件
    assert handle._active
    handle.stop()


# ─── 哨兵文件行为 ─────────────────────────────────────────────────────────


def test_lock_file_created_on_open(tmp_path):
    """FileBus 打开时创建 {sid}.lock 哨兵."""
    bus = FileBus(tmp_path, "s1")
    assert bus.lock_path.exists()
    assert bus.lock_path.name == "s1.lock"
    bus.close()


def test_lock_file_removed_on_close(tmp_path):
    bus = FileBus(tmp_path, "s2")
    bus.write(_make_event())
    bus.close()
    assert not bus.lock_path.exists()


def test_lock_file_contains_pid(tmp_path):
    """哨兵文件写进程 PID (调试用)."""
    import os
    bus = FileBus(tmp_path, "s3")
    pid = bus.lock_path.read_text(encoding="utf-8").strip()
    assert pid == str(os.getpid())
    bus.close()


# ─── SessionLockedError 仍然有效 ─────────────────────────────────────────


def test_second_writer_raises_session_locked(tmp_path):
    """第二个 FileBus 同 session 启动 → 哨兵 O_EXCL 失败 → SessionLockedError."""
    bus1 = FileBus(tmp_path, "s4")
    bus1.write(_make_event())

    with pytest.raises(SessionLockedError):
        bus2 = FileBus(tmp_path, "s4")
        bus2.write(_make_event())  # _open_locked 时抛

    bus1.close()


def test_after_close_second_writer_can_open(tmp_path):
    """第一个 FileBus 关闭后, 第二个可以拿到哨兵 (cleanup 正常)."""
    bus1 = FileBus(tmp_path, "s5")
    bus1.write(_make_event(path="/a"))
    bus1.close()  # 哨兵应被删除

    bus2 = FileBus(tmp_path, "s5")
    bus2.write(_make_event(path="/b"))

    reader = CaptureReader(tmp_path)
    events = reader.read("s5", limit=None)
    assert len(events) == 2
    assert events[0]["path"] == "/a"
    assert events[1]["path"] == "/b"
    bus2.close()


# ─── 跨进程语义 (同进程内模拟两个 bus 实例) ────────────────────────────


def test_different_sessions_coexist(tmp_path):
    """不同 session 互不影响 (各自哨兵)."""
    bus_a = FileBus(tmp_path, "alpha")
    bus_a.write(_make_event(path="/a/1"))
    bus_b = FileBus(tmp_path, "beta")
    bus_b.write(_make_event(path="/b/1"))

    reader = CaptureReader(tmp_path)
    assert len(reader.read("alpha", limit=None)) == 1
    assert len(reader.read("beta", limit=None)) == 1

    bus_a.close()
    bus_b.close()
