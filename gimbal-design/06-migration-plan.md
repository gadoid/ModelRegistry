# 06 · 迁移执行计划

> 本文档描述把 d:/mirror 演进为 gimbal 平台的**具体执行步骤**、里程碑、验收标准、回滚方案。

---

## 1. 总体节奏

### 1.1 4 个里程碑(M1~M4)

| 里程碑 | 范围 | 工作日 | 验收标志 |
|---|---|---|---|
| **M1 · 两个模块拆分** | capture/prism 物理迁出 + 文件系统契约 + 顶层 CLI + 痛点修复 11/12/13 | ~12 天 | `gimbal capture start` 和 `gimbal prism start` 两个独立进程跑通;prism 不再持有 recorder;前端 captures 角标仍可见 |
| **M2 · schema SSOT** | schema 加 UI 注解 + `/api/schema/ui-spec` + 声明式渲染 + schema 增强合并 | ~10 天 | `/api/schema/ui-spec` 返回正确分组;前端按 spec 动态渲染;Meta.name 空白校验生效 |
| **M3 · ModelRegistry 引入** | D:/M/ModelRegistry 引入 + contracts 子包 + doc2model 改造 | ~3 天 | `from gimbal.contracts import EndpointSpec` 可用;`is_available()` 反映真实状态;CI 不依赖 D:/M/ModelRegistry 路径 |
| **M4 · 集成与文档** | 集成测试 + README 重写 + 文档归档 + 公告 | ~3 天 | 端到端 capture→prism→export YAML→schema 校验通过;README 第一屏讲清两个模块故事 |

**总计**:**~28 天**(5.5 周)。

### 1.2 关键依赖关系

```
M1 ───┬──> M2(依赖 M1 的两个模块拆完)
      │
      └──> M3(依赖 M1 的 gimbal 包结构,可不依赖 M2)

M2 ───┬──> M4
      │
M3 ───┘
```

- M2 与 M3 可并行,但都在 M1 完成后才能开始
- M4 是所有里程碑的集成 + 收尾

---

## 2. M1 · 两个模块拆分(~12 天)

### 2.1 任务清单

| # | 任务 | 工时 | 风险 | 验收 |
|---|---|---|---|---|
| M1.1 | 创建 `gimbal/` 顶层包结构(`__init__.py` + 空子包) | 0.5 天 | 0 | `python -c "import gimbal"` 成功 |
| M1.2 | 物理迁移 `prism/capture.py` → `gimbal/capture/proxy.py`,import 改 `gimbal.*` | 0.5 天 | 低 | `gimbal/capture/proxy.py` 单测通过 |
| M1.3 | 物理迁移 `prism/recorder.py` → `gimbal/capture/{recorder.py,bus.py}`,新增 FileBus | 1.5 天 | 中 | FileBus 单测覆盖写入/锁/并发 |
| M1.4 | 物理迁移 `prism/cli.py` `capture` 子命令 → `gimbal/cli/capture.py` | 0.5 天 | 低 | `gimbal capture --help` 列出 4 子命令 |
| M1.5 | 实现 `gimbal capture archive` 子命令 | 0.5 天 | 低 | 归档 + 残留检测单测通过 |
| M1.6 | 物理迁移 `prism/server.py` → `gimbal/prism/server.py`,删除 captures 内存路由,改为读文件 | 2 天 | 中 | `/api/captures?sid=xxx` 走文件读取 |
| M1.7 | 物理迁移 `prism/builder.py` → `gimbal/prism/builder.py`,功能点 13(可复现 name) | 0.5 天 | 低 | builder 单测全过 |
| M1.8 | 物理迁移 `prism/convert.py` / `doc2model.py` → `gimbal/prism/` | 0.5 天 | 低 | 单测过 |
| M1.9 | **删除** `prism/ai/*` 目录(AI 整体不实现,见 01 §1.2) | 0.1 天 | 0 | grep `prism/ai` 无引用 |
| M1.10 | 物理迁移 `prism/static/*` → `gimbal/prism/static/*`,前端 API 路径加 `?sid=`,**移除** chat.js / ai-settings.js | 1 天 | 中 | 浏览器打开看到 captures 列表(无 AI 视图) |
| M1.11 | **痛点 11**:FastAPI lifespan 改造(app.state 取代模块级单例) | 1 天 | 中 | `app.state.*` 全部初始化;旧 `prism/server.py` 单例代码全删 |
| M1.12 | **痛点 12**:资源 kind 派发表 | 0.5 天 | 低 | `_build_resource` 不再用 if/elif 串行 |
| M1.13 | **痛点 13**:默认断言 name 可复现(已在 M1.7 完成) | 0 | — | — |
| M1.14 | 创建 `pyproject.toml` + console_scripts `gimbal`,**不注册** `gimbal run` 子命令 | 0.5 天 | 低 | `pip install -e .` 后 `gimbal --help` 仅列出 capture/prism |
| M1.15 | 全量回归测试 | 1 天 | 中 | `pytest tests/` 全过(无 test_ai_*) |

