"""v0.5.x 修复: ws_captures handler 必须吞掉 uvicorn 二次 SIGINT 派生的 CancelledError。

Bug: 当 uvicorn 收到第二次 Ctrl+C (force quit) 时, 会向运行中的 task 派发
`asyncio.CancelledError`。`ws_captures` 在 `await queue.get()` 处被取消,
由于 Python 3.8+ 起 `asyncio.CancelledError` 不再是 `Exception` 的子类,
现有的 `except Exception` 抓不到, 导致 traceback 冒到顶层
(`File "...\routes.py", line 204, in ws_captures` 的 `await queue.get()`)。

期望: WS handler 必须静默吞 CancelledError, 走 finally 清理 handle.stop()。
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

ROUTES = Path("D:/M/ModelRegistry/gimbal/prism/server/routes.py")


def _read() -> str:
    return ROUTES.read_text(encoding="utf-8")


def _extract_ws_captures_body(text: str) -> str:
    """提取 @router.websocket('/ws/captures') 装饰的 ws_captures 函数体。"""
    m = re.search(
        r"@router\.websocket\(['\"]/ws/captures['\"]\)\s*\n\s*async def ws_captures\([^)]*\)[^:]*:\s*\n(.*?)(?=\n@router|\nclass |\n# ───|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "未找到 ws_captures 函数体"
    return m.group(1)


# ─── 核心 bug: CancelledError 必须被显式吞掉 ─────────────────────────────


def test_ws_captures_catches_cancelled_error():
    """#1 — handler 必须显式 except asyncio.CancelledError, 二次 SIGINT 静默退出。
    Python 3.8+ 起 CancelledError 是 BaseException, 现有 `except Exception` 抓不到。"""
    body = _extract_ws_captures_body(_read())
    assert "asyncio.CancelledError" in body, (
        "ws_captures handler 未捕获 asyncio.CancelledError, "
        "uvicorn 二次 Ctrl+C 会在 await queue.get() 抛 CancelledError "
        "并沿 stack 上溯成 'Exception in ASGI application' traceback"
    )


def test_ws_captures_finally_still_runs():
    """#2 — handler 仍要 finally 调 handle.stop(), 取消路径上不能漏 watcher 清理。"""
    body = _extract_ws_captures_body(_read())
    # 抓 finally 块的内容
    m = re.search(r"finally:\s*\n\s*(\S+)", body)
    assert m, "ws_captures 缺少 finally 块"
    assert "handle.stop" in m.group(1), (
        "ws_captures finally 块未调 handle.stop(), "
        "正常退出和 CancelledError 路径都会泄漏 watcher handle"
    )


def test_ws_captures_unchanged_websocket_disconnect_handling():
    """#3 — 回归: 客户端正常断开 (WebSocketDisconnect) 仍走静默 path。"""
    body = _extract_ws_captures_body(_read())
    assert "WebSocketDisconnect" in body, "WebSocketDisconnect 异常处理丢失"


# ─── 端到端: 模拟 cancel, 验证 handler 静默退出 ─────────────────────────


def test_ws_captures_silently_handles_task_cancellation():
    """#4 — E2E: 取消 task 后, 协程必须安静完成, 不冒 CancelledError。

    uvicorn 在 `await t` 时会检查 task 是否抛了 CancelledError, 若抛了会刷
    "Exception in ASGI application" 错误日志。我们的修复必须用 `pass` 而非
    `raise` 吞掉 CancelledError, 否则 traceback 仍会冒到顶层。
    """
    async def _good_silent():
        """修复后期望: except CancelledError 后静默 (pass/return)。"""
        try:
            await asyncio.Queue().get()
        except asyncio.CancelledError:
            return  # 或 pass — 都让 task 正常结束

    async def _bad_re_raise():
        """bug 行为: except CancelledError 后 raise — task 仍以 CancelledError 结束。"""
        try:
            await asyncio.Queue().get()
        except asyncio.CancelledError:
            raise

    async def _run(handler):
        t = asyncio.create_task(handler())
        await asyncio.sleep(0)
        t.cancel()
        try:
            await t
            return "silent"
        except asyncio.CancelledError:
            return "raised"
        except BaseException:
            return "raised"

    # 文档化: 静默模式不抛 (修复后期望)
    assert asyncio.run(_run(_good_silent)) == "silent"
    # 反证: raise 模式会冒 CancelledError (uvicorn 看到就会刷日志)
    assert asyncio.run(_run(_bad_re_raise)) == "raised"

    # 静态锁住: 修复后的 ws_captures 函数体里, `except asyncio.CancelledError`
    # 后面必须是 `pass` (而不是 `raise`)。要跳过 except 块内的注释行, 找到第一个
    # 非注释、非空行的 token。
    body = _extract_ws_captures_body(_read())
    m = re.search(
        r"except\s+asyncio\.CancelledError\s*:\s*\n(.*?)(?=\n\s*(?:except|finally|\Z))",
        body,
        re.DOTALL,
    )
    assert m, (
        "ws_captures 没有 `except asyncio.CancelledError: <body>` 块, "
        "uvicorn 二次 Ctrl+C 会在 await queue.get() 抛 CancelledError "
        "并沿 stack 上溯成 'Exception in ASGI application' traceback"
    )
    block_body = m.group(1)
    # 去掉注释行和空行, 找到实际的第一条语句 token
    code_lines = [
        line.strip() for line in block_body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    first_token = code_lines[0].split()[0] if code_lines else ""
    assert first_token != "raise", (
        f"ws_captures 的 `except asyncio.CancelledError` 块第一行是 'raise', "
        f"仍会冒 CancelledError 到 uvicorn 触发 'Exception in ASGI application' 日志; "
        f"应改为 'pass' (或 'return' 等) 让 task 静默结束。实际第一行: {code_lines[0]!r}"
    )
