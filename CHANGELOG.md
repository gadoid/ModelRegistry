# Changelog

## v0.5.9 (2026-06-30) — Step 导入去掉 method+path dedup

### 修复 (Fixed)

- **`_mergeCapturesIntoSteps` 不再按 `method|path` 去重**
  - 旧行为: NDJSON 45 行 capture (含 21 行重复 method+path) → 只生成 24 个 step
  - 新行为: 45 行 capture → 45 个 step (1:1)
  - 适用入口: NDJSON 文件选择器导入 / 拖拽导入 / WebSocket `capture` 自动注入 / 自动注入 toggle
  - 影响: 用户主动拖入 NDJSON 时, 历史接口重复调用 (如轮询 / 静态资源) 都会成为独立 step
- **WebSocket `hello` 帧 (重连) 避免重复 step**
  - 旧行为: WS 重连会重新灌入所有历史 captures 为 step (因去重失效会产生大量重复)
  - 新行为: WS hello + autoInjectToSteps=true 分支, 在 `_mergeCapturesIntoSteps` 之前先 `state.steps = []`, 整体替换
  - 仅 WS hello 帧清空 (单条 capture 帧不清 — 单条事件不会重复)

### 测试 (Tests)

- 新增 `tests/fixtures/dup_captures.ndjson` (5 行, 含重复 `GET /`)
- 新增 `tests/test_step_dedup_removed.py` (7 个测试: 函数体静态校验 + WS hello 清空 + server 端不去重)
- `tests/jsdom_harness.js` `import-ndjson` scenario 改用 dup fixture, 验证 5 → 5 step

### 不变 (Unchanged)

- server 端 `CaptureReader.append/read` (按行追加, 不去重)
- WebSocket `capture` 帧的 `state.captures` 层 `ts+method+path` 去重 (`app.js:1390`) — 它管的是 captures 数组不重复, 与 step 无关
- NDJSON → server inject → list 全链路

## v0.6.0 (2026-06-24) — Headless CLI (prism-core)

### 新增 (Added)

- **`gimbal.prism.core`** — 共享 pipeline + edit 原语 (NDJSON → Scenario YAML)
  - Pipeline: `parse_ndjson` / `load_config` / `render` / `write` / `inspect_ndjson` / `validate_config` / `ndjson_to_step_fragments`
  - Edit: `load_scenario` / `save_scenario` / `validate_scenario` / `explain_scenario` / `get_meta` / `set_meta` / `list_users` / `add_user` / `remove_user` / `list_resources` / `add_resource` / `remove_resource` / `get_config_section` / `set_config_section`

- **`gimbal prism` 新增 9 个子命令** (web `prism start` 不动):
  - Pipeline: `convert` / `inspect` / `validate` / `to-steps` / `explain`
  - Edit (按 section): `meta` / `user` / `resource` / `config`

- **Parity canary** (`tests/test_prism_core_builder_parity.py`) — web (`builder.build_scenario`) 与 CLI (`core.convert_ndjson_to_scenario`) 输出 byte-identical, CI 必跑

- **CLI config YAML schema** — snake_case (`time_policy`, `retry`), 与 web `DraftIn` 字段语义一致

### 变更 (Changed)

- `gimbal/prism/cli.py` (单文件) → `gimbal/prism/cli/` (子包), 包含 `start.py` + `_shared.py` + 7 subcommand 文件 + `edit/` 子目录

### 不变 (Unchanged)

- `gimbal/prism/server.py` (web 一行不动)
- `gimbal/prism/builder.py` (`core` 复用, 不重写)
- `gimbal/prism/convert.py` (`core` 复用, 不重写)
- 现有 237 个 web 测试保持绿

### 文件清单

```
NEW:
  gimbal/prism/core.py
  gimbal/prism/cli/{__init__,_shared,start,convert,inspect,validate,to_steps,explain}.py
  gimbal/prism/cli/edit/{__init__,meta,user,resource,config}.py
  tests/test_prism_core.py
  tests/test_prism_core_builder_parity.py
  tests/test_prism_cli_{convert,inspect,validate,to_steps,explain,meta,user,resource,config}.py
  tests/fixtures/sample_config.yaml
  tests/fixtures/minimal_captures.ndjson
```

