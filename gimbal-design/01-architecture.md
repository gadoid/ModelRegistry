# 01 · 总体架构

> 本文档描述 gimbal 平台的总体架构、两个模块的拆分(`capture` 与 `prism`)、顶层 CLI 设计,以及 `$GIMBAL_HOME` 目录结构。
>
> **v0 范围声明**:
> - ✅ 实现: `gimbal capture` + `gimbal prism`(两个独立进程)
> - ❌ 不做: `gimbal run` 执行器、 AI 助手

---

## 1. 架构总览

### 1.1 两个模块的关系

```
                 ┌─────────────────────────────────────┐
                 │            $GIMBAL_HOME             │
                 │  ~/.gimbal/                          │
                 ├─────────────────────────────────────┤
                 │                                      │
   ┌─────────────┼──────────────┐         ┌─────────────┼──────────────┐
   │  captures/  │              │         │ scenarios/  │              │
   │  active/    │  archive/    │         │ {sid}.yaml  │  config.yaml │
   │  {sid}.     │  YYYY-MM-DD/ │         │             │              │
   │  ndjson     │  {sid}-ts.   │         │             │              │
   │             │  ndjson      │         │             │              │
   └──────┬──────┴──────────────┘         └──────▲──────┴──────────────┘
          │                                       │
          │ 写入                                   │ 写入
          │ (only write)                           │ (only write)
          │                                       │
   ┌──────▼───────────────┐              ┌─────────┴────────┐
   │  gimbal capture      │              │  gimbal prism    │
   │  (进程 A)            │              │  (进程 B)        │
   │                      │              │                  │
   │  · mitmproxy addon   │              │  · FastAPI       │
   │  · FileSink          │              │  · 读 NDJSON     │
   │  · 文件锁            │              │  · 写 YAML       │
   │  · Ctrl+C 归档       │              │  · 读 NDJSON     │
   └──────────────────────┘              └──────────────────┘
          │                                       │
          │  端口 :8080 (mitmproxy)               │  端口 :8765 (FastAPI)
          │                                       │
          ▼                                       ▼
   ┌─────────────────────┐              ┌─────────────────────┐
   │  浏览器 HTTP 流量   │              │  浏览器访问 UI      │
   │  代理到 :8080       │              │  http://:8765       │
   └─────────────────────┘              └─────────────────────┘
```

### 1.2 核心不变量

| # | 不变量 | 保证方式 |
|---|---|---|
| 1 | capture 进程**不依赖** prism 进程 | capture 代码不 import gimbal.prism.* |
| 2 | prism 进程**不依赖** capture 进程 | prism 代码不 import gimbal.capture.proxy;只通过 FileBus 读 NDJSON |
| 3 | 进程间**无 API 调用** | 文件系统是唯一介质,无 HTTP / RPC / socket |
| 4 | 两个模块共享**仅 schema / ModelRegistry** | 通过 `pyproject.toml` 的本地可编辑依赖 + 类型注解传递 |
| 5 | **v0 无执行器** | `gimbal run` 子命令**不注册**(甚至不出现于 `--help` 中) |
| 6 | **v0 无 AI 助手** | 不存在 `gimbal/prism/ai/` 目录、不依赖 `anthropic` / `httpx` 等 AI 包 |

---

## 2. v0 范围边界

### 2.1 v0 包含(本设计要实现)

| 模块 | 命令 | 职责 |
|---|---|---|
| `gimbal capture` | `capture start` / `list` / `show` / `archive` | mitmproxy 代理 + NDJSON 落盘 + 归档 |
| `gimbal prism` | `prism start` | FastAPI web 配置器,基于 schema + ModelRegistry 渲染 UI |

### 2.2 v0 不包含(本设计**明确不做**)

