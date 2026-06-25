# gimbal 模块架构分析报告

**日期**：2026-06-25
**范围**：`gimbal/` 全部子包（prism、schema、capture、contracts、cli、__init__）
**深度**：架构级（跨模块耦合、抽象逃逸、命名一致性、层级清晰度）
**方法**：3 个并行探索 agent 各自产出文件清单 + 依赖图 + 红旗标记，controller 综合。

---

## 1. 总览

`gimbal/` 是一个 Pydantic 驱动的测试用例配置平台，含 3 大子包：

| 子包 | LOC | 文件数 | 职责 |
|---|---|---|---|
| `gimbal/schema/` | ~870 | 14 | Pydantic 数据模型（SSOT）|
| `gimbal/capture/` | ~1180 | 9 | mitmproxy 流量捕获 + 文件总线 |
| `gimbal/prism/` | ~2350 | 22 | 配置器 web + cli + core |
| `gimbal/contracts/` | ~100 | 1 | ModelRegistry 可选桥接 |
| `gimbal/cli/` | ~130 | 3 | Typer 顶层入口 |
| **合计** | **~4630** | **49** | |

测试代码：`tests/` 约 3400 LOC。

---

## 2. 跨包依赖图

```
                    ┌────────────────────┐
                    │   gimbal.schema    │  ← Pydantic SSOT, 全部依赖此
                    │  (14 models)       │
                    └─────────┬──────────┘
                              │ used by ↓
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌────────────────┐    ┌──────────────────┐
│gimbal.capture │    │ gimbal.prism   │    │gimbal.contracts  │
│               │    │                │    │ (optional bridge)│
│  bus/loader/  │    │ core/builder/  │    └──────────────────┘
│  proxy/cli/   │    │ server/state/  │
│  strategy/    │    │ cli/render/    │
└───────┬───────┘    └────────┬───────┘
        │                     │
        └──────────┬──────────┘
                   ▼
           ┌──────────────┐
           │ gimbal.cli   │  ← 顶层 Typer entry
           │  app/capture │
           └──────────────┘
```

依赖方向基本干净（capture → cli, prism → cli, schema → 全部），无循环。

---

## 3. 模块评分（架构清晰度）