---

## v0.5.5 (2026-06-23) — Step 分页 + 空状态文件选择器

### 新增 (Added)

- **Step 分页侧栏**：左侧垂直 1-10 / 11-20 / 21-30 索引，sticky 滚动；右侧 10 个 step 的横向 tag 流 (method + path)
- **空状态文件选择器**：`#step-empty` 框可点击 / Enter / Space → 弹出原生文件选择器；拖拽 `.ndjson` 到 step 区域 / 空状态框也触发导入
- **单展开手风琴**：点击 tag → 下方展开完整 step 编辑（API/Request/Strategy 三子 tab）；再点同 tag 收起；点别 tag 自动收起前一个
- **tag 删除按钮 + 拖拽重排**：hover tag 出现 ×；拖 tag 在当前页 10 个内重排（跨页守卫）
- **`state.currentPage` / `state.expandedStepSid` / `PAGE_SIZE = 10`** 新 state 字段 + 派生原语 (`_syncStepPagination` / `_computePageRanges`)
- **`_importNdjsonFile`** 替代旧 `importFromFile`，加空文件早返

### 删除 (Removed)

- 「全部展开」/「全部折叠」按钮（单展开替代）
- 步骤导入行（输入框 + 按钮），改由空状态框触发
- 前端 `importFromPath` 函数（无新调用方；后端 `/api/captures/import-from-path` 端点保留向后兼容）
- `.json` 文件导入支持（v0.5.5 起只接受 `.ndjson`）

### 保留 (Retained for backward compat)

- `/api/captures/import-from-path` 后端端点（v0.5 历史已暴露）
- `state.expandedSteps` / `state.collapsedSteps` Set 字段（供 undo/redo 历史栈 serialize 形状兼容）
- 「实时捕获」面板（含「自动注入 step」toggle），行为不变

### 文件变更

- `gimbal/prism/static/app.js`: 拆 `renderSteps` → 3 个子渲染器 + 4 类交互绑定
- `gimbal/prism/static/index.html`: 删 import-row / expand-all / collapse-all；加 `<input type="file">`；改 `#step-empty`；包 `.step-layout`
- `gimbal/prism/static/style.css`: 追加 `.step-layout` / `.step-sidebar` / `.step-tag` 等 13 个新类（复用现有 CSS 变量，0 个新 token）
- `tests/test_frontend_v1.py`: 更新 step 工具栏 ID 断言
- `tests/test_step_pagination_state.py` (新): 8 个静态测试
- `tests/test_step_pagination_css.py` (新): 4 个 CSS 测试
- `tests/test_render_steps_refactor.py` (新): 3 个 refactor 测试
- `tests/test_tag_drag_delete.py` (新): 2 个 tag 交互测试
- `tests/test_step_import_ux.py` (新): 7 个 import UX 测试
- `tests/test_step_pagination.py` (新): 4 个 E2E 分页测试
- `tests/test_step_import_e2e.py` (新): 4 个 E2E 导入测试
- `tests/fixtures/sample_captures.ndjson` (新): 3 条 sample NDJSON
- `USER_MANUAL.md`: §5.2 表格 + §5.2.5 新章节
- `docs/superpowers/specs/2026-06-23-step-pagination-and-import-design.md` (新): 设计文档
- `docs/superpowers/plans/2026-06-23-step-pagination-and-import.md` (新): 实施计划

### E2E 验证

- 237 passed / 4 skipped (无回归; v0.5.8 基线 202 + 35 新增)
- HTTP-level: 25-step draft 持久化 / .ndjson 注入 / 草稿往返
- 手动 smoke: 见 plan Task 10 10 步验收清单

---

## v0.5.8 (2026-06-22) — meta.name 默认 "template"

### 变更 (Changed)

- **`DraftIn.name` 默认值** `""` → `"template"`
  - 新 session 草稿创建时即带此名, 提醒用户填真实名
  - 不影响已被保存的草稿 (草稿是已存在的 dict, 默认值只用于新建)