| 不做 | 原因 | 是否在文档中提及 |
|---|---|---|
| `gimbal run` 子命令 | 用户明确"后续再看",v0 只做配置 | 仅在 §1.2 不变量 #5 与本节说明 |
| AI 助手(`gimbal/prism/ai/`) | 用户明确"先不考虑 AI" | 仅在 §1.2 不变量 #6 与本节说明 |
| `anthropic` / `httpx` 等 AI 相关依赖 | AI 暂不实现,无依赖 | pyproject.toml 不引入 |
| `ai/config.json` / `ai/history/` 目录 | 同上 | `$GIMBAL_HOME` 不创建 |
| scenarios `.lastrun.json` | `gimbal run` 不实现,无 lastrun | `$GIMBAL_HOME` 不创建 |
| 多 worker uvicorn | sessions 是进程内状态 | `--workers 1` 强制 |

### 2.3 仓库中**不存在的文件**清单

下列文件在本设计中**不应被创建**,任何 PR 引入这些文件都应被驳回:

```
gimbal/prism/ai/                    # 整个 AI 子包
gimbal/prism/ai/__init__.py
gimbal/prism/ai/assistant.py
gimbal/prism/ai/tools.py
gimbal/prism/ai/prompts.py
gimbal/prism/ai/config.py
gimbal/prism/ai/errors.py
gimbal/prism/ai/streaming.py
gimbal/prism/ai/providers/
gimbal/prism/ai/providers/anthropic.py
gimbal/cli/run.py                   # gimbal run 入口
gimbal/executor/                    # 整个执行器
gimbal/prism/static/chat.js         # AI 聊天视图(随 AI 一起删)
gimbal/prism/static/ai-settings.js  # AI 设置(随 AI 一起删)
```

---

## 3. 目录结构(v0)

### 3.1 仓库目录(d:/mirror)

```
d:/mirror/
├── gimbal/                          # ★ 新增:gimbal 平台包(本次改造主战场)
│   ├── __init__.py                  # 版本号、顶层异常
│   ├── cli/                         # 顶层 CLI 实现
│   │   ├── __init__.py
│   │   ├── app.py                   # 根 typer app
│   │   ├── capture.py               # `gimbal capture` 子命令组
│   │   └── prism.py                 # `gimbal prism` 子命令组
│   ├── capture/                     # capture 模块
│   │   ├── __init__.py
│   │   ├── proxy.py                 # mitmproxy addon(原 prism/capture.py)
│   │   ├── recorder.py              # CaptureEvent dataclass(原 prism/recorder.py 主体)
│   │   ├── bus.py                   # FileBus(NDJSON 文件实现)
│   │   ├── archive.py               # active/*.ndjson → archive/{date}/*.ndjson
│   │   └── filter.py                # path 前缀过滤 + host 匹配
│   ├── prism/                       # prism 配置器
│   │   ├── __init__.py
│   │   ├── server.py                # FastAPI 后端(原 prism/server.py)
│   │   ├── builder.py               # draft → Scenario(原 prism/builder.py)
│   │   ├── convert.py               # NDJSON → step 片段(原 prism/convert.py)
│   │   ├── doc2model.py             # 样本 → Pydantic(原 prism/doc2model.py)
│   │   ├── state.py                 # session/draft/history 状态管理

│   │   ├── render/                  # schema + ModelRegistry → UI spec
│   │   │   ├── __init__.py
│   │   │   ├── ui_spec.py           # 序列化 Pydantic 模型为前端可消费 JSON
│   │   │   ├── walk_model.py        # 遍历 Pydantic 模型生成 dot-path 列表
│   │   │   └── registry_spec.py     # ★ 新增:ModelRegistry → UI spec(下拉选项等)
│   │   └── static/                  # 前端(基于 D:/M/ModelRegistry 样式)
│   │       ├── index.html
│   │       ├── app.js
│   │       └── style.css
│   ├── schema/                      # Pydantic 静态描述层(原 schema/)
│   │   ├── __init__.py
│   │   ├── states.py
│   │   ├── ref.py
│   │   ├── resource.py
│   │   ├── api.py
│   │   ├── request.py
│   │   ├── step.py                  # 本次加 key 字段
│   │   ├── strategy.py
│   │   ├── timepolicy.py
│   │   ├── retrypolicy.py
│   │   ├── scenario.py              # 本次加 Meta.name blank 校验
│   │   ├── setup.py
│   │   ├── teardown.py
│   │   └── auth.py
│   └── contracts/                   # ModelRegistry 引入(原 ModelRegistry/)
│       ├── __init__.py
│       ├── _aliases.py
│       ├── core.py
│       └── spec.py
│
├── pyproject.toml                   # ★ 新增:打包元数据 + console_scripts
├── README.md                        # 顶层 README(重写)
│
├── tests/                           # 测试(原 tests/)
│   ├── test_schema_*.py             # 新增:schema 冒烟
│   ├── test_builder.py              # 新增:builder 单元
│   ├── test_capture_bus.py          # 新增:FileBus 单元
│   ├── test_capture_archive.py      # 新增:归档策略
│   ├── test_prism_lifespan.py       # 新增:lifespan 改造回归
│   └── test_prism_render.py         # 新增:schema + ModelRegistry → UI spec
│
├── docs/                            # 保留现有 docs
│
├── captures.ndjson                  # 数据(保留)
├── codfish1.ndjson                  # 数据(保留)
├── e2e_gimbal.json                  # 数据(保留)
│
└── gimbal-design/                   # 本设计文档目录
    ├── README.md
    ├── 01-architecture.md           # 本文件
    ├── 02-capture-module.md
    ├── 03-prism-module.md
    ├── 04-schema-ssot.md
    ├── 05-model-registry-integration.md
    └── 06-migration-plan.md
```