### 2.2 验收标准

```bash
# 1. capture 独立进程跑通
$ gimbal capture start --session dev-1 --port 8080
[capture] session=dev-1  port=8080  filter=/api/
[capture] out=C:\Users\me\.gimbal\captures\active\dev-1.ndjson
[Ctrl+C]
[capture] stopping...
[capture] archived → C:\Users\me\.gimbal\captures\archive\2026-06-18\dev-1-1700000000.ndjson

# 2. prism 独立进程跑通(独立于 capture)
$ gimbal prism start --port 8765
[prism] GIMBAL_HOME=C:\Users\me\.gimbal
[prism] starting on http://127.0.0.1:8765

# 3. UI 看到刚才 capture 的数据
# 浏览器打开 http://127.0.0.1:8765 → 选 session=dev-1 → 看到 capture 列表

# 4. 同 session 二次 capture 报锁冲突
$ gimbal capture start --session dev-1
[ERROR] session 已被另一个进程占用

# 5. 静态分析
$ ruff check gimbal/
$ mypy gimbal/
```

### 2.3 回滚方案

每个 M1.x 子任务独立提交(commit),失败时 `git revert <commit>` 单点回滚。

物理迁移采用**双写**策略:
- 旧 `prism/xxx.py` 在 M1 期间保留但 deprecated(发 `DeprecationWarning`)
- 新 `gimbal/xxx.py` 同步实现
- M1 全部子任务完成后,统一提交"删除旧 prism/" PR

---

## 3. M2 · schema SSOT(~10 天)

### 3.1 任务清单

| # | 任务 | 工时 | 风险 | 验收 |
|---|---|---|---|---|
| M2.1 | 在 `gimbal/schema/__init__.py` 实现 `Field(..., ui=...)` 包装 | 0.5 天 | 低 | 单测覆盖 `ui` 元数据传入 |
| M2.2 | 给 `Meta` / `Config` / `TimePolicy` / `RetryPolicy` / `Resource` 等所有顶层模型加 UI 注解 | 2 天 | 中 | 每个字段都有 ui 配置;无遗漏 |
| M2.3 | 实现 `gimbal/prism/render/walk_fields` 遍历算法 | 1 天 | 中 | 嵌套 model 递归正确;Union / list 正确处理 |
| M2.4 | 实现 `gimbal/prism/render/ui_spec.py:build_ui_spec` | 1 天 | 中 | `/api/schema/ui-spec` 返回正确 JSON |
| M2.5 | schema 增强合并:Step.key + Meta.name blank 校验 | 0.5 天 | 低 | 见 05 §2 |
| M2.6 | `/api/schema/dot-paths` 端点 | 0.5 天 | 低 | 端点返回合法路径列表 |
| M2.7 | **前端声明式渲染引擎** `app.js`:fetch spec → 动态生成控件 | 3 天 | 高 | 浏览器打开 UI,字段正确渲染;双向绑定工作 |
| M2.8 | D:/M/ModelRegistry 样式接入(直接作为基线,不叠加 AI 视图) | 1 天 | 中 | 视觉与 D:/M/ModelRegistry 一致;无 AI 视图 |
| M2.9 | 测试:schema 注解覆盖 + ui_spec 单测 + 端到端 | 1 天 | 中 | `pytest tests/test_schema_*` 全过 |

### 3.2 验收标准

```bash
# 1. ui-spec 端点
$ curl http://127.0.0.1:8765/api/schema/ui-spec | jq '.groups[0]'
{
  "id": "meta",
  "label": "用例元信息",
  "icon": "info-circle",
  "fields": [
    {"path": "meta.name", "widget": "input", "required": true, "label": "用例名", ...},
    {"path": "meta.priority", "widget": "select", "options": [...], ...},
    ...
  ]
}

# 2. dot-paths 端点
$ curl http://127.0.0.1:8765/api/schema/dot-paths | jq '.count'
47

# 3. Meta.name blank 校验
$ curl -X POST http://127.0.0.1:8765/api/draft/test/export
{"detail": {"schema_errors": [{"loc": ["meta", "name"], "msg": "name 不能为空白字符串"}]}}

# 4. 浏览器
# 打开 http://127.0.0.1:8765
# 看到 4 tab,字段按 schema spec 渲染
# 改字段 → 实时同步到 draft → 改 retry.enabled=true → retry 子字段显示
```

