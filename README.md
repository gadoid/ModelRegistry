# gimbal

> 测试用例配置平台 v0.1.0

`gimbal` 把"浏览器真实流量"转成"可复用的 GIMBAL Scenario":

```
浏览器 ──→ capture 代理 (:8080) ──→ NDJSON 落盘
                                        │
                                        │ (文件系统契约)
                                        ▼
                              prism 配置器 (:8765)
                                        │
                                        │ 编辑/校验/导出
                                        ▼
                                scenarios/{sid}.yaml
```

两个独立进程,**无反向依赖**,**无进程间 API**,文件是唯一契约。

## 安装

```bash
# 标准安装
pip install -e .

# 启用 ModelRegistry 集成 (可选)
pip install -e ".[model-registry]"
# 或通过环境变量 (无需重装):
export GIMBAL_MODEL_REGISTRY_PATH=/path/to/D:/M/ModelRegistry

# 装上后 import 验证
python -c "from gimbal.contracts import is_available, EndpointSpec; print(is_available())"
```

> 未启用时,`gimbal.contracts` 子包仍可 import,但 `is_available()` 返回 False,
> 相关功能 (registry spec 端点) 返回最小空 spec,其他模块正常工作。

## 快速上手

### 1. 启动捕获代理

```bash
# 终端 1: 启动 capture (简单 CSV 模式, v0 行为)
gimbal capture start --session dev-1 --port 8080
# [capture] session=dev-1  port=8080  filter=/api/
# [capture] out=C:\Users\me\.gimbal\captures\active\dev-1.ndjson
# 浏览器代理指向 127.0.0.1:8080, 信任 mitmproxy CA (http://mitm.it)

# v0.4 新增: YAML 筛选策略 (profile + include 复用)
gimbal capture start --session dev-1 \
  --filter-file filters.yaml \
  --filter-profile smoke
```

启动后浏览器走代理,HTTPS 请求会进入 `$GIMBAL_HOME/captures/active/dev-1.ndjson`。
按 Ctrl+C 停止,自动归档到 `archive/{date}/dev-1-{ts}.ndjson`。

### 2. 启动配置器

```bash
# 终端 2: 启动 prism
gimbal prism start --port 8765
# [prism] GIMBAL_HOME=C:\Users\me\.gimbal
# [prism] starting on http://127.0.0.1:8765
```

浏览器打开 <http://127.0.0.1:8765>:
- **① 捕获** 标签: 看到 capture 列表,SSE 实时推送新增
- **② 元信息/配置** 标签: schema 驱动的声明式表单 (从 `/api/schema/ui-spec` 派生)
- **③ 资源** 标签: 资源 mock/file 配置
- **④ Steps** 标签: 步骤编辑

### 3. 切换 session / 列出 / 归档

```bash
# 列出 active 下的 session
gimbal capture list

# 查看某 session 最近 50 条
gimbal capture show dev-1 --limit 50

# 手动归档 (从 active 移到 archive)
gimbal capture archive dev-1
```

## 子命令

| 命令 | 作用 |
|---|---|
| `gimbal capture start` | 启动 mitmproxy 抓包 |
| `gimbal capture list` | 列出 active 下的 session |
| `gimbal capture show <sid>` | 查看某 session 的事件 |
| `gimbal capture archive <sid>` | 手动归档 |
| `gimbal prism start` | 启动 web 配置器 (默认 :8765) |
| `gimbal prism convert` | NDJSON (+ config) → Scenario YAML |
| `gimbal prism inspect` | NDJSON 统计 + 前 N 条样本 |
| `gimbal prism validate` | config YAML 校验 |
| `gimbal prism to-steps` | NDJSON → step 片段 JSON |
| `gimbal prism explain <sc>` | scenario YAML 结构摘要 |
| `gimbal prism meta get/set` | 读 / 改 scenario meta 字段 |
| `gimbal prism user list/add/remove` | 读 / 改 scenario users |
| `gimbal prism resource list/add/remove` | 读 / 改 scenario resources |
| `gimbal prism config get/set` | 读 / 改 scenario config sections |

## v0.4 状态 (Capture Filter Strategy)

- ✅ `gimbal/capture/strategy.py` — Pydantic `Rule` / `Profile` / `StrategyFile` + `CompiledMatcher`
- ✅ `gimbal/capture/loader.py` — YAML 解析 + include 递归 + profile 选择 + CLI 追加
- ✅ `gimbal/capture/proxy.py` — `CaptureAddon` 接受 `CompiledMatcher`
- ✅ `gimbal/capture/cli.py` — 新增 `--filter-file` / `--filter-profile` / `--filter-mode` / `--strict-files-only`
- ✅ `gimbal/capture/filter.py` — `PathFilter` 兼容层保留 (旧 CSV 行为不变)
- ✅ 81 个新单测, 165 passed / 4 skipped