| 模块 | 评分 | 一句话 |
|---|---|---|
| `gimbal/schema/ref.py` | ⭐⭐⭐⭐⭐ | 干净，10 行 RefBase，无冗余 |
| `gimbal/schema/states.py` | ⭐⭐⭐⭐⭐ | 5 个 enum，无冗余 |
| `gimbal/schema/setup.py` / `teardown.py` | ⭐⭐⭐⭐ | 仅 `kind` 字段，过于空但语义合理 |
| `gimbal/schema/api.py` / `request.py` | ⭐⭐⭐⭐ | 单一职责，结构清晰 |
| `gimbal/schema/strategy.py` | ⭐⭐⭐⭐ | 4 种策略类型 + 4 个 enum，组合清晰 |
| `gimbal/schema/resource.py` | ⭐⭐⭐⭐ | ResourceUnion 派发合理 |
| `gimbal/schema/auth.py` | ⭐⭐⭐ | **混数据 + 行为**（compute properties + apply_token/clear_token） |
| `gimbal/schema/scenario.py` | ⭐⭐⭐⭐ | Meta+Config+Scenario 拆分合理 |
| `gimbal/schema/__init__.py` | ⭐⭐⭐⭐ | 单一职责（re-exports） |
| `gimbal/capture/recorder.py` | ⭐⭐⭐ | 命名误导——内容是 `CaptureEvent` 数据模型，非"lifecycle" |
| `gimbal/capture/filter.py` | ⭐ | **死代码**（28 LOC，零 importer）|
| `gimbal/capture/bus.py` | ⭐⭐⭐⭐ | 文件锁逻辑清晰 |
| `gimbal/capture/loader.py` | ⭐⭐ | **349 LOC，职责过载**（文件发现 + YAML 解析 + include 循环 + profile 选择 + regex 编译 + 端到端编排）|
| `gimbal/capture/cli.py` | ⭐⭐⭐ | 258 LOC，含 Typer 命令 + 子进程脚本渲染 + 探针逻辑 |
| `gimbal/capture/strategy.py` | ⭐⭐⭐ | Pydantic 模型 + 编译运行时混在一起（206 LOC）|
| `gimbal/capture/proxy.py` | ⭐⭐⭐⭐ | 单一职责（mitmproxy addon）|
| `gimbal/capture/archive.py` | ⭐⭐⭐⭐⭐ | 50 LOC，3 个函数，单一职责 |
| `gimbal/prism/convert.py` | ⭐⭐⭐ | 纯函数 `convert_record` + I/O `convert_file/load_rules` 混在一个文件 |
| `gimbal/prism/builder.py` | ⭐⭐⭐ | **396 LOC，4 个 draft dataclass + 14 函数 + 派发表**——可拆 |
| `gimbal/prism/state.py` | ⭐⭐⭐ | 260 LOC，4 个类混合（Session/CaptureReader/CaptureWatcher）|
| `gimbal/prism/server.py` | ⭐⭐ | **525 LOC，14 个路由 + lifespan + middleware + Pydantic wire + draft 转换**——超出警戒 |
| `gimbal/prism/core.py` | ⭐⭐ | **声称"pure functions no I/O"，但实际有 7+ 个 I/O 函数**（parse_ndjson/load_config/write/save_scenario/load_yaml）——违反层级契约 |
| `gimbal/prism/doc2model.py` | ⭐ | **434 LOC，混数据加载 + 类型推断 + 代码生成 + argparse CLI**——违反分层 |
| `gimbal/prism/cli/__init__.py` | ⭐⭐⭐⭐ | 干净（37 LOC，纯组装）|
| `gimbal/prism/cli/_shared.py` | ⭐⭐⭐⭐ | 4 个 helper，单一职责 |
| `gimbal/prism/cli/edit/*` | ⭐⭐⭐⭐ | 4 个 sub-app，模式一致 |
| `gimbal/prism/cli/{convert,inspect,...}.py` | ⭐⭐⭐⭐ | 每个 30-50 LOC，单一职责 |
| `gimbal/prism/cli/start.py` | ⭐⭐⭐⭐ | 48 LOC，单一职责 |
| `gimbal/prism/render/*` | ⭐⭐⭐⭐ | Schema → UI spec 反射层 |
| `gimbal/contracts/__init__.py` | ⭐⭐ | sys.path 注入副作用；当前**零调用方** |
| `gimbal/cli/app.py` | ⭐⭐⭐⭐ | 顶层 Typer 装配，try/except 静默 ImportError 可改进 |
| `gimbal/cli/capture.py` | ⭐⭐⭐⭐ | 85 LOC，4 个 Typer 命令 |
| `gimbal/__init__.py` | ⭐⭐⭐⭐⭐ | 仅 docstring + `__version__` |

---

## 4. 关键架构问题（按严重度排序）

### 🔴 严重（Critical）

#### C1. `gimbal/prism/core.py` 违反"纯函数无 I/O"契约

文档与子代理模板都强调 `core.py` 是**纯函数层**，但实际包含：

- `parse_ndjson` — 读文件
- `load_config` — 读 YAML
- `write` — 写 YAML
- `load_scenario` / `save_scenario` — 读写 YAML
- `validate_config` — 读 YAML（间接）
- `convert_ndjson_to_scenario` — 编排完整 I/O 管道

**影响**：违反架构分层承诺，使 core 既不可单测（需要临时文件）也不可在 web 复用时一致；混淆了"core 层"语义。

