"""去掉 `_mergeCapturesIntoSteps` 的 method+path dedup 后, 验证:

1. `_mergeCapturesIntoSteps` 函数体内不再构造 sigSet, 不再按 method+path 跳过 capture
2. server 端 `/api/captures` 不会自动去重 (按行追加)
3. 用 dup_captures.ndjson fixture (含重复 method+path) 跑通 inject → list 全链路,
   server 端 captures 数量 == fixture 行数
4. app.js 的 WS onmessage 'hello' 分支 (autoInjectToSteps 开启) 在重新灌入前清空 state.steps,
   防止 WS 重连产生重复 step

fixtures/dup_captures.ndjson 故意包含 5 行, 其中 ``GET /`` 出现 2 次,
``GET /api/login``、``POST /api/order``、``GET /api/order/1`` 各 1 次.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")
FIXTURE = Path("D:/M/ModelRegistry/tests/fixtures/dup_captures.ndjson")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ─── fixture 自身校验 ────────────────────────────────────────────────


def test_dup_fixture_has_duplicate_method_path():
    """fixture 必须真的含重复 method+path, 否则本文件其它测试是空测。"""
    assert FIXTURE.exists(), f"fixture 缺失: {FIXTURE}"
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    sigs = []
    for line in lines:
        ev = json.loads(line)
        sigs.append(f"{ev['method']}|{ev['path']}")
    assert len(lines) == 5, f"fixture 应有 5 行, 实际 {len(lines)}"
    assert len(set(sigs)) == 4, (
        f"fixture 应只有 4 个唯一 method+path (5 行有 1 行重复), 实际唯一 {len(set(sigs))}: {sigs}"
    )
    # 重复行必须是 GET /
    assert sigs.count("GET|/") == 2, f"GET / 应出现 2 次, 实际 {sigs.count('GET|/')}"


# ─── app.js 静态校验: dedup 已去掉 ───────────────────────────────────


def _read_app_js() -> str:
    assert APP_JS.exists(), f"app.js 不存在: {APP_JS}"
    return APP_JS.read_text(encoding="utf-8")


def _extract_function_body(text: str, fname: str) -> str:
    m = re.search(
        rf"(?:async\s+)?function\s+{re.escape(fname)}\s*\([^)]*\)\s*\{{(.*?)\n\}}",
        text,
        re.DOTALL,
    )
    assert m, f"未找到 {fname} 函数体"
    return m.group(1)


def test_merge_into_steps_no_sigset():
    """``_mergeCapturesIntoSteps`` 函数体内不能再出现 sigSet / method|path 字符串拼接。"""
    text = _read_app_js()
    body = _extract_function_body(text, "_mergeCapturesIntoSteps")
    assert "sigSet" not in body, (
        "_mergeCapturesIntoSteps 不应再构造 sigSet (去掉了 dedup), "
        "请把函数体里的 `const sigSet = new Set(...)` 段删除"
    )
    assert "${c.method || ''}|${c.path || ''}" not in body, (
        "不应再按 `${c.method}|${c.path}` 计算签名"
    )
    assert "${s.capture?.method || s.api?.method || ''}|" not in body, (
        "不应再从 state.steps 派生 method|path 签名集"
    )


def test_merge_into_steps_no_skip_via_signature():
    """函数体内不能再用 `sigSet.has(sig)` 跳过 capture。"""
    text = _read_app_js()
    body = _extract_function_body(text, "_mergeCapturesIntoSteps")
    assert "sigSet.has" not in body, (
        "不应再有 sigSet.has 跳过逻辑 (dedup 已移除)"
    )


def test_merge_into_steps_pushes_every_capture():
    """函数体应: 遍历 state.captures → 直接 _eventToStepDraft + push, 无跳过条件。"""
    text = _read_app_js()
    body = _extract_function_body(text, "_mergeCapturesIntoSteps")
    # 期望结构: for (...) { _eventToStepDraft; __sid; push; }
    assert "for (const c of state.captures)" in body, \
        "应仍遍历 state.captures"
    assert "_eventToStepDraft(c)" in body, \
        "应仍调 _eventToStepDraft"
    assert "state.steps.push(ns)" in body, \
        "应仍 push 到 state.steps"


# ─── app.js 静态校验: WS hello 在 autoInject 分支清 state.steps ──────


def test_ws_hello_clears_state_steps_when_auto_inject():
    """WS 'hello' 帧 + autoInjectToSteps=true 分支, 在 _mergeCapturesIntoSteps 之前
    必须先清空 state.steps, 防止 WS 重连产生重复 step。"""
    text = _read_app_js()
    # 找 hello 分支
    hello_idx = text.find("p.type === 'hello'")
    assert hello_idx > 0, "未找到 WS hello 分支"
    # 取从 hello 到下一个 if (p.type === 'capture') 之间的窗口
    capture_idx = text.find("p.type === 'capture'", hello_idx)
    assert capture_idx > hello_idx, "未找到 capture 分支"
    snippet = text[hello_idx: capture_idx]
    # 必须含 state.steps = [] 或 splice 清空
    assert re.search(r"state\.steps\s*=\s*\[\s*\]", snippet), (
        "WS hello + autoInject 分支应在 _mergeCapturesIntoSteps 之前清空 state.steps "
        "(用户要求 WS 重连时不产生重复 step)"
    )
    # 清空语句必须出现在 _mergeCapturesIntoSteps() 调用之前
    clear_pos = snippet.find("state.steps = []")
    merge_pos = snippet.find("_mergeCapturesIntoSteps()")
    assert clear_pos >= 0 and merge_pos >= 0, (
        "找不到清空语句或 _mergeCapturesIntoSteps 调用"
    )
    assert clear_pos < merge_pos, (
        f"清空 state.steps 必须在 _mergeCapturesIntoSteps 之前, "
        f"实际 clear@{clear_pos} merge@{merge_pos}"
    )


def test_ws_capture_frame_does_not_clear_state_steps():
    """WS 'capture' 帧 (单条新事件) 不应清 state.steps — 仅 hello 帧 (整体 replay) 清。"""
    text = _read_app_js()
    capture_idx = text.find("p.type === 'capture'")
    assert capture_idx > 0
    # 找 capture 分支的右大括号或下一个分支
    next_hello = text.find("p.type === 'hello'", capture_idx)
    end = next_hello if next_hello > capture_idx else capture_idx + 1000
    snippet = text[capture_idx: end]
    # capture 分支不应清空
    assert "state.steps = []" not in snippet, (
        "WS 'capture' 帧不应清 state.steps (单条新事件, 无重复风险)"
    )


# ─── server 端 captures 累计行为 (验证 dedup 移除后 server 不背锅) ───


def test_server_keeps_all_injected_events_including_duplicates(client):
    """server 端 CaptureReader.append 不去重, 注入 N 行 → list 返回 N 条,
    即使 method+path 完全相同。"""
    sid = "dedup-removed-sid"
    # 清残留
    client.delete(f"/api/captures?sid={sid}")
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    for line in lines:
        ev = json.loads(line)
        r = client.post(f"/api/captures/inject?sid={sid}", json=ev)
        assert r.status_code == 200
    r = client.get(f"/api/captures?sid={sid}")
    assert r.status_code == 200
    events = r.json().get("events", [])
    assert len(events) == len(lines), (
        f"server 端应保留所有 inject 进来的 {len(lines)} 条 event, "
        f"实际 {len(events)} 条 (若有去重, 此处会 < {len(lines)})"
    )
    # 两条 GET / 必须都在
    get_root = [e for e in events if e.get("method") == "GET" and e.get("path") == "/"]
    assert len(get_root) == 2, (
        f"server 端应保留 2 条 GET /, 实际 {len(get_root)} 条"
    )