"""Step 分页 E2E 测试: HTTP 层面验证 draft 含 25 steps 时,
prism server 能正常 GET /, 前端 app.js 含分页原语。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _make_steps(n: int) -> list:
    return [
        {
            "id": f"step-{i+1}",
            "api": {"service": "https://api.example.com", "method": ["GET", "POST", "PUT"][i % 3], "path": f"/api/order/{i+1}"},
            "req": {"params": {}, "headers": {}, "body": {}},
            "assertions": [], "extracts": [], "assigns": [],
            "key_hint": f"call_{i+1}",
        }
        for i in range(n)
    ]


@pytest.fixture
def client():
    # 必须用 `with TestClient(app) as client:` 触发 lifespan, 初始化 app.state.sessions
    with TestClient(app) as c:
        yield c


def test_draft_with_25_steps_serves_ok(client):
    sid = "test-sid-25"
    draft = {
        "scenario_id": sid,
        "name": "test", "description": "", "module": "default",
        "priority": 1, "author": "prism", "owner": "prism",
        "tags": [], "version": "1.0.0", "expire": False,
        "requirement_ref": [], "services": {}, "users": [],
        "time_policy_kind": "record", "time_policy_seconds": 60,
        "retry_enabled": False, "retry_max_attempts": 3,
        "retry_backoff_seconds": 20, "retry_on": [],
        "setup_refs": [], "teardown_refs": [],
        "resources": [], "steps": _make_steps(25),
    }
    r = client.put(f"/api/draft/{sid}", json=draft)
    assert r.status_code == 200, r.text
    r2 = client.get(f"/configure?session={sid}")
    assert r2.status_code == 200
    # 验证 HTML 含新结构
    body = r2.text
    assert 'id="step-sidebar"' in body
    assert 'id="step-tags"' in body
    assert 'id="step-detail"' in body
    assert 'id="ndjson-file-input"' in body
    # 旧结构应已不在
    assert 'id="import-btn"' not in body
    assert 'id="expand-all"' not in body
    assert 'id="collapse-all"' not in body


def test_draft_with_0_steps_keeps_no_sidebar(client):
    sid = "test-sid-0"
    draft = {
        "scenario_id": sid, "name": "empty", "description": "",
        "module": "default", "priority": 1, "author": "prism", "owner": "prism",
        "tags": [], "version": "1.0.0", "expire": False,
        "requirement_ref": [], "services": {}, "users": [],
        "time_policy_kind": "record", "time_policy_seconds": 60,
        "retry_enabled": False, "retry_max_attempts": 3,
        "retry_backoff_seconds": 20, "retry_on": [],
        "setup_refs": [], "teardown_refs": [], "resources": [], "steps": [],
    }
    r = client.put(f"/api/draft/{sid}", json=draft)
    assert r.status_code == 200
    r2 = client.get(f"/configure?session={sid}")
    assert r2.status_code == 200
    # 空 draft 仍能 serve, sidebar 容器存在 (运行时 hidden)
    body = r2.text
    assert 'id="step-sidebar"' in body


def test_app_js_loads_draft_into_state_steps():
    """客户端从 draft 加载 steps 的逻辑必须保留。"""
    text = APP_JS.read_text(encoding="utf-8")
    # draft.step_ids 或 draft.steps 赋值给 state.steps
    assert "state.steps =" in text, "app.js 必须从 draft 加载 state.steps"
    # step 渲染路径走 renderStepTags (新增)
    assert "renderStepTags()" in text


def test_page_size_ten():
    text = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"PAGE_SIZE\s*=\s*(\d+)", text)
    assert m
    assert int(m.group(1)) == 10