- **`SessionStore.get_or_create` 新 session 时填充 DraftIn 默认值**
  - 之前: 新 session `draft = {}` (空 dict, 前端 fields 全空)
  - 现在: 新 session `draft = DraftIn().model_dump()` (含 name="template", scenario_id="sc_new", module="default", priority=1, version="1.0.0" 等)
  - 避免新 session 在前端"空空如也", 用户无需手动填默认值

- **HTML `<input id="m-name" value="...">`** `"新用例"` → `"template"` (静态首屏默认值, 与 DraftIn 对齐)

### 文件变更

- `gimbal/prism/server.py`: `DraftIn.name = "template"`
- `gimbal/prism/state.py`: `SessionStore.get_or_create` 填 `DraftIn().model_dump()`
- `gimbal/prism/static/index.html`: m-name 默认值

### E2E 验证

- 新 session GET → `name = "template"`
- PUT 自定义 name 后 GET → 保持自定义 name
- 多 session 隔离 (改 A 不影响 B)
- 202 passed + 4 skipped (无回归)

---

## v0.5.7 (2026-06-22) — sid 切换按钮加"切换"文字

### 变更 (Changed)

- **Header `header-sid-switch` 按钮**: 之前只有 `→` 图标, 现在加 `切换` 文字 (`→ 切换`)
- CSS: `width: 26px` 固定 → `padding: 0 8px` 自适应, 加 `gap: 4px` 图标文字间距, font-size 13px → 11.5px

### 文件变更

- `gimbal/prism/static/index.html`: +1 行 (`<span class="btn-label">切换</span>`)
- `gimbal/prism/static/style.css`: +3 行 (-3, +6, 调整 .sid-switch 样式)

### 测试

- 202 passed + 4 skipped（无回归）

---

## v0.5.6 (2026-06-22) — 导航栏按钮加文字提示

### 变更 (Changed)

**Header 4 个图标按钮加文字**：

| 按钮 | 原 | 新 |
|---|---|---|
| undo | `←` 图标 | `← 撤销` |
| redo | `→` 图标 | `→ 重做` |
| help | `?` 图标 | `? 帮助` |
| captures-clear | `×` 图标 | `🗑 清空` (新增 trash 图标) |
| yaml-toggle | `👁 只读 YAML` (已有) | 保留 |

### CSS 调整

- `.topbar-btn`: padding 5px 8px → 10px, font-size 14px → 12px, 加 `gap: 5px` (图标与文字间距)
- `.topbar-btn .btn-label`: font-weight 500
- `.captures-clear`: 加 padding 1px 4px + border-radius 3px + hover 红色背景
- 响应式 (`max-width: 900px` / `768px`): 隐藏 `.btn-label` 只显示图标（窄屏不挤）

### 文件变更

- `gimbal/prism/static/index.html`: 4 按钮各加 `<span class="btn-label">`
- `gimbal/prism/static/style.css`: +12 行 (`.btn-label` 样式 + 响应式)

### 测试

- 202 passed + 4 skipped（无回归）

---

## v0.5.5 (2026-06-22) — 页面 sid 配置框

### 新增 (Added)

- **Header sid 输入框 + 切换按钮** (替换原只读 span)
  - 用户直接在页面改 sid，不用重新打开带 `?session=xxx` 的 URL
  - 输入框: 占位符 + 聚焦自动全选 + 失焦/Enter 触发切换
  - 切换按钮: `→` 图标, 也可按 Enter
  - 验证: sid 只能含字母数字 `.` `_` `-`
  - 切换流程: 关闭旧 WS → state.sessionId = 新值 → URL `?session=xxx` 更新 → loadDraft → 新 WS → renderAll
  - 切前有未保存修改会弹 confirm modal

### 文件变更

- `gimbal/prism/static/index.html`: +5 行 (input + button + 隐藏 span)
- `gimbal/prism/static/style.css`: +37 行 (.sid-input / .sid-switch 样式)
- `gimbal/prism/static/app.js`: +45 行 (detectSession 同步 + switchSession + Enter/click 绑定)

### E2E 验证

- WS sid 切换: `default` / `dev-1` / `dev-2` 都返回正确 hello
- 数据隔离: PUT dev-1 不影响 dev-2 草稿
- 测试 202 passed + 4 skipped

---

## v0.5.4 (2026-06-22) — 自定义轮询 + 自动注入开关

### 修复 (Fixed)

