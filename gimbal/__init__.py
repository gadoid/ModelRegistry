"""gimbal — 测试用例配置平台。

两个独立进程:
  - `gimbal capture`  流量录制器(mitmproxy + NDJSON 落盘)
  - `gimbal prism`    配置器(FastAPI web)

v0 不实现: `gimbal run` 执行器、AI 助手。
"""

__version__ = "0.1.0"
