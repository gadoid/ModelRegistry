"""Smoke test for gimbal.capture module."""
import json
import time
import tempfile
from pathlib import Path

from gimbal.capture.bus import FileBus, SessionLockedError
from gimbal.capture.recorder import CaptureEvent, event_from_dict
from gimbal.capture.filter import PathFilter
from gimbal.capture.archive import archive_session


def test_capture_event_to_dict():
    ev = CaptureEvent(
        ts=time.time(), method="GET", scheme="https", host="api.example.com",
        port=443, path="/api/users", query={"a": "1"}, headers={"X-Foo": "bar"},
        body="", response_status=200, response_headers={"Content-Type": "application/json"},
        response_body='{"users": []}',
    )
    d = ev.to_dict()
    assert d["response"]["status"] == 200
    assert d["response"]["headers"] == {"Content-Type": "application/json"}
    assert d["response"]["body"] == '{"users": []}'
    print("1. CaptureEvent.to_dict() OK")


def test_file_bus_write_and_lock():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        ev = CaptureEvent(
            ts=1.0, method="GET", scheme="https", host="api.example.com",
            port=443, path="/api/users", body="",
            response_status=200, response_body="{}",
        )
        bus = FileBus(home, "test-sid")
        bus.write(ev)
        bus.close()
        out = home / "captures" / "active" / "test-sid.ndjson"
        assert out.exists()
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/api/users"
        assert parsed["response"]["status"] == 200
        # 重开 (close 后锁已释放)
        bus2 = FileBus(home, "test-sid")
        bus2.write(ev)
        bus2.close()
        lines2 = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines2) == 2
        print("2. FileBus.write() + lock + re-open OK")


def test_path_filter_boundaries():
    f = PathFilter.from_csv("/api/order,/api/user")
    assert f.match("/api/order")
    assert f.match("/api/order/123")
    assert not f.match("/api/orderlist"), "前缀不应误伤 /api/orderlist"
    assert f.match("/api/user/42")
    assert not f.match("/api/other")
    # 空过滤 = 全部通过
    empty = PathFilter.from_csv("")
    assert empty.match("/anything")
    print("3. PathFilter 边界 OK")


def test_archive_session():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        ev = CaptureEvent(
            ts=1.0, method="GET", scheme="https", host="x", port=443, path="/", body="",
            response_status=200,
        )
        bus = FileBus(home, "test-sid")
        bus.write(ev)
        bus.close()
        archive_dst = archive_session(home, "test-sid")
        assert archive_dst is not None
        assert archive_dst.exists()
        assert not (home / "captures" / "active" / "test-sid.ndjson").exists()
        # 不存在的 session
        assert archive_session(home, "nope") is None
    print("4. archive_session OK")


def test_event_from_dict_roundtrip():
    raw = {
        "ts": 1.0, "method": "POST", "scheme": "http", "host": "x", "port": 80,
        "path": "/a", "query": {"q": "1"}, "headers": {}, "body": "",
        "response": {"status": 201, "headers": {}, "body": "{}"},
    }
    ev = event_from_dict(raw)
    assert ev.method == "POST"
    assert ev.response_status == 201
    # roundtrip
    d2 = ev.to_dict()
    assert d2["method"] == "POST"
    assert d2["response"]["status"] == 201
    print("5. event_from_dict roundtrip OK")


if __name__ == "__main__":
    test_capture_event_to_dict()
    test_file_bus_write_and_lock()
    test_path_filter_boundaries()
    test_archive_session()
    test_event_from_dict_roundtrip()
    print("\nAll smoke tests passed")