#### Bug D: PollingObserver 在 Windows 上 `on_modified` 触发的是目录而非文件

**问题**：v0.5.2 改造后用 `watchdog.observers.polling.PollingObserver(timeout=0.5)` 监听 NDJSON 文件。
在 Windows 上，`on_modified` 事件的 `src_path` 是**目录**而非具体文件。我们的过滤逻辑
`P(event.src_path) == self.path` 比较失败，事件被跳过。**结果：实时推送在 Windows 上完全失效**。

**修复**：放弃 watchdog，**自实现后台轮询线程**：
- daemon thread 每 0.2s 检查所有 watched 文件的 (mtime, size)
- size 变化 → 读新增内容（seek `_last_pos`）
- size 减小 → 文件被截断，重置 `_last_pos = 0`
- 100 sessions × 5/s = 500 stat/s, 开销可忽略
- 跨平台一致，Windows / POSIX 行为统一

### 新增 (Added)

- **「自动注入 step」开关** (captures 表格上方 toggle)
  - 默认关闭，保持 v0.5.3 行为
  - 勾选后，新 capture 自动 push 到 `state.steps` + 立即保存草稿
  - 关闭不影响已注入的 step（按 ts+method+path dedup）
  - 重新打开会立即灌入当前所有 captures（用 `_mergeCapturesIntoSteps` 已有 dedup）

### 文件变更

- `gimbal/prism/state.py`: 删 `Observer`/`PollingObserver` 依赖，加 `threading` + 自实现 `CaptureWatcher._poll_loop`
- `gimbal/prism/static/index.html`: +9 行 (`captures-toolbar` + `auto-inject-toggle`)
- `gimbal/prism/static/style.css`: +11 行 (`.captures-toolbar`)
- `gimbal/prism/static/app.js`: +30 行 (state.autoInjectToSteps + toggle handler + WS onmessage 注入逻辑)

### E2E 验证

- capture 写 → 0.5s 内 WS 收到 → 0.5s 内 step 列表更新（如果勾选）
- 测试 202 passed + 4 skipped（无回归）

---

## v0.5.3 (2026-06-22) — 前端 captures 实时列表

### 新增 (Added)

- **Step tab 上方实时 captures 列表**：4 列表格（METHOD pill / PATH / STATUS / 耗时）
  - 倒序显示（最新在上）
  - 自动追加新事件（WS push 即时刷新，无须手动导入）
  - 折叠/展开：`<details>` 默认展开
  - 列表上限 200 条（防止长会话内存爆炸）
  - 空态：「尚无捕获事件」
  - 顶栏 inline 计数：实时同步 `#captures-count-inline`

### 行为 (Behavior)

- **WS onmessage `hello` / `capture` 帧**：更新 `state.captures` + 调 `renderCaptures()` 刷新列表
- **导入完成（`_mergeCapturesIntoSteps`）**：列表同步刷新
- **清空 captures（`clear-captures` 按钮）**：列表同步清空
- **不变**：捕获不会自动合并到 step。用户必须手动点 Step tab 底部的「导入」按钮。

### 文件变更

- `gimbal/prism/static/index.html`: +17 行（`<details class="captures-panel">` + 4 列表格）
- `gimbal/prism/static/style.css`: +97 行（.captures-panel / .captures-table / 颜色 / 动画）
- `gimbal/prism/static/app.js`: +50 行（`renderCaptures` + 4 个接入点）

### 验证

- **E2E**：capture 写 5 条事件 → prism WS 收到 5 条推送，延迟 < 1s
- **测试**：202 passed + 4 skipped（无回归）
- 列表展示：METHOD pill 颜色化（GET 绿 / POST 紫 / PUT 黄 / DELETE 红），STATUS 按 2xx/3xx/4xx/5xx 上色

---

## v0.5.2 (2026-06-22) — capture-prism 数据流通 (Windows 修复)

### 修复 (Fixed)

#### Bug A: msvcrt.locking 是 mandatory lock, 锁住 NDJSON 后 prism 端读 PermissionError