### 3.3 回滚方案

`schema/__init__.py` 的 `Field` 包装**保留向后兼容**:无 `ui=` 参数时行为与原生 pydantic.Field 一致。回滚时只需把 `Field(..., ui=...)` 改为 `Field(...)`,ui 注解全部失效,前端退回静态 HTML。

---

## 4. M3 · ModelRegistry 引入(~3 天)

### 4.1 任务清单

| # | 任务 | 工时 | 风险 | 验收 |
|---|---|---|---|---|
| M3.1 | 实现 `gimbal/contracts/__init__.py` 双路径加载(pip 优先 + 环境变量兜底) | 1 天 | 中 | 装上 model-registry-local 可用;不装也能 import,只是 is_available() = False |
| M3.2 | `pyproject.toml` 加 `[project.optional-dependencies] model-registry` | 0.2 天 | 低 | `pip install -e ".[model-registry]"` 成功 |
| M3.3 | 改造 `gimbal/prism/doc2model.py` 用 `gimbal.contracts` 而非 `from ModelRegistry.spec` | 0.5 天 | 低 | doc2model 子命令在 ModelRegistry 不可用时友好失败 |
| M4.4 | builder.py 可选调用 `registry.resolve()`(失败降级) | 0.5 天 | 低 | 可用时 step.endpoint_ref 被填充;不可用时跳过 |
| M3.5 | 测试:3 种状态(装上/环境变量/无)的契约加载 | 1 天 | 中 | `tests/test_contracts_init.py` 全过 |

### 4.2 验收标准

```python
# 1. 装上 model-registry-local
$ pip install -e ".[model-registry]"
$ python -c "from gimbal.contracts import EndpointSpec, is_available; print(is_available())"
True

# 2. 不装 + 环境变量
$ unset pip-installed
$ export GIMBAL_MODEL_REGISTRY_PATH=D:/M/ModelRegistry
$ python -c "from gimbal.contracts import EndpointSpec, is_available; print(is_available())"
True

# 3. 完全不可用
$ unset GIMBAL_MODEL_REGISTRY_PATH
$ python -c "from gimbal.contracts import is_available; print(is_available())"
False

# 4. CI 跑通(无 D:/M/ModelRegistry 路径)
$ pytest tests/test_contracts_init.py -v
# 三种状态都有覆盖
```

### 4.3 回滚方案

`gimbal/contracts/__init__.py` 完全独立,失败可直接 `rm -rf gimbal/contracts/`,对其他模块零影响。

---

## 5. M4 · 集成与文档(~3 天)

### 5.1 任务清单

| # | 任务 | 工时 | 风险 | 验收 |
|---|---|---|---|---|
| M4.1 | 集成测试:capture→prism→export→schema 校验端到端 | 1.5 天 | 中 | `tests/integration/test_e2e.py` 覆盖主流程 |
| M4.2 | 重写顶层 README,讲两个模块故事 + 安装 + 快速上手 | 1 天 | 低 | README 第一屏讲清"capture→prism(配置→导出 YAML)"完整闭环 |
| M4.3 | 公告 / release notes / changelog | 0.5 天 | 0 | CHANGELOG.md 增 v0.1.0 条目 |

### 5.2 验收标准

```bash
# 1. 端到端
$ pytest tests/integration/test_e2e.py -v
test_e2e_capture_prism_export  PASSED

# 2. README 第一屏
$ head -50 README.md
# gimbal · 测试用例配置平台
> capture 抓真实流程 → prism 编辑成场景 → gimbal run 执行用例

## 安装
pip install -e ".[model-registry]"   # 可选,启用 ModelRegistry

## 快速上手
$ gimbal capture start --session dev-1
$ gimbal prism start   # 打开 http://127.0.0.1:8765
```

---

## 6. 风险清单(总体)

