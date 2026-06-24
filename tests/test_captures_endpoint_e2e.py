"""端到端: 验证 prism server ``/api/captures`` 的 sid 契约 + client 修复后的行为一致。

这是对 Bug 2 (_pullCaptures / clear-captures 漏 sid) 的 server-side 集成层保障,
覆盖:
- GET 不带 sid → 422 (验证 server 端契约, 解释为什么前端必须带 sid)
- GET 带 sid → 200 + 真实数据 (验证 _pullCaptures 修复后能拿到数据)
- POST inject → 单 event 追加
- DELETE 带 sid → 真清空 (验证 clear-captures 修复后能真生效)
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from gimbal.prism.server import app


def test_get_captures_without_sid_returns_422():
    """不传 sid 必返回 422 — 这就是 Bug 2 的根因 (server 端 Query(...) 必填)。"""
    with TestClient(app) as client:
        r = client.get("/api/captures")
    assert r.status_code == 422, r.text
    body = r.json()
    assert any(d.get("loc", [])[-1] == "sid" for d in body.get("detail", [])), \
        f"422 错误应指向 sid 字段: {body}"


def test_pull_captures_round_trip_with_sid():
    """完整链路: POST inject × N → GET with sid → 拿到全部事件 (这是 _pullCaptures 修复后的行为)。"""
    sid = "test-pull-captures-rt"
    with TestClient(app) as client:
        client.delete(f"/api/captures?sid={sid}")
        events = [
            {"ts": 1.0, "method": "POST", "host": "api.example.com",
             "scheme": "https", "port": 443, "path": "/api/login",
             "query": {}, "headers": {}, "body": "{}",
             "response": {"status": 200}, "response_ms": 120},
            {"ts": 2.0, "method": "GET", "host": "api.example.com",
             "scheme": "https", "port": 443, "path": "/api/order/1",
             "query": {}, "headers": {}, "body": "{}",
             "response": {"status": 200}, "response_ms": 50},
        ]
        for ev in events:
            r = client.post(f"/api/captures/inject?sid={sid}", json=ev)
            assert r.status_code == 200, r.text
        # 这是修复后的 _pullCaptures 走的 URL 模式
        r = client.get(f"/api/captures?sid={sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert len(data["events"]) == 2
        # 真清空 (这是 clear-captures 修复后走的 URL 模式)
        r = client.delete(f"/api/captures?sid={sid}")
        assert r.status_code == 200
        assert r.json() == {"status": "cleared", "sid": sid}
        r = client.get(f"/api/captures?sid={sid}")
        assert r.json()["count"] == 0


def test_pull_captures_different_sid_isolation():
    """不同 sid 的 captures 互不串。"""
    sid_a, sid_b = "iso-sid-a", "iso-sid-b"
    with TestClient(app) as client:
        client.delete(f"/api/captures?sid={sid_a}")
        client.delete(f"/api/captures?sid={sid_b}")
        ev = {"ts": 1.0, "method": "GET", "host": "x", "scheme": "https",
              "port": 443, "path": "/", "query": {}, "headers": {},
              "body": "", "response": {"status": 200}, "response_ms": 1}
        client.post(f"/api/captures/inject?sid={sid_a}", json=ev)
        a = client.get(f"/api/captures?sid={sid_a}").json()
        b = client.get(f"/api/captures?sid={sid_b}").json()
        assert a["count"] == 1, f"sid_a 应有 1 条, 实际 {a['count']}"
        assert b["count"] == 0, f"sid_b 应有 0 条, 实际 {b['count']}"
        # 清理
        client.delete(f"/api/captures?sid={sid_a}")