**问题**：`capture` 进程用 `msvcrt.locking(fd, LK_NBLCK, 1)` 锁 NDJSON 文件第 0 字节。
Windows 的 `msvcrt.locking` 是 **mandatory lock** (Python 文档明确)，其他进程**任何**读该文件
都报 `PermissionError [Errno 13]`。`prism` 端 `CaptureReader.read()` / `CaptureWatcher` / WebSocket
全部读不到。

**修复**：去掉 msvcrt.locking，改用**哨兵文件** `{sid}.lock` (O_CREAT|O_EXCL) 做 session 互斥：
- capture 启动时创建哨兵 → 失败抛 `SessionLockedError`（另一 capture 在跑）
- capture 关闭时删除哨兵 + close fd
- NDJSON 文件本身**完全无锁**，prism 端可自由读
- 跨平台一致（POSIX 走 `os.open` + O_EXCL，行为统一）

#### Bug B: Windows watchdog Observer 延迟 ~21 秒，prism 端实时推送失效

**问题**：`gimbal/prism/state.py` 用 `Observer()` (ReadDirectoryChangesW) 监听 NDJSON 文件修改。
在 uvicorn 事件循环下，Windows 的 ReadDirectoryChangesW 事件被合并 + 延迟到 **20+ 秒**。
prism 端 WebSocket 收到 capture 事件延迟 20s+，实时捕获体验完全失效。

**修复**：改用 `watchdog.observers.polling.PollingObserver(timeout=0.5)`：
- 主动每 0.5s 轮询文件 mtime/size
- 延迟可控（0.5-1s）
- 跨平台一致（POSIX 也用 PollingObserver，避免 2 套行为）
- 性能开销：每秒 stat 一次 N 个文件，对 capture 场景可忽略

### 端到端验证

- capture 写 NDJSON → prism WS 收到 capture 事件延迟 < 1s
- 测试总数：194 → **202 passed** + 4 skipped（+8 bus_lock_semantics 新测试）
- 启动 capture + 启动 prism，浏览器代理开 / 操作 / 立即在 prism 看到 captures 实时增长

### 向后兼容

- 旧 `PathFilter` + `LockBackend` 接口保留（被 test 引用）
- 旧客户端只发 `step_ids` 仍能 work
- `msvcrt.locking` 行为不再依赖

---

## v0.5.1 (2026-06-21) — Step 自定义字段持久化 (P0 修复)

### 修复 (Fixed) — 审计报告 §3 三个 P0 Gap

#### Gap #1 + #2: Step 自定义字段全部丢失

**问题**：前端 `serializeDraft` 只发 `step_ids: [String(0), String(1), ...]`（基于 `state.captures` 索引），
完全不发送 `state.steps[i]` 里的 `api_override` / `req_override` / `assertions` / `extracts` / `assigns` / `key_hint`。
后端 `DraftIn` 也没有 `steps` 字段，无法接收。

**后果**：用户在 step 卡片里改的 method / path / 加的 assertion / 命名都**保存即丢失**。

**修复**：
- `gimbal/prism/builder.py`: `StepDraft` 新增 `api_override: Optional[dict]` + `req_override: Optional[dict]`
- `gimbal/prism/builder.py`: `_build_step` 优先用 `api_override` 覆盖 method / path / service
- `gimbal/prism/builder.py`: `_build_step` 优先用 `req_override` 替换 request.params / body
- `gimbal/prism/server.py`: `DraftIn` 新增 `steps: list[dict[str, Any]]` 字段
- `gimbal/prism/server.py`: `_draft_from_in` 优先用 `payload.steps` 直接构造 `StepDraft`（含完整自定义）
- `gimbal/prism/server.py`: 保留 `step_ids` 字段作为 fallback（旧客户端兼容）
- `gimbal/prism/static/app.js`: `serializeDraft` 改发完整 `state.steps`（剥离 `__sid` 等 UI 本地字段）

#### Gap #3: `get_draft` 永远返回空 `steps`

**问题**：`_ensure_session` 用 `DraftIn().model_dump()` 初始化空 session，
旧 `step_ids` 路径不存 step 自定义，刷新后 steps 永远是空的。

**修复**：现在 PUT 落 `steps` 完整对象，GET 直接返回（无需特殊处理）。

### 验证