**根因**：v0.6 设计文档把 core 当作 "shared pipeline + edit primitives"，CLI 层通过 load → apply → save 模式调用。但实际是把 core 既当 core 又当 convenience I/O 层用。

**修复方向**：拆分 core.py 为两层：
- `core.py`（纯函数）：仅保留 edit primitives（get_meta/set_meta/list_users/...）+ render 包装 build_scenario
- `io.py`（I/O 包装）：parse_ndjson/load_config/write/load_scenario/save_scenario

CLI 层通过 core.py（pure）+ io.py（io）组合，避免"core has I/O"的语义破坏。

#### C2. `gimbal/prism/doc2model.py` 违反分层（434 LOC）

单一文件混合了 4 个职责：
1. 数据加载（JSON/YAML 样本读取）
2. 类型推断（string/int/list/dict/Enum 启发式）
3. Pydantic 模型代码生成（字符串拼接）
4. argparse CLI（与项目其它 Typer CLI 不一致）

**影响**：434 LOC 的"上帝文件"，不可复用其中任何一层（库使用者被迫引入 argparse）。

**修复方向**：拆分：
- `doc2model/infer.py` — 类型推断函数
- `doc2model/codegen.py` — Pydantic 模型代码生成
- `doc2model/cli.py` — argparse 入口（保留兼容）
- `doc2model/__init__.py` — re-exports

#### C3. `gimbal/prism/server.py` 525 LOC，单文件过多职责

FastAPI 文件同时承担：
- HTTP 路由（14 个端点）
- lifespan 管理
- 中间件（cache-control）
- Pydantic wire forms（DraftIn）
- draft-from-payload 转换（`_draft_from_in`）
- static file serving
- WebSocket 路由

**影响**：违反"文件大小与单一职责"原则；测试需要加载整个 FastAPI app 才能测单个端点；新增端点需滚动大量无关代码。

**修复方向**：拆分：
- `server/app.py` — FastAPI app + lifespan + middleware
- `server/routes.py` — 14 个路由
- `server/wire.py` — DraftIn/UserIn wire Pydantic
- `server/conversions.py` — `_draft_from_in`

---

### 🟡 中等（Important）

#### I1. `gimbal/prism/builder.py` 396 LOC，混数据 + 行为

4 个 draft dataclass + 14 函数 + 派发表 + `build_scenario()` 主函数 + `Meta.createTime = datetime.now()` 副作用。

**修复方向**：拆分：
- `builder/drafts.py` — 4 个 dataclass
- `builder/resources.py` — 资源派发表（5 种 kind 的 dispatch）
- `builder/steps.py` — `_build_step` + strategy 构造
- `builder/scenario.py` — `build_scenario()` 主函数 + time_policy/retry/setup/teardown

#### I2. `gimbal/capture/loader.py` 349 LOC，7 个职责

文件发现、YAML 解析、include 循环检测、profile 选择、regex 编译、CSV 追加、sentinel fallback。

**修复方向**：拆分：
- `capture/loader/discovery.py` — 文件查找
- `capture/loader/yaml_parser.py` — YAML 解析 + include 循环
- `capture/loader/profile.py` — profile 选择
- `capture/loader/compile.py` — regex 编译 + matcher 构建

#### I3. `gimbal/capture/strategy.py` 混 Pydantic 模型 + 编译运行时

206 LOC 含：
- 3 个 Pydantic 模型（Rule, Profile, StrategyFile）
- 1 个 enum
- 1 个 dataclass（CompiledRule）
- 1 个 matcher 类 + `_match_one` 实现

**修复方向**：拆分：
- `capture/strategy/models.py` — Pydantic
- `capture/strategy/runtime.py` — CompiledMatcher + match 逻辑

#### I4. NDJSON line reading 重复 4 次

相同 `for line in f: strip + json.loads` 模式出现在：
- `prism/state.py:CaptureReader.read`
- `prism/core.py:parse_ndjson`
- `prism/convert.py:convert_file`
- `prism/doc2model.py:load_samples`

