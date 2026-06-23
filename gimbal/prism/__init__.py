"""gimbal.prism — 配置器(web)。

读取 capture 写入的 NDJSON,提供 4-Tab web UI 让你把捕获
编辑成 GIMBAL Scenario YAML,落到 $GIMBAL_HOME/scenarios/{sid}.yaml。

v0 状态管理走 FastAPI `lifespan` + `app.state`,无模块级单例。
"""
