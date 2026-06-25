# gimbal 用户文档

> 把 HTTP 流量（NDJSON）一键转换为 GIMBAL 可运行的 Scenario YAML。
> 支持两种配置方式：Web UI 和 CLI。

## 文档导航

### 📘 新手必读

- **[overview.md](./overview.md)** — gimbal 是什么、整体架构、端到端 5 步工作流、决策树
  - 第一次跑通先看这个

### 🔧 抓包子系统

- **[capture.md](./capture.md)** — `gimbal capture` 完整用法
  - `start` / `list` / `show` / `archive` 4 个子命令
  - YAML 筛选策略（v0.4+）完整说明
  - NDJSON 字节级格式

### 🌐 Web 配置器

- **[prism.md](./prism.md)** — `gimbal prism start` 4-Tab UI
  - 实时事件流 (SSE / WebSocket)
  - HTTP API 完整参考
  - 拖拽 / 调断言 / 写 extracts

### ⌨️ CLI 配置器

- **[prism-cli.md](./prism-cli.md)** — `gimbal prism` 10 个子命令
  - 5 个 pipeline: `convert` / `inspect` / `validate` / `to-steps` / `explain`
  - 4 组 edit: `meta` / `user` / `resource` / `config`
  - Web vs CLI 选型矩阵

## 一页纸 cheat sheet

```bash
# 抓包
gimbal capture start -s SID [--filter-file FILE] [--filter-profile PROF]
gimbal capture list / show SID / archive SID

# 转换
gimbal prism convert -i NDJSON [-c CONFIG] [-o OUTPUT]

# 校验 + 摘要
gimbal prism validate -c CONFIG
gimbal prism explain SCENARIO [--json]

# 增量编辑
gimbal prism meta {get|set} SCENARIO [--name N] [--priority P]
gimbal prism user {list|add|remove} SCENARIO --key K
gimbal prism resource {list|add|remove} SCENARIO --name N
gimbal prism config {get|set} SCENARIO [--time-policy-kind K] [--retry-enabled]

# Web UI
gimbal prism start [--port 8765] [--reload]
```

## 30 秒上手

```bash
# 1. 抓包
gimbal capture start -s hello
# 浏览器代理: 127.0.0.1:8080
# 业务操作... Ctrl+C

# 2. 转 scenario
gimbal prism convert -i ~/.gimbal/captures/archive/*/hello-*.ndjson -o /tmp/hello.yaml

# 3. 看结果
gimbal prism explain /tmp/hello.yaml
```

完整教程见 [overview.md](./overview.md)。
