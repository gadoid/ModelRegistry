"""gimbal.capture.recorder — 单次 HTTP 抓包事件数据模型。

字段顺序与 prism/capture.py 历史 NDJSON 输出**字节级兼容**,
response.{status, headers, body} 嵌套结构保留,旧 reader 不需改动。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaptureEvent:
    """单次 HTTP 抓包事件。

    字段以 Pydantic-style 平铺,序列化时 (to_dict) 合并为 {response: {...}}。
    """

    ts: float                                # epoch 秒
    method: str                              # 大写 (GET/POST/...)
    scheme: str                              # http / https
    host: str
    port: int
    path: str                                # 已去 query string
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    response_status: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""

    def to_dict(self) -> dict[str, Any]:
        """输出与 NDJSON 写入格式一致的 dict(嵌套 response.*)。

        CaptureEvent 内部把 response 拆成平铺字段(便于 dataclass),
        序列化时合并为 {response: {status, headers, body}}。
        """
        d: dict[str, Any] = {
            "ts": self.ts,
            "method": self.method,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "query": self.query,
            "headers": self.headers,
            "body": self.body,
            "response": {
                "status": self.response_status,
                "headers": self.response_headers,
                "body": self.response_body,
            },
        }
        return d


def event_from_dict(d: dict[str, Any]) -> CaptureEvent:
    """从 NDJSON 单行 dict 构造 CaptureEvent(给 convert / replay / 测试用)。"""
    resp = d.get("response") or {}
    return CaptureEvent(
        ts=float(d.get("ts", 0.0)),
        method=d.get("method", "GET"),
        scheme=d.get("scheme", "https"),
        host=d.get("host", ""),
        port=int(d.get("port", 0)),
        path=d.get("path", "/"),
        query=d.get("query") or {},
        headers=d.get("headers") or {},
        body=d.get("body") or "",
        response_status=int(resp.get("status", 0)),
        response_headers=resp.get("headers") or {},
        response_body=resp.get("body") or "",
    )