**修复方向**：抽出 `gimbal/io_utils.py::iter_ndjson_lines(path) -> Iterator[dict]`，4 处复用。消除漂移风险。

#### I5. YAML load/save 重复 2 处

- `prism/core.py:load_scenario/save_scenario`
- `prism/cli/_shared.py:load_yaml/save_yaml`

`load_yaml` 已含 `print_error` + 缺文件处理；`load_scenario` 没有。漂移风险。

**修复方向**：CLI 层直接调用 `core.load_scenario` + `cli._shared.print_error`，让 `core` 拥有统一语义，删除 `_shared.load_yaml/save_yaml`。

#### I6. `prism/state.py` 反向依赖 `prism/server.py`

`SessionStore.get_or_create` 用**延迟 import** 引入 `server.DraftIn`——这意味着 state 隐式依赖 server 的 wire form。

**修复方向**：将 `DraftIn`（或最少需要的字段）下沉到 `state.py` 或 `schema/`，删除循环。

#### I7. `gimbal/contracts/` 零调用方 + sys.path 副作用

`__init__.py` 第 30+ 行做 `sys.path.insert(0, ...)` 来注入 ModelRegistry；当前**没有任何模块 import 它**（grep 零命中）。

**影响**：副作用 sys.path 注入，但提供的能力未被消费——是"未来集成"的占位代码。

**修复方向**：删除 `contracts/`，待真有需求时重新引入。或者：把注入移到可选的 CLI 命令中（`gimbal contracts status`），按需触发。

#### I8. `prism/state.py` 内多类混入

260 LOC 含：
- `Session`（draft + history + undo/redo）
- `SessionStore`（sessions dict）
- `CaptureReader`（只读 NDJSON 视图）
- `CaptureWatcher`（自实现轮询线程）

**修复方向**：拆分：
- `state/session.py` — Session + SessionStore
- `state/capture.py` — CaptureReader + CaptureWatcher

#### I9. `prism/convert.py` 混纯函数 + I/O

`convert_record`（纯函数）+ `convert_file/load_rules`（I/O）混合。

**修复方向**：把 `convert_file` 移到 `core.py` 或 `cli/_shared.py`；`convert.py` 仅保留纯函数 `convert_record/load_rules`。

---

### 🟢 轻微（Minor）

#### M1. `gimbal/capture/filter.py` 死代码

28 LOC，零 importer。计划中保留兼容但实际无人调用。

**修复方向**：删除文件。

#### M2. `gimbal/capture/recorder.py` 命名误导

模块注释"capture lifecycle"，实际是 `CaptureEvent` 数据模型定义。lifecycle 在 cli.py 和 proxy.py。

**修复方向**：改名 `recorder.py` → `event.py`（或保持现状但改 docstring）。

#### M3. `gimbal/schema/auth.py` 混数据 + 行为

`AuthSession` 既存储凭据又有 `apply_token/clear_token/is_same_credential` 等方法。

**影响**：Pydantic 模型应只描述数据形状；token 生命周期管理应在 schema 外的 service 层。

**修复方向**：拆分为：
- `schema/auth.py` — 仅数据模型
- `auth/service.py` — token 生命周期（新增）

#### M4. 字段命名 camelCase vs snake_case 漂移

Schema 用 camelCase（scenarioId, createTime, portMapping, maxAttempts），prism YAML 配置用 snake_case（scenario_id, port_mapping, max_attempts）。映射逻辑散落在 `core.load_config`、`builder._make_mock`、`builder._time_policy` 等多处。

**修复方向**：
- 在 `core.load_config` 集中处理（已基本完成）
- 文档化"schema = camelCase, yaml = snake_case, mapping 在 core.load_config"

#### M5. Setup / Teardown schema 字段过空

`Setup` / `Teardown` 只有 `kind` 字段，无实际内容。`builder.build_scenario` 总是 emit `Setup(kind="setup") + SetupRef(ref=r)` pair，看起来 schema 还没设计完整。

