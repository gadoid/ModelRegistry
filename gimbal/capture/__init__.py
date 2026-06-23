"""gimbal.capture — 流量捕获模块。

只做一件事:把浏览器/客户端通过本地代理发出的 HTTP 请求/响应
原样追加写到 $GIMBAL_HOME/captures/active/{sid}.ndjson。

文件锁保证同 session 只能一个 capture 进程持有。
"""