详见 [`docs/superpowers/specs/2026-06-21-capture-filter-strategy-design.md`](docs/superpowers/specs/2026-06-21-capture-filter-strategy-design.md)。

## v0.3 状态

- ✅ 旧 `prism/` 顶层包已删 (84 测试全过, 4 skipped)
- ✅ 4-Tab 声明式渲染 (基于 `/api/schema/ui-spec`)
- ✅ 30+ 字段带 UI 注解 (meta / config / timePolicy / retry / users / resource)
- ✅ ModelRegistry 双路径加载 (env var / 已装) + 字段漂移保护
- ✅ `gimbal capture/prism` 进程级独立, 无反向依赖, 无进程间 API
- ✅ FileBus 文件锁 (POSIX fcntl / Windows msvcrt) + 归档策略

## v0.2 / v0.3 历史变更

详见 [CHANGELOG.md](CHANGELOG.md)。v0.1 起的所有痛点修复 (5/6/7/8/9/10/11/12/13/14) 都已落地。

## 端点

`gimbal prism` 暴露的 HTTP 端点 (默认 :8765):

| 路径 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 配置器 HTML |
| `/configure?session=<sid>` | GET | 带 session 注入的 HTML |
| `/api/health` | GET | 健康检查 + 计数 |
| `/api/captures?sid=<sid>` | GET | 列出某 session 的 capture |
| `/api/captures?sid=<sid>` | DELETE | 清空 (truncate) |
| `/api/captures/inject?sid=<sid>` | POST | 单 event 追加 |
| `/api/captures/import-from-path` | POST | 从 NDJSON 路径导入 (沙箱限制 CWD 内) |
| `/api/captures/stream?sid=<sid>` | GET | **SSE** 实时推送 capture 增量 |
| `/api/draft/{sid}` | GET / PUT | 草稿读写 |
| `/api/draft/{sid}/export` | POST | 写 Scenario YAML 到 `$GIMBAL_HOME/scenarios/{sid}.yaml` |
| `/api/draft/{sid}/yaml` | POST | 只读 YAML 预览 (422 on invalid) |
| **`/api/schema/ui-spec`** | GET | **schema → 前端 JSON** (SSOT) |
| **`/api/schema/dot-paths`** | GET | **合法 dot-path 白名单** |
| **`/api/registry/ui-spec`** | GET | **ModelRegistry → UI spec** |

## 数据目录 (`$GIMBAL_HOME`)

默认 `~/.gimbal/`,可通过 `GIMBAL_HOME` 环境变量或 `--home` 覆盖:

```
$GIMBAL_HOME/
├── captures/
│   ├── active/
│   │   └── {session_id}.ndjson    # capture 正在写入 (排他文件锁)
│   └── archive/
│       └── 2026-06-18/
│           └── {sid}-{epoch}.ndjson
├── scenarios/
│   └── {scenario_id}.yaml         # prism 导出
└── config.yaml                     # v0 暂未实现
```

## 设计文档

详细设计见 [`gimbal-design/`](gimbal-design/) (7 份文档):
- `01-architecture.md` — 总体架构 + 两个模块拆分
- `02-capture-module.md` — capture 详细设计
- `03-prism-module.md` — prism 配置器设计
- `04-schema-ssot.md` — schema SSOT 与 UI 注解体系
- `05-model-registry-integration.md` — ModelRegistry 引入
- `06-migration-plan.md` — M1-M4 迁移计划
- `07-filter-strategy.md` — v0.4 Capture Filter Strategy 实施归档

## 开发

```bash
# 在 .venv (隔离虚拟环境) 中
D:/M/ModelRegistry/.venv/Scripts/python.exe -m pip install -e . --no-deps

# 跑测试
D:/M/ModelRegistry/.venv/Scripts/python.exe -m pytest tests/

# 静态分析
D:/M/ModelRegistry/.venv/Scripts/python.exe -m ruff check gimbal/
```

## v0 不做的事

- ❌ `gimbal run` 执行引擎 (后续看用户需求)
- ❌ AI 助手 (`gimbal/prism/ai/` 已删, `anthropic` / `httpx` 未引入)
- ❌ 大规模 E2E 测试补全 (只补核心路径)
- ❌ 多 worker uvicorn (`--workers 1` 强制, sessions 是进程内状态)
- ❌ config.yaml 完整实现 (v0 全部走 CLI 参数)