- **新测试** `tests/test_step_persistence.py` × 16 个：覆盖 StepDraft 新字段 / DraftIn 新字段 / `_draft_from_in` 双路径 / `build_scenario` 5 个策略应用 / round-trip
- **测试总数**: 178 → **194 passed** + 4 skipped
- **端到端**: PUT 含完整自定义的 steps → GET 完整恢复 → POST /yaml 输出含 `api.service=auth-svc, api.method=PUT, request.body.user=admin, strategy.extract target=auth_token, key=1-login_step` 等

### 向后兼容

- 旧客户端只发 `step_ids` 仍能工作（fallback 到 captures 文件索引）
- 但旧客户端**不携带** step 自定义 — 升级前端后才能编辑 step 字段

---

## v0.5 (2026-06-21) — 前端 v1.0.0 (PR1SM 视觉规范)

### 变更 (Changed)

- **`gimbal/prism/static/style.css`**: 90 行 → 862 行，引入完整设计系统（CSS 变量 / 卡片阴影 / tabler-icons / 模态 / Toast / 拖拽 / 响应式 / Reduced Motion）
- **`gimbal/prism/static/index.html`**: 64 行 → 320 行，顶部固定栏 + tab 切换 + 卡片堆叠 + 多模态（YAML 预览 / Help / 策略编辑）
- **`gimbal/prism/static/app.js`**: 18KB → 64KB，重写为 state 驱动 + 拖拽重排 + undo/redo + 快捷键 + 密码脱敏

### 新增 (Added)

- **`/ws/captures?sid=<sid>` WebSocket 端点**（gimbal/prism/server.py）: 替代 v0 的 SSE `/api/captures/stream`
  - 协议：连上后发 `{"type":"hello","count":N,"events":[...]}`，每条新事件发 `{"type":"capture","data":...}`
  - 兼容 PR1SM app.js 的 WebSocket 客户端

### 删除 (Removed)

- **前端声明式 schema 渲染**（v0 的 `/api/schema/ui-spec` 端点 + app.js 7-widget 派发）
  - 字段 ID 全部硬编码到 HTML（`#m-name` / `#m-desc` / `#m-tags-wrap` / ...）
  - 性能更好（无 schema 反射），但失去 schema 改 → UI 自动跟随的能力

### 统计 (v0.5)

- **测试**: 165 → 178 passed (+13 替换 v0 旧声明式测试)
- **前端体积**: 18KB+5KB+2KB (25KB) → 64KB+14KB+30KB (108KB) — 4.3×，换视觉规范
- **零新增依赖**: tabler-icons 走 CDN (`cdnjs.cloudflare.com`)，未引入 npm 资产

### v0.5 不做 (YAGNI)

- ❌ 视觉主题切换（暗色模式）
- ❌ 多语言 i18n（保留中文 UI）
- ❌ 前端组件库拆分（保持单文件）
- ❌ 移动端深度优化（仅基础响应式）

---

## v0.4 (2026-06-21) — Capture Filter Strategy

### 新增 (Added)

- **`gimbal/capture/strategy.py`**: Pydantic 数据类 `FilterMode` / `Rule` / `Profile` / `StrategyFile`, 编译产物 `CompiledRule` (frozen dataclass) + `CompiledMatcher` (含 `match_with_reason` 调试接口)
- **`gimbal/capture/loader.py`**: 端到端 `build_matcher()` 入口 + `discover_filter_file()` / `resolve_includes()` (环检测) / `select_profile()` / `append_cli_rules()` / `compile_matcher()`
- **CLI 4 个新参数**: `--filter-file` / `--filter-profile` / `--filter-mode` / `--strict-files-only`
- **Rule 字段**: `host` / `host_glob` / `host_regex` / `path` / `path_glob` / `path_regex` / `methods` (HTTP method 自动大写)
- **include 复用**: 一个文件可 `includes: [...]` 组合多个 profiles, 同名 profile 后者覆盖前者 + 警告
- **配置错误退出码 5**: YAML 错 / 正则编译错 / include 循环 / profile 找不到 / 空规则 全部 → 父进程红字退出

### 变更 (Changed)