**修复方向**：待真有 setup 内容需求时扩展；当前保留即可。

#### M6. `prism/render/` 用 Pydantic `_PydField` 直接而非包级 `Field(ui=...)`

UI spec 反射代码直接 import pydantic 而非走 `gimbal.schema.Field`，漂移风险。

**修复方向**：render 层统一用包级 `Field`，减少 schema 与 render 的耦合。

#### M7. `gimbal/cli/app.py` 静默 ImportError

```python
try:
    from gimbal.cli.capture import capture_app
    app.add_typer(capture_app, name="capture")
except ImportError:
    pass
```

这掩盖了真实问题（曾经导致 Task 21 的 wiring bug）。

**修复方向**：保留 try/except 但加显式 warning（`typer.echo("WARN: gimbal.cli.capture not available", err=True)`）。

#### M8. 缺尾换行符

多文件缺最终 `\n`（v0.6.1 已修 16 个，但其它子包仍有遗留）。

---

## 5. 重构优先级建议

按"价值/风险比"排序：

### 第一批（高价值、低风险，立即执行）

1. **删除 `gimbal/capture/filter.py`**（死代码，零风险）
2. **抽出 `gimbal/io_utils.py::iter_ndjson_lines()`**（4 处复用，立即消除漂移）
3. **`prism/cli/_shared.py` 删除 `load_yaml/save_yaml`**，统一调用 `core.load_scenario/save_scenario`（已有等价 API）
4. **`prism/convert.py` 拆分**：`convert_record` 留下，`convert_file` 移至 `cli/_shared.py`
5. **修复 `prism/state.py` 对 `prism/server.py` 的反向依赖**（下沉 DraftIn 到 state）

### 第二批（中等价值、需要测试）

6. **拆分 `prism/server.py`** → app/routes/wire/conversions（~250 + ~250 + ~50 + ~50 LOC）
7. **拆分 `prism/builder.py`** → drafts/resources/steps/scenario
8. **拆分 `prism/doc2model.py`** → infer/codegen/cli
9. **`gimbal/contracts/` 移除或重新定位**（要么真集成，要么删除）

### 第三批（待评估）

10. **`gimbal/schema/auth.py` 数据/行为分离**
11. **`capture/loader.py` 拆分**（349 LOC 多职责）
12. **`capture/strategy.py` 拆模型 vs 运行时**
13. **`prism/state.py` 拆分 session/capture**

---

## 6. 总结

- **优点**：
  - `gimbal/schema/` 子包 DAG 干净，无循环，SSOT 明确
  - `gimbal/prism/cli/` 9 个子命令分层清晰，文件大小合理
  - `gimbal/prism/core.py` 的 edit primitives 设计良好（pure functions）
  - v0.6 的子命令架构对齐"section-grouped editing"语义

- **核心问题**：
  - **C1（core.py 违反"无 I/O"契约）**是当前架构最大的认知负担——文档承诺和实现不符
  - **C2 + C3（doc2model + server.py 两个超 400+ LOC 文件）**是实际的维护负担
  - **I7（contracts 零调用方）**是死代码 + 副作用
  - **I4 + I5（重复 NDJSON/YAML 读取）**是漂移源

- **结论**：
  项目整体结构清晰，但有 3 个 Critical + 9 个 Important 问题值得重构。第一批 5 个改动是高 ROI 的清理；第二批 3 个文件拆分是中等工作量但回报明确；第三批需要更多设计讨论。

---

## 7. 下一步

按用户要求，本报告+配套实施计划已完成。计划文档由 `superpowers:writing-plans` skill 起草，列出每个重构的具体步骤（精确路径、文件大小目标、测试要求、commit 边界）。

报告保存在 `docs/superpowers/specs/2026-06-25-architecture-analysis.md`，配套计划即将生成。