| 风险 | 影响 | 缓解 |
|---|---|---|
| 物理迁移路径破坏现有 import | 旧代码全部失效 | M1 全程双写;删除旧 prism/ 之前发 DeprecationWarning |
| uvicorn `--workers > 1` 时 sessions 跨 worker 不可见 | 用户多 worker 时数据错乱 | v0 强制 `workers=1`,文档明确 |
| 文件锁在 NFS / 网络盘失效 | capture start 失败 | 检测路径类型 + 拒绝网络盘 |
| Windows Defender 误杀 mitmproxy addon 脚本 | capture 启动失败 | 文档指引加白名单 |
| `file:///D:/M/ModelRegistry` 路径 Linux CI 失败 | CI 跑不通 | CI 用环境变量 + `optional-dependencies` 跳过 |
| prism/ai/ 子包残留(若未删除) | 误以为 AI 仍存在,引入新依赖 | M1.9 显式 `rm -rf prism/ai/` + 任何 import 必失败 |
| D:/M/ModelRegistry 删除/移动 | dev 环境失效 | `gimbal.contracts.is_available()` 检测 + 友好提示 |
| schema UI 注解遗漏某个字段 | 前端不渲染 | M2 验收要求"每个顶层字段都有 ui" |

---

## 7. 验收总览

### 7.1 功能验收

| 功能 | 验收命令 |
|---|---|
| capture 独立运行 | `gimbal capture start --session test` 启动,Ctrl+C 归档 |
| capture 列出/查看 | `gimbal capture list` / `gimbal capture show test` |
| prism 独立运行 | `gimbal prism start` 起 :8765,UI 可访问 |
| captures 文件读取 | UI 看到 NDJSON 事件列表(从 `$GIMBAL_HOME/captures/active/`) |
| 实时 capture 推送 | capture 写入新事件 → prism SSE 推送 → UI 自动追加 |
| draft 编辑 | 改任意字段 → 自动 PUT /api/draft/{sid} |
| YAML 导出 | 点"导出 YAML" → 写 `$GIMBAL_HOME/scenarios/{sid}.yaml` |
| schema 校验失败 | draft 字段非法 → 422 + 字段路径提示 |
| undo/redo | UI 撤销按钮 → draft 回滚到上版 |
| schema SSOT | UI 字段定义来自 `/api/schema/ui-spec` |
| ModelRegistry 引入 | `from gimbal.contracts import EndpointSpec` 可用 |
| ModelRegistry → UI spec | `GET /api/registry/ui-spec` 返回 endpoints/auth/templates;前端 select 用之 |

### 7.2 非功能验收

| 维度 | 标准 |
|---|---|
| 单测覆盖 | `gimbal/` 子模块 line coverage ≥ 80% |
| 集成测试 | capture→prism→export 端到端通过 |
| 静态分析 | `ruff check` 0 error;`mypy` 0 error(忽略无注解的 __init__.py) |
| 性能 | prism start < 3 秒(cold start);capture 启动 < 5 秒(含 mitmdump) |
| 内存 | prism 常驻 < 200MB;capture < 150MB |
| 文档 | README 第一屏讲清产品故事;`gimbal-design/` 6 文档齐全 |
| 安装 | `pip install -e .` + `pip install -e ".[model-registry]"` 双路径都跑通 |

---

## 8. 团队协作建议

### 8.1 任务分配(若 2 人)

| 人 | 任务 |
|---|---|
| A · 架构师 | M1.1~M1.5(capture 拆分 + FileBus + 归档) + M1.9(删除 prism/ai) + M3.1~M3.5(ModelRegistry) |
| B · 前端 | M1.10(前端迁移) + M2.7(声明式渲染) + M2.8(样式接入) |
| 共担 | M1.6(prism server 改造,功能点 11) + M1.16(回归) + M4 |

### 8.2 PR 节奏

- 每个 Mx.y 独立 PR,标题格式 `[M1.3] 实现 FileBus 与文件锁`
- PR 描述必须包含:动机 / 改动 / 验收命令 / 关联 issue
- 至少 1 人 review + CI 通过才能 merge
- 单 PR 控制在 1 天工作量内

### 8.3 沟通机制

- 每日 standup:3 个 bullet(昨天做了什么 / 今天做什么 / 阻塞)
- 每周 demo:周五下午录 5 分钟视频演示当前里程碑成果
- 重大决策(影响 > 3 天工作量)需要先写 RFC 进 `gimbal-design/`,再评审

---

## 9. 不做的事(再次明确)