### 3.2 运行时目录(`$GIMBAL_HOME`)

```
$HOME/.gimbal/                       # 由环境变量 GIMBAL_HOME 覆盖,默认 ~/.gimbal
├── captures/
│   ├── active/
│   │   ├── {session_id_1}.ndjson    # capture 正在写入
│   │   ├── {session_id_2}.ndjson
│   │   └── ...
│   └── archive/
│       ├── 2026-06-17/
│       │   ├── {sid}-1700000000.ndjson
│       │   └── ...
│       └── 2026-06-18/
│           └── ...
├── scenarios/
│   ├── {scenario_id_1}.yaml
│   └── ...
└── config.yaml                      # 平台全局配置(端口、默认 session 等)
```

**关键约定**:
- `$GIMBAL_HOME` 由 `gimbal/config.py` 解析,优先级:`GIMBAL_HOME` 环境变量 > `--home` CLI 参数 > `~/.gimbal` 默认
- `captures/active/*.ndjson` 是 capture 进程的写入面,prism 进程的读取面
- `scenarios/*.yaml` 是 prism 进程的写入面(未来 `gimbal run` 进程的读取面,v0 不存在)
- v0 **不创建** `ai/` 目录,**不创建** `*.lastrun.json`
- `config.yaml` 字段见 §7

---

## 4. 文件系统契约

### 3.1 写入契约(capture 进程)

```python
# gimbal/capture/bus.py
class FileBus:
    """capture 进程对外契约:把 CaptureEvent 追加写入 $GIMBAL_HOME/captures/active/{sid}.ndjson"""

    def __init__(self, home: Path, session_id: str) -> None:
        self.path = home / "captures" / "active" / f"{session_id}.ndjson"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp: IO[str] | None = None
        self._lock_acquired = False

    def write(self, event: CaptureEvent) -> None:
        """单次写入:行缓冲 + 排他文件锁。"""
        if self._fp is None:
            self._open_with_lock()
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        self._fp.write(line)

    def close(self) -> None:
        if self._fp:
            self._fp.flush()
            self._fp.close()
            self._fp = None
        self._lock_acquired = False

    def _open_with_lock(self) -> None:
        # POSIX: fcntl.flock;Windows: msvcrt.locking
        # 排他锁 + 非阻塞,失败抛 RuntimeError("session 已被占用")
        ...
```

