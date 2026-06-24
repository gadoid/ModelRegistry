"""导入流程 E2E 测试: 模拟 .ndjson 文件被 _importNdjsonFile 处理,
验证 server 端 captures 累计 + 客户端能从 captures 派生 steps。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app

FIXTURE = Path("D:/M/ModelRegistry/tests/fixtures/sample_captures.ndjson")


@pytest.fixture
def client():
    # 必须用 `with TestClient(app) as client:` 触发 lifespan, 初始化 app.state.sessions
    with TestClient(app) as c:
        yield c


def test_ndjson_fixture_loads():
    """fixture 文件存在且可解析。"""
    assert FIXTURE.exists(), f"fixture 缺失: {FIXTURE}"
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    for line in lines:
        ev = json.loads(line)
        assert "method" in ev and "path" in ev


def test_captures_inject_and_list(client):
    """模拟 _importNdjsonFile 行为: 逐行 POST /api/captures/inject, 然后 GET 列表。"""
    sid = "import-e2e-sid"
    # 清掉残留 (capture file 持久化在 disk, 跨 test run 累积)
    client.delete(f"/api/captures?sid={sid}")
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    n_ok = 0
    for line in lines:
        ev = json.loads(line)
        r = client.post(f"/api/captures/inject?sid={sid}", json=ev)
        assert r.status_code == 200, r.text
        n_ok += 1
    assert n_ok == 3, f"应注入 3 条, 实际 {n_ok}"
    r = client.get(f"/api/captures?sid={sid}")
    assert r.status_code == 200
    data = r.json()
    assert len(data.get("events", [])) == 3, f"server 端应有 3 条, 实际 {len(data.get('events', []))}"


def test_app_js_import_from_file_uses_inject_endpoint():
    """app.js 内的 _importNdjsonFile 必须 POST /api/captures/inject (带 sid query)。"""
    app_js = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")
    text = app_js.read_text(encoding="utf-8")
    # 端点 URL 必须包含 sid query (server 端 Query(...) 是必填)
    assert "/api/captures/inject" in text, \
        "_importNdjsonFile 必须调 /api/captures/inject"
    assert "sid=" in text, "POST URL 必须带 sid query 参数 (server 端要求)"
    assert "encodeURIComponent(state.sessionId" in text, \
        "应使用 state.sessionId 编码为 sid"
    assert "JSON.parse(line)" in text, "应逐行 JSON 解析"
    # 校验后缀
    assert "/\\.ndjson$/i.test(file.name)" in text, "应做 .ndjson 后缀校验"
    # 空文件早返
    assert "文件为空" in text, "空文件应 toast"


def test_draft_persistence_with_imported_steps(client):
    """导入后构造 draft 包含 3 个 step (与 fixture 一一对应), PUT/GET 验证。"""
    sid = "import-e2e-draft"
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    steps = []
    for i, line in enumerate(lines):
        ev = json.loads(line)
        steps.append({
            "id": f"step-{i+1}",
            "api": {
                "service": f"{ev.get('scheme', 'https')}://{ev.get('host', 'api.example.com')}",
                "method": ev["method"], "path": ev["path"],
            },
            "req": {"params": ev.get("query", {}),
                    "headers": ev.get("headers", {}),
                    "body": ev.get("body", {})},
            "assertions": [], "extracts": [], "assigns": [],
            "key_hint": "",
            "capture": ev,
        })
    draft = {
        "scenario_id": sid, "name": "imported", "description": "",
        "module": "default", "priority": 1, "author": "prism", "owner": "prism",
        "tags": [], "version": "1.0.0", "expire": False,
        "requirement_ref": [], "services": {}, "users": [],
        "time_policy_kind": "record", "time_policy_seconds": 60,
        "retry_enabled": False, "retry_max_attempts": 3,
        "retry_backoff_seconds": 20, "retry_on": [],
        "setup_refs": [], "teardown_refs": [],
        "resources": [], "steps": steps,
    }
    r = client.put(f"/api/draft/{sid}", json=draft)
    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/draft/{sid}")
    assert r2.status_code == 200
    data = r2.json()
    # server 把 draft 嵌套在 data["draft"] 下
    assert len(data["draft"]["steps"]) == 3
    assert data["draft"]["steps"][0]["api"]["path"] == "/api/login"