- **`gimbal/capture/proxy.py`**: `CaptureAddon.__init__` 接受 `CompiledMatcher` 替代 `PathFilter`
- **`gimbal/capture/cli.py`**: 父进程提前 `build_matcher()` 校验, addon 脚本注入 `build_matcher` 调用
- **`gimbal/capture/filter.py`**: `PathFilter` 兼容层保留 (旧 `--filter CSV` 行为完全不变)

### 修复 (Fixed)

- path 前缀匹配的边界严格化: 编译期正则预编译, 运行期只查 `re.Pattern.search()`, 避免热路径字符串拼接

### 统计 (v0.4)

- **测试**: 84 passed → 165 passed (+81), 4 skipped
- **新文件 (v0.4)**: 2 个核心模块 (`strategy.py` / `loader.py`) + 9 个测试文件
- **零新增依赖**: 用已装的 `PyYAML>=6.0`, 正则走标准库 `re` 和 `fnmatch`

### v0.4 不做 (YAGNI)

- ❌ header / cookie 黑名单
- ❌ 用户自定义插件 / Strategy 类
- ❌ JSON / TOML 配置（YAML 已够）
- ❌ 远程配置中心（仅本地文件）
- ❌ 热重载 (mitmdump 子进程内 build 一次即可)
- ❌ 跨平台 path glob 差异处理

---

## v0.3 (2026-06-18) — 删旧 `prism/` 顶层包 + 收尾

### 删除 (Removed)

- 整个 `prism/` 顶层包 (~30 文件, 含 14 `_schema/`, 8 `tests/`, 8 业务文件)
  - `from prism.builder` → `from gimbal.prism.builder`
  - `from prism.recorder` → `from gimbal.capture.recorder`
  - `from prism.server:app` → `from gimbal.prism.server:app`
  - `from prism._schema import ...` → `from gimbal.schema import ...`
  - `from prism._model_registry import ...` → `from gimbal.contracts import ...`

### 统计 (v0.3)

- **测试**: 84 passed, 4 skipped (含 1 个 contracts unavailable, 1 个 doc2model unavailable, 2 个 v0 historical)
- **新文件 (v0.2-v0.3)**: 4 个 schema annotation (TimePolicy/RetryPolicy/AuthSession) + 3 个测试文件 + 1 个 doc2model 副本
- **前端 v0.2.5**: 4-Tab 声明式渲染 (基于 `/api/schema/ui-spec`), 7 widget 派发

---

## v0.2 (2026-06-18) — UI 注解全覆盖 + 前端声明式 + 文档/迁移

### 新增 (Added)

- **v0.2.1 迁移 `prism/tests/` → 顶层 `tests/`**: 6 测试文件改 import 路径, 修 Windows `monkeypatch.chdir` + watchdog Observer 句柄泄漏
- **v0.2.2 迁移 `prism/doc2model.py` → `gimbal.prism.doc2model.py`**: 改用 `gimbal.contracts`, `--into-registry` 在 ModelRegistry 不可用时退出码 3 + 友好提示
- **v0.2.3 补 Resource/Step UI 注解**: Mock.kind select widget (mock/mock_ref/file/file_ref), Mock.image input, Mock.portMapping kv-list, File.kind/path; Step.api/request/strategy/key (key readonly)
- **v0.2.4 补 Config 子结构 UI 注解**: TimePolicy.kind select (record/timeout) + show_if 联动 seconds, RetryPolicy 3 字段 show_if 联动, AuthSession 7 字段 (password widget, token readonly)
- **v0.2.5 前端声明式 4-Tab 渲染**: app.js 重写, 7 widget 派发 (input/textarea/select/number/toggle/tags/kv-list), 自动保存 (debounce 500ms), show_if 联动, options_from 解析

### 删除 (Removed)

- `prism/_model_registry/` (Phase 3 末): 改用 `gimbal.contracts`

### 统计 (v0.2)

- **测试**: 105 passed → 113 passed (8 套件)
- **覆盖度**: `/api/schema/ui-spec` 输出 5 个 group (meta/config/timePolicy/retry/users) 共 30+ 字段

---

## v0.1.0 (2026-06-18) — gimbal 平台首发

### 新增 (Added)