**字段契约**(每行 NDJSON):

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ts` | `float` | ✅ | epoch 秒,`time.time()` |
| `method` | `str` | ✅ | HTTP method 大写 |
| `scheme` | `str` | ✅ | `http` / `https` |
| `host` | `str` | ✅ | 域名或 IP |
| `port` | `int` | ✅ | 端口 |
| `path` | `str` | ✅ | 已去 query string |
| `query` | `dict[str, str]` | ✅ | query 参数 |
| `headers` | `dict[str, str]` | ✅ | 请求头 |
| `body` | `str` | ✅ | 请求体原文(空字符串表示无 body) |
| `response.status` | `int` | ✅ | 响应状态码 |
| `response.headers` | `dict[str, str]` | ✅ | 响应头 |
| `response.body` | `str` | ✅ | 响应体原文 |

**写入规则**:
- append-only,任何修改/重写视为破坏契约
- 文件不存在则自动创建,父目录自动 `mkdir -p`
- 同一 session 同一时刻只允许一个 capture 进程持有排他锁
- 写入失败 → 进程退出 + 日志告警,**不静默吞错**

### 3.2 读取契约(prism 进程)

```python
# gimbal/prism/state.py(节选)
class CaptureReader:
    """prism 进程对 capture 数据的只读视图。"""

    def __init__(self, home: Path) -> None:
        self.home = home

    def list_active(self) -> list[str]:
        """返回 active/ 下所有 session_id 列表。"""
        active = self.home / "captures" / "active"
        if not active.exists():
            return []
        return sorted(p.stem for p in active.glob("*.ndjson"))

    def read(self, session_id: str, tail: bool = False) -> Iterator[CaptureEvent]:
        """流式读取 NDJSON。tail=True 时只读新增(seek 到上次位置)。"""
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        ...

    def watch(self, session_id: str, on_event: Callable[[CaptureEvent], None]) -> None:
        """watchdog 监听文件 modify 事件,on_event 回调。"""
        ...