| 不做 | 文档引用 |
|---|---|
| AI 助手(`gimbal/prism/ai/`、`anthropic`、`httpx`、AI chat UI) | 见 [01-architecture.md §2.2](01-architecture.md) |
| `gimbal run` 执行引擎 | 见 [01-architecture.md §1.2](01-architecture.md) |
| 大规模 E2E 测试补全 | 见 [01 §9](01-architecture.md) |
| frontend 视觉重设计(沿用 D:/M/ModelRegistry 样式) | 见 [03 §9](03-prism-module.md) |
| 多 worker uvicorn | 见 [01 §1.2](01-architecture.md) |
| prism 启动 capture(隐式拉起) | 见 [01 §10](01-architecture.md) |

---

## 10. 附录

### 10.1 文件迁移总表

| 原路径(d:/mirror) | 新路径(d:/mirror/gimbal/) | 状态 |
|---|---|---|
| `prism/__init__.py` | `prism/__init__.py` | 改为 gimbal.prism |
| `prism/capture.py` | `capture/proxy.py` | 改名 |
| `prism/recorder.py` | `capture/{recorder.py,bus.py}` | 拆分 |
| `prism/convert.py` | `prism/convert.py` | 路径变 |
| `prism/builder.py` | `prism/builder.py` | 路径变 |
| `prism/doc2model.py` | `prism/doc2model.py` | 路径变 |
| `prism/server.py` | `prism/server.py` | 路径变 |
| `prism/cli.py` | `cli/capture.py` + `cli/prism.py` | 拆分 |
| `prism/ui_cli.py` | `cli/prism.py` | 改名 |
| `prism/ai/*` | — | **删除**(v0 不实现 AI) |
| `prism/static/chat.js` | — | **删除** |
| `prism/static/ai-settings.js` | — | **删除** |
| `prism/static/*` (其余) | `prism/static/*` | 路径变(沿用 D:/M/ModelRegistry 基线) |
| `schema/__init__.py` | `schema/__init__.py` | 路径变 |
| `schema/*.py` | `schema/*.py` | 路径变 |
| `ModelRegistry/*.py` | `contracts/*.py` | 改名 + 路径变 |
| — | `cli/app.py` | 新增(顶层 typer,**不注册** gimbal run 子命令) |
| — | `prism/state.py` | 新增(sessions / capture reader / watcher) |
| — | `prism/render/` | 新增(schema + ModelRegistry → ui_spec) |

### 10.2 命令对照表

| 旧命令 | 新命令 |
|---|---|
| `python -m prism.cli capture --filter /api/ -o f.ndjson -p 8080` | `gimbal capture start --session X --filter /api/` |
| `python -m prism.cli convert f.ndjson` | (删除,改用 `gimbal prism start` UI) |
| `python -m prism.cli ui serve --web 8765` | `gimbal prism start --port 8765` |
| `python -m prism.cli ui convert-scenario ...` | `gimbal prism start` UI 内操作 |
| `python -m prism.cli ui doc2model ...` | `gimbal prism doc2model` |
| `python -m prism.cli ui init` | `gimbal prism init` |
| `python -m prism.cli ui run x.yaml` | v0 不实现,无对应命令 |

### 10.3 配置项对照表

| 旧环境变量 | 新环境变量 | 说明 |
|---|---|---|
| `PRISM_WEB_PORT` | (无,改 `--port` 参数) | uvicorn 端口 |
| (无) | `GIMBAL_HOME` | 数据目录 |
| (无) | `GIMBAL_MODEL_REGISTRY_PATH` | ModelRegistry 兜底路径 |
| `ANTHROPIC_API_KEY` / `MINIMAX_API_KEY` | (删除,v0 不引入 AI) | — |

### 10.4 测试路径对照表

| 旧测试 | 新测试 |
|---|---|
| `tests/test_ai_*.py` | **删除**(v0 不实现 AI) |
| `tests/test_ai_frontend.py` | **删除** |
| (无) | `tests/test_capture_bus.py` |
| (无) | `tests/test_capture_archive.py` |
| (无) | `tests/test_state.py` |
| (无) | `tests/test_schema_meta.py` |
| (无) | `tests/test_schema_step.py` |
| (无) | `tests/test_schema_ui_spec.py` |
| (无) | `tests/test_contracts_init.py` |
| (无) | `tests/integration/test_e2e.py` |

---

## 11. 下游引用

- 总体架构 → [01-architecture.md](01-architecture.md)
- capture 模块 → [02-capture-module.md](02-capture-module.md)
- prism 配置器 → [03-prism-module.md](03-prism-module.md)
- schema SSOT → [04-schema-ssot.md](04-schema-ssot.md)
- ModelRegistry 引入 → [05-model-registry-integration.md](05-model-registry-integration.md)
- 文档索引 → [README.md](README.md)