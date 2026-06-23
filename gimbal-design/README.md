# gimbal 设计文档

> 本目录是 `d:/mirror`(gimbal 平台)的设计文档归档。所有从阶段 1 评审通过的设计决策、新增功能点实现细节、迁移计划,均沉淀在此。

---

## 0. 文档索引

| 编号 | 文档 | 范围 | 状态 |
|---|---|---|---|
| 01 | [01-architecture.md](01-architecture.md) | 总体架构 · 两个模块拆分 · 顶层 CLI · 文件系统契约 | ✅ v0.1 |
| 02 | [02-capture-module.md](02-capture-module.md) | `gimbal capture` 模块详细设计 | ✅ v0.1 |
| 03 | [03-prism-module.md](03-prism-module.md) | `gimbal prism` 配置器详细设计 | ✅ v0.1 |
| 04 | [04-schema-ssot.md](04-schema-ssot.md) | schema 单源化 · UI 注解体系 · 前端声明式渲染 | ✅ v0.1 |
| 05 | [05-model-registry-integration.md](05-model-registry-integration.md) | 引入 D:/M/ModelRegistry 的 ModelRegistry + schema 增强 | ✅ v0.1 |
| 06 | [06-migration-plan.md](06-migration-plan.md) | 迁移执行计划 · 里程碑 · 风险与验收 | ✅ v0.1 |
| 07 | [07-filter-strategy.md](07-filter-strategy.md) | v0.4 Capture Filter Strategy 实施归档 (YAML + profile + include) | ✅ v0.4 |

---

## 1. 背景与目标

### 1.1 现状摘要

- `d:/mirror` 当前包含 `prism/`(配置器 + 代理)、`schema/`(pydantic 模型)、`ModelRegistry/`(endpoint 契约注册中心)、`tests/`、`docs/`
- `prism` 单一进程同时承担:① 抓包代理 ② web 配置器(原 d:/mirror 中还含 AI 助手,v0 删除)
- `schema` 字段名在 `prism/server.py:150 DraftIn` + `prism/static/index.html` HTML id 等多处重复定义(原 AI 派生文件 v0 删除)
- `D:/M/ModelRegistry` 是 d:/mirror 的离线副本,包含 `ModelRegistry/`(4 文件 md5 一致)与 `prism/_schema/`(内联 schema 副本,部分增强)
- v0 范围:仅两个独立模块 `gimbal capture` + `gimbal prism`,**不包含**执行器与 AI 助手

### 1.2 目标

将 d:/mirror 演进为 **gimbal 平台**(v0),包含**两个**独立模块:

| 模块 | 角色 | 入口命令 | 状态 |
|---|---|---|---|
| `gimbal capture` | 流量录制器 | `gimbal capture start --session <sid>` | v0 实现 |
| `gimbal prism` | 配置器(web) | `gimbal prism start` | v0 实现 |

并达成以下架构目标:

1. **两个模块进程级独立**,无反向依赖,无进程间 API
2. **文件系统作为唯一契约**(`$GIMBAL_HOME/captures/` 与 `$GIMBAL_HOME/scenarios/`)
3. **schema 作为单一事实源**(SSOT):UI、校验统一从 schema 派生
4. **ModelRegistry 驱动前端**:从 D:/M/ModelRegistry 反射 → `/api/registry/ui-spec` → 下拉/选项/自动补全
5. **D:/M/ModelRegistry 引入**:本地可编辑依赖,ModelRegistry 与 schema 增强并入主线
6. **前端样式基线切换为 D:/M/ModelRegistry 版本**(纯净版,不叠加 AI 视图)

### 1.3 显式不做(v0)

- ❌ **不实现** `gimbal run` 执行引擎(子命令不注册)
- ❌ **不实现** AI 助手:删除 `gimbal/prism/ai/`,不依赖 `anthropic` / `httpx`,不创建 `$GIMBAL_HOME/ai/`
- ❌ 不做 AI 工具/Prompts 从 schema 自动派生(原 B5 后续;因 AI 整体不做,这两项也跟着不做)
- ❌ 不引入 D:/M/ModelRegistry 的 `prism/_schema/` 内联副本(避免双源,以 d:/mirror/schema/ 为准)
- ❌ 不重做 prism 前端视觉(沿用 D:/M/ModelRegistry 样式,无 AI 视图叠加)
- ❌ 不补大规模 E2E 测试(只补 schema + builder + capture + prism render 核心路径)

---

## 2. 范围对照(阶段 1 评审采纳)

阶段 1 提出的 14 项功能点中,本次 v0 采纳 11 项:

| 功能点 | 状态 | 见文档 |
|---|---|---|
| 1. 两个模块拆分(capture / prism) | ✅ 采纳 | [01](01-architecture.md) / [02](02-capture-module.md) / [03](03-prism-module.md) |
| 2. 文件系统契约 | ✅ 采纳 | [01](01-architecture.md) §4 |
| 3. gimbal 顶层 CLI + console_scripts(仅 capture/prism) | ✅ 采纳 | [01](01-architecture.md) §6 |
| 4. schema SSOT · UI 注解 · 声明式渲染 | ✅ 采纳 | [04](04-schema-ssot.md) |
| 5. Step.key + Meta.name blank 校验 | ✅ 采纳 | [05](05-model-registry-integration.md) §2 |
| 6. capture/prism 进程解耦 | ✅ 采纳 | [02](02-capture-module.md) / [03](03-prism-module.md) |
| 7. 归档策略 | ✅ 采纳 | [02](02-capture-module.md) §5 |
| 8. ModelRegistry 数据类引入 | ✅ 采纳 | [05](05-model-registry-integration.md) |
| 9. ModelRegistry → UI spec(`/api/registry/ui-spec`) | ✅ 采纳 | [04](04-schema-ssot.md) §6 / [03](03-prism-module.md) §6 |
| 10. (B5 取消)AI tools 自动推导 | ❌ 不做(AI 整体未实现) | — |
| 11. FastAPI lifespan 改造 | ✅ 采纳 | [03](03-prism-module.md) §3 |
| 12. 资源 kind 枚举收敛 | ✅ 采纳 | [03](03-prism-module.md) §7 |
| 13. 默认断言 name 可复现 | ✅ 采纳 | [03](03-prism-module.md) §7 |
| 14. 架构决策档案 | ✅ 采纳(本目录) | — |

---

## 3. 命名约定

| 旧名(本次改造前) | 新名(v0) | 说明 |
|---|---|---|
| `prism capture` 子命令 | `gimbal capture start` | 独立进程 |
| `prism ui serve` | `gimbal prism start` | 独立进程 |
| `prism ui run` | — | **删除**(v0 不实现执行器) |
| `prism/ui_cli.py` | `gimbal/cli/prism.py` | 顶层 CLI 子命令(只注册 prism 子命令) |
| `prism/capture.py` | `gimbal/capture/proxy.py` | 物理迁出 prism/ |
| `prism/recorder.py` | `gimbal/capture/bus.py` + `gimbal/capture/recorder.py` | 总线与事件 dataclass 拆开 |
| `prism/server.py` | `gimbal/prism/server.py` | 物理迁出 prism/ |
| `prism/builder.py` | `gimbal/prism/builder.py` | 物理迁出 prism/ |
| `prism/ai/*` | — | **删除**(v0 不实现 AI) |
| `prism/static/chat.js` | — | **删除**(随 AI 子包) |
| `prism/static/ai-settings.js` | — | **删除**(随 AI 子包) |
| `prism/static/*` (其余) | `gimbal/prism/static/*` | 物理迁出 prism/(沿用 D:/M/ModelRegistry 基线) |
| `schema/` | `gimbal/schema/` | 物理迁出,挂顶级包 |
| `ModelRegistry/` | `gimbal/contracts/` | 物理迁出,顶级包(可选) |

**核心原则**:
- 所有"gimbal 平台代码"统一前缀 `gimbal.`,**不再保留** 顶层 `prism/` 与 `schema/` 目录
- 原 `prism/` 目录在 v0.1 起**不再创建**,代码全部迁入 `gimbal/`
- 原 `prism/ai/` 目录**不迁入**,v0 直接删除(用户明确"先不考虑 AI")
- D:/M/ModelRegistry 的 `prism/_schema/` 内联副本**不引入**,统一以 `gimbal/schema/` 为准

---

## 4. 阅读顺序建议

- 想理解**整体架构** → [01-architecture.md](01-architecture.md)
- 负责 **capture 模块** 实现 → [02-capture-module.md](02-capture-module.md)
- 负责 **prism 配置器** 实现 → [03-prism-module.md](03-prism-module.md)
- 负责 **schema/前端** 实现 → [04-schema-ssot.md](04-schema-ssot.md)
- 负责 **D:/M/ModelRegistry 引入** → [05-model-registry-integration.md](05-model-registry-integration.md)
- 想知道**执行节奏** → [06-migration-plan.md](06-migration-plan.md)
- 想了解 **v0.4 筛选策略**（YAML 配置 / profile / include 复用）→ [07-filter-strategy.md](07-filter-strategy.md)