- **`gimbal/` 顶层包**: 两个独立子模块,console_scripts 入口 `gimbal`
- **`gimbal capture`**: mitmproxy 代理 + FileBus 文件锁 (POSIX `fcntl` / Windows `msvcrt`) + NDJSON 落盘 + 归档策略
- **`gimbal prism`**: FastAPI 配置器 + `lifespan` 上下文 (替代模块级单例) + SSE (`/api/captures/stream`) 替代 WebSocket
- **`gimbal schema/`**: 14 个 Pydantic 文件从 `prism/_schema/` 迁出, 全部加 `model_config = ConfigDict(extra="forbid")`
- **`Field(..., ui=...)` 包装**: UI 元数据走 `json_schema_extra`, 不进入 `model_dump`
- **`/api/schema/ui-spec` 端点**: schema 反射为前端 JSON (SSOT)
- **`/api/schema/dot-paths` 端点**: 合法 dot-path 白名单
- **`/api/registry/ui-spec` 端点**: ModelRegistry → UI spec (下拉/选项/自动补全)
- **`gimbal contracts/`**: ModelRegistry 引入层 (双路径加载: env var / 已装)
- **前端 `app.js`**: WebSocket → EventSource, `?sid=` 多 session 化
- **声明式 4-Tab UI**: 元信息 / 配置 / 资源 / Steps

### 修复 (Fixed)

- 痛点 #5 (Fix #5): `Meta.name` 必填校验, 空字符串/纯空白拒绝
- 痛点 #6 (Fix #6): `_loop is None` 时 `_broadcast` 发 warning 而非静默 return
- 痛点 #7 (Fix #7): CLI 子命令显式注册, 避免 `sys.modules['__main__']` hack
- 痛点 #8 (Fix #8): `Step.key` 字段 (替代 `setattr` 黑魔法)
- 痛点 #9 (Fix #9): 草稿编辑产生深拷贝, undo/redo 隔离
- 痛点 #10 (Fix #10): `/api/captures/import-from-path` CWD 沙箱
- 痛点 #11 (v0 改造): FastAPI lifespan + `app.state` 替代模块级单例 (recorder / ws_clients / _loop / sessions 全删)
- 痛点 #12: 资源 kind 用 `dispatch` dict 替代 if/elif 串行
- 痛点 #13: 默认 assertion name 用 `assert_status_{idx}` (替代 `hash(path)` 不可复现)
- 痛点 #14: schema 注解驱动的声明式前端

### 变更 (Changed)

- **路径迁移**: `prism/_schema/*.py` → `gimbal/schema/*.py` (全部)
- **路径迁移**: `prism/builder.py` → `gimbal/prism/builder.py` (痛点 12/13 改造)
- **路径迁移**: `prism/server.py` → `gimbal/prism/server.py` (痛点 11 改造)
- **路径迁移**: `prism/static/*` → `gimbal/prism/static/*` (SSE + sid 化)
- **依赖清理**: 删除 `prism/ai/` (AI 整体未实现)
- **依赖清理**: 删除 `prism/_model_registry/` (改用 `gimbal.contracts`)

### 弃用 (Deprecated)

- 整个 `prism/` 顶层包, 标 `DeprecationWarning`, **v0.3 删除**

### v0 不做 (Explicit Non-Goals)

- ❌ `gimbal run` 执行引擎
- ❌ AI 助手 (`gimbal/prism/ai/`, `anthropic`, `httpx`)
- ❌ 多 worker uvicorn (`--workers 1` 强制)
- ❌ `config.yaml` 加载 (全部走 CLI 参数)
- ❌ `ai/config.json`, `ai/history/`, `*.lastrun.json` (无 AI 无 lastrun)
- ❌ 完整 E2E 测试 (只补核心路径)
- ❌ 前端视觉重设计 (沿用 M1.4 极简风格, M2.4 声明式渲染)

### 统计

- **代码**: 25 个新文件, 旧 `prism/` 改 import 6 处, `prism/_model_registry/` 删 2 文件
- **测试**: 64 个测试 (含 30 旧基线), 1 个 v0.2 待修 xfail, 1 个 v0.2 已知 skip
- **依赖**: 新增 `sse-starlette>=2.1` + `watchdog>=4.0`; 不引入 `anthropic` / `httpx`
- **设计文档**: `gimbal-design/` 6 份归档保留
