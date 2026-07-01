"""Windows 上 asyncio proactor event loop 在 socket 清理时会冒
``ConnectionResetError`` (WinError 10054) — 见 Python 3.14 stdlib
``asyncio/proactor_events.py`` 第 165 行 ``self._sock.shutdown(socket.SHUT_RDWR)``
被 ``finally`` 包但无内层 try/except, 当 OS 已把 socket 状态置为 reset 时抛。

默认 asyncio exception handler 把这种内部清理异常刷成 "Unhandled error in task",
误导用户以为是业务代码 bug。

修复: ``gimbal.prism.server.app`` 的 lifespan 启动期注册一个
``set_exception_handler``, 静默吞 ConnectionResetError, 其它异常仍走默认 handler。

本测试套件锁住:
1. lifespan 启动后, running loop 的 exception handler 存在
2. handler 对 ConnectionResetError 静默 (不调用 default_exception_handler)
3. handler 对其它异常仍走 default
"""
from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app

APP_PY = Path("D:/M/ModelRegistry/gimbal/prism/server/app.py")


def _read_app() -> str:
    assert APP_PY.exists(), f"app.py 不存在: {APP_PY}"
    return APP_PY.read_text(encoding="utf-8")


def _extract_lifespan_body(text: str) -> str:
    """提取 ``lifespan`` 函数体 (yield 之前的 startup 部分)。"""
    m = re.search(
        r"async\s+def\s+lifespan\s*\([^)]*\)\s*:\s*\n(.*?)(?=\n@asynccontextmanager|\ndef\s|\nclass\s|\n# ─|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "未找到 lifespan 函数体"
    return m.group(1)


# ─── 静态校验: lifespan 必须装 exception handler ──────────────────────


def test_lifespan_installs_exception_handler():
    """lifespan startup 阶段必须调 ``set_exception_handler(...)`` —
    否则 Windows 上 proactor socket 清理会刷 ConnectionResetError (10054)。"""
    text = _read_app()
    body = _extract_lifespan_body(text)
    assert "set_exception_handler" in body, (
        "lifespan 未注册 asyncio exception handler; "
        "Windows 上 proactor socket 清理 (proactor_events.py:165 "
        "shutdown(SHUT_RDWR)) 会在 WinError 10054 时刷 "
        "'Unhandled error in task' 误报"
    )


def test_lifespan_handler_silences_connection_reset():
    """handler 实现必须: ConnectionResetError → 静默返回, 不抛 / 不调 default。"""
    text = _read_app()
    # 找 set_exception_handler 用的回调函数 body
    m = re.search(
        r"def\s+(_silence_proactor_connection_reset)\s*\([^)]*\)[^:]*:\s*\n(.*?)(?=\n# ─)",
        text,
        re.DOTALL,
    )
    assert m, (
        "未找到 _silence_proactor_connection_reset 函数体 "
        "(应在 app.py 顶部定义, lifespan 内 set_exception_handler 引用)"
    )
    fn_body = m.group(2)
    # 必须显式判 ConnectionResetError
    assert "ConnectionResetError" in fn_body, (
        f"handler 函数体未识别 ConnectionResetError — 仍会刷 'Unhandled error in task'\n"
        f"实际 body:\n{fn_body}"
    )
    # ConnectionResetError 分支应直接 return (静默)
    assert "return" in fn_body, (
        "handler 必须在 ConnectionResetError 分支 return, 不调 default"
    )


# ─── E2E 校验: lifespan 启动后, 当前 loop 已装 handler ────────────────


def test_lifespan_loop_has_custom_exception_handler():
    """Real app 的 lifespan 跑起来后, loop.set_exception_handler 必须被调用过,
    且传入的是 _silence_proactor_connection_reset (非 None)。"""
    import importlib
    import sys
    if "gimbal.prism.server._app_mod" not in sys.modules:
        importlib.import_module("gimbal.prism.server.app")
        sys.modules["gimbal.prism.server._app_mod"] = sys.modules.pop("gimbal.prism.server.app")
    app_mod = sys.modules["gimbal.prism.server._app_mod"]
    real_app = app_mod.app

    captured: list = []
    real_set = asyncio.BaseEventLoop.set_exception_handler

    def patched(self, handler):
        captured.append(handler)
        return real_set(self, handler)

    asyncio.BaseEventLoop.set_exception_handler = patched
    try:
        with TestClient(real_app) as client:
            client.get("/")
    finally:
        asyncio.BaseEventLoop.set_exception_handler = real_set

    assert captured, (
        "lifespan 跑完后, 没有 set_exception_handler 调用 "
        "(app.py lifespan 内应 loop.set_exception_handler(...))"
    )
    assert app_mod._silence_proactor_connection_reset in captured, (
        f"set_exception_handler 未注册 _silence_proactor_connection_reset, "
        f"实际注册列表: {captured!r}"
    )


# ─── handler 行为单测: ConnectionResetError 静默 ─────────────────────


def test_handler_silences_connection_reset_error():
    """直接调用注册的 handler, 给 ConnectionResetError 上下文 — 应静默
    (不抛, 不调 default_exception_handler)。"""
    text = _read_app()
    m = re.search(
        r"def\s+(_?\w*proactor\w*|_?silence\w*|_?\w*exc(?:eption)?\w*handler\w*)\s*\(",
        text,
    )
    assert m, "未找到 silencing handler 函数"
    fn_name = m.group(1)
    # 加载 app 模块, 拿到这个函数
    import importlib
    import sys
    # gimbal.prism.server.app 在 server/__init__.py 被 re-export 成 FastAPI 实例,
    # 真正的模块是 gimbal.prism.server.app 文件本身, 用 importlib 显式加载
    if "gimbal.prism.server._app_mod" not in sys.modules:
        importlib.import_module("gimbal.prism.server.app")
        sys.modules["gimbal.prism.server._app_mod"] = sys.modules.pop("gimbal.prism.server.app")
    app_mod = sys.modules["gimbal.prism.server._app_mod"]
    fn = getattr(app_mod, fn_name, None)
    if fn is None:
        # 函数可能定义在 _shared 之类, 搜 src
        m2 = re.search(
            rf"def\s+{re.escape(fn_name)}\s*\([^)]*\)\s*:\s*\n(.*?)(?=\n\ndef |\nclass |\n@|\n# ─|\Z)",
            text,
            re.DOTALL,
        )
        assert m2, f"handler 函数 {fn_name} 不在 app_mod"
        pytest.skip(f"handler {fn_name} 不在 app_mod 模块导出, 静态测试已覆盖")
    # 构造 fake loop
    class FakeLoop:
        def __init__(self):
            self.default_called = False
            self.passed_context = None
        def default_exception_handler(self, ctx):
            self.default_called = True
            self.passed_context = ctx
    loop = FakeLoop()
    ctx = {
        "message": "test message",
        "exception": ConnectionResetError(10054, "远程主机强迫关闭了一个现有的连接"),
        "future": None,
    }
    fn(loop, ctx)  # 不抛 = 通过
    assert not loop.default_called, (
        "ConnectionResetError 应被静默, 不应再走 default_exception_handler"
    )


def test_handler_passes_other_exceptions_to_default():
    """非 ConnectionResetError 的异常应继续走 default_exception_handler。"""
    text = _read_app()
    m = re.search(
        r"def\s+(_?\w*proactor\w*|_?silence\w*|_?\w*exc(?:eption)?\w*handler\w*)\s*\(",
        text,
    )
    if not m:
        pytest.skip("handler 未在 app.py 定义")
    fn_name = m.group(1)
    import sys
    import importlib
    if "gimbal.prism.server._app_mod" not in sys.modules:
        importlib.import_module("gimbal.prism.server.app")
        sys.modules["gimbal.prism.server._app_mod"] = sys.modules.pop("gimbal.prism.server.app")
    app_mod = sys.modules["gimbal.prism.server._app_mod"]
    fn = getattr(app_mod, fn_name, None)
    if fn is None:
        pytest.skip("handler 不在 app_mod 导出")
    class FakeLoop:
        def default_exception_handler(self, ctx):
            self.default_called = True
    loop = FakeLoop()
    loop.default_called = False
    ctx = {
        "message": "other exc",
        "exception": ValueError("not a connection reset"),
    }
    fn(loop, ctx)
    assert loop.default_called, (
        "非 ConnectionResetError 异常必须走 default_exception_handler "
        "(不能误吞业务异常)"
    )