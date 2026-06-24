"""Runtime e2e 测试: 实际在 jsdom 里跑 app.js, 验证 state 和 DOM 真的更新。

覆盖所有静态测试抓不到的运行时问题:
- 脚本顶层是否抛错 (例如 dead code 引用已删除的 DOM ID)
- click 事件是否真的触发 + state 是否真的更新 + DOM 是否真的渲染
- _importNdjsonFile 链路 (inject + pull + merge) 是否真的生成 step

前置: jsdom 在 C:/Users/jiaoshouxiang/AppData/Local/Temp/node_modules/jsdom
      (用 `npm install jsdom` 装到那里)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HARNESS = Path("D:/M/ModelRegistry/tests/jsdom_harness.js")
JS_BIN = "C:/Program Files/nodejs/node.exe" if Path("C:/Program Files/nodejs/node.exe").exists() else "node"


def _run_harness(scenario: str) -> dict:
    """Run the jsdom harness with given scenario, return parsed JSON report."""
    result = subprocess.run(
        [JS_BIN, str(HARNESS), scenario],
        capture_output=True, text=True, timeout=30, cwd="D:/M/ModelRegistry",
    )
    assert result.returncode == 0, f"harness exit {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    return json.loads(result.stdout)


def test_app_js_loads_without_throwing():
    """脚本顶层不应抛错 (line 1102 死代码问题导致所有 static 测试漏过)。"""
    r = _run_harness("initial-load")
    err = r.get("scriptLoadErr")
    assert err is None, (
        f"app.js 顶层 throw:\n  msg: {err['msg']}\n  stack: {err['stack']}\n"
        "通常是 dead code 引用了已删除的 DOM ID"
    )


def test_app_js_state_globally_accessible_after_load():
    """脚本跑完后, state 应在 window 域 (即 const 顶层声明的 state 被 init 用到)。"""
    r = _run_harness("initial-load")
    assert r["hasState"] is True, f"state 没暴露: {r}"


def test_click_add_step_grows_state_and_updates_dom():
    """点击 #add-step 后: state.steps 增长 + DOM 真的更新 (sidebar/tags 出现 page-tab/step-tag)。"""
    r = _run_harness("click-add-step")
    # 脚本本身应能跑通
    assert r.get("scriptLoadErr") is None, f"脚本顶层 throw: {r.get('scriptLoadErr')}"
    # state 必须增长
    assert r["afterSteps"] == r["beforeSteps"] + 1, (
        f"state.steps 没增长: before={r['beforeSteps']} after={r['afterSteps']}"
    )
    # DOM 必须更新 (侧栏有 page-tab, 标签栏有 step-tag)
    assert r["domUpdates"]["sidebarHasTab"] is True, (
        f"step-sidebar 没渲染 page-tab: {r['domUpdates']}"
    )
    assert r["domUpdates"]["tagsHasTag"] is True, (
        f"step-tags 没渲染 step-tag: {r['domUpdates']}"
    )
    # 空状态应被藏起来
    assert r["domUpdates"]["stepEmptyHidden"] is True, (
        f"step-empty 应被隐藏 (因为有 step 了): {r['domUpdates']}"
    )
    assert r["domUpdates"]["stepListHidden"] is False, (
        f"step-list 应被显示 (因为有 step 了): {r['domUpdates']}"
    )


def test_import_ndjson_flow_creates_steps_and_renders_dom():
    """_importNdjsonFile 链路: inject + pull + merge → state.steps 增长 + DOM 更新。"""
    r = _run_harness("import-ndjson")
    assert r.get("scriptLoadErr") is None, f"脚本顶层 throw: {r.get('scriptLoadErr')}"
    # 链路状态: inject 应 200, pull 应 200
    assert r["injectStatus"] == 200, f"inject 失败: status={r['injectStatus']}"
    assert r["pullStatus"] == 200, f"pull 失败: status={r['pullStatus']}"
    # 关键: 合并后 steps 真的多了
    assert r["stepsAfter"] > r["stepsBefore"], (
        f"merge 没把 capture 转成 step: before={r['stepsBefore']} after={r['stepsAfter']}"
    )
    # DOM 也应更新
    assert r["domUpdates"]["sidebarHasTab"] is True, (
        f"sidebar 没渲染: {r['domUpdates']}"
    )
    assert r["domUpdates"]["tagsHasTag"] is True, (
        f"tags 没渲染: {r['domUpdates']}"
    )
