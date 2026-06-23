"""gimbal.capture.proxy — mitmproxy addon。

由 `gimbal capture start` 通过 mitmdump -s 加载,不直接运行。
只做两件事: 按 CompiledMatcher 过滤、把请求/响应原样写入 NDJSON。
不做任何清洗或转换 —— 捕获层只记录事实。

v0.4 变更 (Capture Filter Strategy):
  - CaptureAddon 接受 CompiledMatcher 替代 PathFilter
  - PathFilter 兼容层保留 (旧命令 / 测试 / 文档示例)
"""
from __future__ import annotations

import sys
import time

from mitmproxy import ctx, http

from .bus import FileBus
from .recorder import CaptureEvent
from .strategy import CompiledMatcher


class CaptureAddon:
    """mitmproxy addon: 按 CompiledMatcher 过滤,落 FileBus。"""

    def __init__(self, bus: FileBus, matcher: CompiledMatcher) -> None:
        self.bus = bus
        self.matcher = matcher
        self.count = 0

    def load(self, loader):  # noqa: ANN001 - mitmproxy 协议
        loader.add_option(
            "capture_filter", str, "/api/",
            "path 前缀过滤,逗号分隔,如 /api/order,/api/user (v0 兼容, 新用法走 YAML)",
        )
        loader.add_option(
            "capture_session", str, "default",
            "session id(传给 addon,落地文件名)",
        )
        loader.add_option(
            "capture_home", str, str(self.bus.home),
            "GIMBAL_HOME 路径",
        )

    def _build_event_dict(self, flow: http.HTTPFlow, path: str) -> dict:
        """构造 CompiledMatcher.match 需要的 event dict。

        字段: method, host, path (与 design §2.3 / §3.2 描述一致)
        """
        return {
            "method": flow.request.method,
            "host": flow.request.host,
            "path": path,
        }

    def response(self, flow: http.HTTPFlow):  # noqa: ANN001
        if flow.response is None:
            return  # 失败请求不录

        path = flow.request.path.split("?")[0]
        event = self._build_event_dict(flow, path)
        if not self.matcher.match(event):
            return

        # body 可能非文本 (binary),回退到空串
        try:
            req_body = flow.request.get_text()
        except Exception:  # noqa: BLE001
            req_body = ""
        try:
            resp_body = flow.response.get_text()
        except Exception:  # noqa: BLE001
            resp_body = ""

        capture_event = CaptureEvent(
            ts=time.time(),
            method=flow.request.method,
            scheme=flow.request.scheme,
            host=flow.request.host,
            port=flow.request.port,
            path=path,
            query=dict(flow.request.query),
            headers=dict(flow.request.headers),
            body=req_body,
            response_status=flow.response.status_code,
            response_headers=dict(flow.response.headers),
            response_body=resp_body,
        )
        self.bus.write(capture_event)
        self.count += 1
        print(
            f"[capture] #{self.count} {capture_event.method} {capture_event.path}",
            file=sys.stderr,
            flush=True,
        )

    def done(self):  # noqa: ANN001 - mitmproxy 协议
        """mitmproxy 关闭时调用。"""
        self.bus.close()
