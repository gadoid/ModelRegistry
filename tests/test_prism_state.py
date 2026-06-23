"""Smoke test for gimbal.prism.state (Session / SessionStore / CaptureReader)."""
import json
import tempfile
import time
from pathlib import Path

from gimbal.prism.state import SessionStore, Session, CaptureReader


def test_session_undo_redo():
    s = Session()
    s.draft = {"a": 1}
    s.push_history(s.snapshot())
    s.draft = {"a": 2}
    s.push_history(s.snapshot())
    s.draft = {"a": 3}
    # 3 个版本 (1, 2, 3), history 有 2 个快照
    assert s.draft == {"a": 3}
    assert len(s.history) == 2
    # undo → a=2
    s.undo()
    assert s.draft == {"a": 2}
    # undo → a=1
    s.undo()
    assert s.draft == {"a": 1}
    # undo → None (history 空)
    assert s.undo() is None
    # redo → a=2
    s.redo()
    assert s.draft == {"a": 2}
    # 任何新编辑清空 redo
    s.push_history(s.snapshot())
    s.draft = {"a": 99}
    assert s.redo() is None
    print("1. Session undo/redo OK")


def test_session_store():
    store = SessionStore()
    s1 = store.get_or_create("foo")
    s1.draft = {"k": "v"}
    s2 = store.get_or_create("foo")  # 已存在
    assert s2 is s1
    assert s2.draft == {"k": "v"}
    s3 = store.get_or_create("bar")
    assert s3 is not s1
    assert len(store) == 2
    store.delete("foo")
    assert len(store) == 1
    assert store.get("foo") is None
    print("2. SessionStore OK")


def test_capture_reader():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        reader = CaptureReader(home)
        # 不存在的 session
        assert reader.read("nope") == []
        assert reader.list_active() == []
        # 写入 3 条
        for i in range(3):
            reader.append("test-sid", {"ts": float(i), "method": "GET", "path": f"/a/{i}"})
        # list
        active = reader.list_active()
        assert len(active) == 1
        assert active[0]["session_id"] == "test-sid"
        # read 全部
        events = reader.read("test-sid", limit=None)
        assert len(events) == 3
        # read with limit
        assert len(reader.read("test-sid", limit=2)) == 2
        # truncate
        assert reader.truncate("test-sid") is True
        assert reader.read("test-sid") == []
        # 再次 truncate (文件已空, 仍返回 True 因为文件存在)
        assert reader.truncate("test-sid") is True
        # 不存在
        assert reader.truncate("nope") is False
    print("3. CaptureReader OK")


if __name__ == "__main__":
    test_session_undo_redo()
    test_session_store()
    test_capture_reader()
    print("\nAll state tests passed")