```

**读取规则**:
- 进程内不获取任何写锁
- 文件不存在 → 返回空列表(不抛错)
- 文件正在被 capture 写入 → 正常追读(OS 保证尾部追加原子可见)
- 文件被 capture 重命名(归档) → watcher 检测到 `moved` 事件,转为读 archive/

### 3.3 scenarios 写入契约(prism 进程)

```python
# gimbal/prism/server.py(节选)
@app.post("/api/draft/{session_id}/export")
def export_draft(session_id: str, payload: ExportIn) -> dict[str, str]:
    """draft → $GIMBAL_HOME/scenarios/{sid}.yaml。

    写盘前必须过 schema.Scenario 校验,失败 → 422 + 详细字段错误。
    """
    draft = _ensure_session(session_id)["draft"]
    scenario = build_scenario(draft)
    # schema 校验(必做)
    try:
        Scenario.model_validate(scenario)
    except ValidationError as e:
        raise HTTPException(422, detail={"schema_errors": e.errors()})

    out_path = payload.output_path or (
        gimbal_home / "scenarios" / f"{session_id}.yaml"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {"status": "ok", "path": str(out_path)}
```

**关键约束**:
- 写入前必须经 `Scenario.model_validate(scenario)`,失败拒绝写入
- 文件已存在 → **覆盖**(同 sid 视为编辑同一用例),不保留旧版本(v0)
- 输出 YAML 用 `allow_unicode=True, sort_keys=False`,字段顺序与 schema 定义一致
- v0 不做"原子写"(写一半崩溃留半文件),由 OS 提供的写语义兜底

---

## 5. 进程契约

### 4.1 端口与监听

| 进程 | 监听端口 | 配置方式 |
|---|---|---|
| `gimbal capture` | `:8080`(mitmproxy) | `gimbal capture start --port 8080` |
| `gimbal prism` | `:8765`(FastAPI/uvicorn) | `gimbal prism start --port 8765` |

> v0 **不存在** `gimbal run` 进程,因此本表无第三行。

### 4.2 进程内单例与状态隔离

| 进程 | 全局状态 | 隔离要求 |
|---|---|---|
| `gimbal capture` | `FileBus` 单例(每个 session 一个实例) | 进程内单例无问题;多进程会触发文件锁 |
| `gimbal prism` | sessions dict、ws clients | 改用 FastAPI `app.state`,**禁止** 模块级 mutable 单例 |

**改造点**(采纳功能点 11):
- 删除 `prism/server.py:64-69` 的 `recorder` / `sessions` / `ws_clients` / `_loop` 模块级单例
- 改用 `lifespan` 上下文管理器初始化 / 清理
- `recorder` 改为 `app.state.recorder`,通过 `request.app.state.recorder` 访问
- v0 **不引入** ai config 单例(AI 子包整体删除)

### 4.3 优雅退出

| 进程 | 触发方式 | 退出流程 |
|---|---|---|
| `gimbal capture` | `Ctrl+C` / SIGTERM | 1. mitmproxy 优雅停 2. FileBus.close() 释放文件锁 3. 归档 active → archive/ 4. 退出码 0 |
| `gimbal prism` | `Ctrl+C` / SIGTERM | 1. uvicorn 收到信号 2. 触发 lifespan shutdown 3. 关闭 ws 客户端 4. 退出码 0 |

---

## 6. 顶层 CLI

### 5.1 console_scripts(在 pyproject.toml)

```toml
[project.scripts]
gimbal = "gimbal.cli.app:main"
```

注册后,`pip install -e .` 后即可全局调用 `gimbal` 命令。

### 5.2 子命令树

```
gimbal
├── capture
│   ├── start       启动 mitmproxy 抓包
│   ├── list        列出 active 下的 session(只读 NDJSON 文件名)
│   ├── show        查看某个 session 的事件(分页)
│   └── archive     手动归档某个 session(立即从 active 移到 archive)
└── prism
    └── start       启动 web 配置器(默认 :8765)
```

> v0 `gimbal run` **不在此树中**——子命令未注册,`gimbal run` 直接返回"未知命令"错误。

### 5.3 完整命令示例

```bash
# capture
gimbal capture start --session dev-1 --port 8080 --filter /api/,/v1/
gimbal capture list
gimbal capture show dev-1 --limit 50
gimbal capture archive dev-1

# prism
gimbal prism start --port 8765 --home ~/.gimbal
gimbal prism start --port 8765 --home /tmp/gimbal-test   # 测试用

# 试图调用不存在的 gimbal run(v0 行为)
$ gimbal run scenarios/foo.yaml
Usage: gimbal [OPTIONS] COMMAND [ARGS]...
Try 'gimbal --help' for help.
Error: No such command 'run'.

# 帮助
gimbal --help
gimbal capture --help
gimbal capture start --help
gimbal prism --help
gimbal prism start --help
```

### 5.4 退出码约定

| 退出码 | 含义 | 触发场景 |
|---|---|---|
| 0 | 正常 | 命令成功完成 |
| 1 | 一般错误 | 业务错误(校验失败、文件不存在等) |
| 2 | 命令行参数错 | typer 校验失败 / 缺参数 |
| 3 | 环境错 | mitmproxy 未装、Python 版本不匹配 |
| 4 | 锁冲突 | capture start 时发现同 session 已被占用 |
| 5 | 权限错 | $GIMBAL_HOME 不可写 |

---

## 7. config.yaml 全局配置

```yaml
# $GIMBAL_HOME/config.yaml
# v0 仅 3 个顶层键,其他键忽略并保留供未来扩展

version: 1

# 端口默认
ports:
  capture: 8080          # mitmproxy 代理
  prism: 8765            # web 配置器

# capture 默认
capture:
  filter: "/api/"        # path 前缀过滤,逗号分隔
  out_dir: "captures/active"   # 相对于 home

# prism 默认
prism:
  static_dir: null       # null 时用 gimbal/prism/static 内置
  cors_origins: []       # 未来 CORS 用,v0 留空
```

**优先级**:
1. CLI 参数 > 环境变量 > config.yaml > 内置默认
2. v0 不实现 config.yaml 加载(留到 v0.1 增量),先全部走 CLI 参数

> v0 config.yaml **不包含** `ai:` 段(AI 子包整体未实现)。

**优先级**:
1. CLI 参数 > 环境变量 > config.yaml > 内置默认
2. v0 不实现 config.yaml 加载(留到 v0.1 增量),先全部走 CLI 参数

---

## 8. pyproject.toml 草案

```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "gimbal"
version = "0.1.0"
description = "GIMBAL 测试用例配置平台"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Proprietary" }
authors = [{ name = "gimbal team" }]

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.8",
    "typer>=0.12",
    "PyYAML>=6.0",
    "watchdog>=4.0",       # prism 监听 capture 文件用
    "mitmproxy>=12.0",     # capture 代理
    # 注意:v0 不引入 anthropic / httpx(AI 整体不做)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.6",
    "mypy>=1.11",
]

[project.scripts]
gimbal = "gimbal.cli.app:main"

# 引入 D:/M/ModelRegistry 的可编辑依赖(阶段 4 功能点 8)
[tool.uv]
dev-dependencies = [
    "ModelRegistry @ file:///D:/M/ModelRegistry",
]

[tool.hatch.build.targets.wheel]
packages = ["gimbal"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**关于 ModelRegistry 引入方式**(对应阶段 1 Q2):
- 采用 **选项 A:本地可编辑依赖**(本节 `[tool.uv]` 用 `file:///` URL)
- 同时保留 `sys.path` 注入的备选入口(在 `gimbal/__init__.py` 启动时检查 `sys.path`)
- 不采用选项 C(物理复制),避免 D:/M/ModelRegistry 副本脱钩

---

## 9. 关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 目录迁移破坏现有 import 路径 | 所有 `from prism.xxx import` 的代码失效 | 提供 `pyproject.toml` 兼容垫片(v0.1 阶段提供 `prism = gimbal.prism` 软链入口,v0.2 删除) |
| 文件锁在 Windows 上行为差异 | capture start 失败 | 抽象 `LockBackend`,Windows 用 `msvcrt`,POSIX 用 `fcntl` |
| schema 校验失败导致 export 失败 | 用户无法导出 | UI 端 `POST /api/draft/.../yaml` 提前校验 + 错误提示下钻到字段 |
| uvicorn 多 worker 下 `app.state` 不共享 | sessions dict 跨 worker 不可见 | v0 仅支持 `--workers 1`,文档明确写出 |
| D:/M/ModelRegistry 路径写死 | 不可移植 | `pyproject.toml` 用相对路径或 `os.environ["GIMBAL_MODEL_REGISTRY_HOME"]` |
| ModelRegistry 字段漂移导致 UI 渲染错 | 下拉/选项错位 | `registry_spec.py` 启动期反射 `EndpointSpec` 字段,缺失时启动失败(显式优于隐式) |
| 大 NDJSON 文件一次性 read 内存爆炸 | prism 启动慢 / OOM | FileBus 提供 `iter_events(limit=N, offset=M)` 分页 |

---

## 10. 不做的事(再强调一次)

| 不做 | 原因 |
|---|---|
| `gimbal run` 实际执行 | 用户明确"后续再看",本设计**不注册该子命令** |
| AI 助手(`prism/ai/`、`anthropic`、`httpx`) | 用户明确"先不考虑 AI" |
| `gimbal capture status` 子命令 | 文件系统状态可见(读 `ls` 即可),不需要状态查询命令 |
| 自动拉起 capture(在 prism start 里) | 用户自主决定工作流,避免隐式行为 |
| 多 worker uvicorn | sessions 是进程内状态,扩 worker 需要 Redis(超出 v0 范围) |
| prism UI 调用 capture 进程 API | 反向依赖,破坏架构原则 |
| config.yaml 完整实现 | v0 全部走 CLI 参数,config.yaml 留接口 |
| `scenarios/*.lastrun.json` | `gimbal run` 不存在,无 lastrun |
| `ai/config.json` / `ai/history/` | AI 整体未实现 |

---

## 11. 下游文档引用

- capture 模块实现细节 → [02-capture-module.md](02-capture-module.md)
- prism 配置器实现细节 → [03-prism-module.md](03-prism-module.md)
- schema 单源化与 UI 注解 → [04-schema-ssot.md](04-schema-ssot.md)
- ModelRegistry 引入 → [05-model-registry-integration.md](05-model-registry-integration.md)
- 迁移执行计划 → [06-migration-plan.md](06-migration-plan.md)
