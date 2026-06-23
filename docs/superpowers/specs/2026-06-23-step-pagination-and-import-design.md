# Step 分页 + 空状态文件选择器设计

> **日期**：2026-06-23
> **作者**：gimbal team
> **范围**：`gimbal/prism/static/{app.js, index.html, style.css}` 三个前端文件
> **状态**：设计中（待用户审阅）
> **版本**：v0.5.5 候选

---

## 0. 背景与目标

**现状**（v0.5.3）：
- Steps Tab 顶部是「实时捕获」面板（WS 推送的内存 captures 列表）。
- 下方是步骤工具栏（全部展开 / 全部折叠 / 新增 Step）。
- 步骤列表是**垂直堆叠的全功能卡片**（`#step-list` 内每张 `.step-card` 占据完整宽度）。
- 步骤空状态（`#step-empty`）是被动文字提示：「尚无 Step — 导入 captures 或点击「+ 新增 Step」开始」。
- 步骤导入行（`.import-row`）包含一个 `<input id="import-path">` 文本框 + 「导入」按钮，限制沙箱路径（CWD 内），并支持拖入 `.ndjson` / `.json` 文件。

**痛点**（用户反馈）：
1. 导入交互有「按钮+输入框」两层认知负担 — 既然主要场景是从本地文件加载，不如直接弹出文件选择器。
2. 步骤数量大时（典型 50+ steps），垂直堆叠的全功能卡片让用户在滚动时丢失全局视野 — 看不到"我已经到第几个了"、"上下相邻步骤是哪些"。
3. 没有快速分页手段 — 想跳到 step 23 必须先滚到那。

**目标**（本期实现）：
1. **空状态框可点击**：点击 `#step-empty` 弹出原生文件选择器，限定 `.ndjson` 后缀。删除 `import-row` 输入框与按钮。
2. **分页侧栏 + 标签流**：左侧垂直侧栏按 10 个一组显示页码（`1-10`、`11-20`、`21-30` ...），右侧是当前页 10 个 step 的「标签」风格横向流（method pill + path）。
3. **单展开手风琴**：点击一个 tag → 下方展开完整编辑面板（沿用现有 `.step-card` 的 API/Request/Strategy 子 tab 结构）。再点同一个 tag 收起；点别的 tag 自动收起前一个。

**显式不做**（YAGNI）：
- 不引入新 CSS 变量或字体，复用现有 token。
- 不分页「实时捕获」面板（它走 WebSocket 推送，每次 200 条上限内不需要分页）。
- 不重构 `importFromFile` / `_mergeCapturesIntoSteps` 等已有函数，保留其行为。
- 不删除 `/api/captures/import-from-path` 后端端点（向后兼容），仅前端 `importFromPath` 不再被 UI 调用。
- 不支持跨页拖拽（拖一个 tag 到另一页的 tag 区域）— 拖拽仅在当前页内有效，越界时由 `_syncStepPagination` 校正。

---

## 1. 架构与组件

### 1.1 新增 state 字段

`gimbal/prism/static/app.js` 的 `state = {}` 内追加：

```javascript
state.currentPage = 1;            // 1-based 页码
state.expandedStepSid = null;     // 当前展开的 step.__sid; 取代 expandedSteps Set 语义
const PAGE_SIZE = 10;             // 模块级常量, 写在 state 定义之后
```

> **注意**：保留 `state.expandedSteps` 与 `state.collapsedSteps` 两个 Set 字段（既有代码 / undo 历史栈 / serialize 路径不破坏）。`expandedStepSid` 是新增字段，渲染逻辑只读它；老的 Set 字段保留作为向后兼容，但本期不被新逻辑写。

### 1.2 渲染函数拆分

`gimbal/prism/static/app.js` 的 `// ── Steps ──` 区域重写：

```
PAGE_SIZE              = 10
_syncStepPagination()  // state.steps 长度变化后调用, 越界校正
_computePageRanges()   // 派生: [{label: '1-10', start: 0, end: 10}, ...]
renderStepSidebar()    // 渲染左侧垂直侧栏
renderStepTags()       // 渲染当前页 10 个 tag
renderStepDetail()     // 渲染展开面板 (复用现有 step-card 内部)
renderSteps()          // 总入口, 顺序调用以上
```

### 1.3 HTML 改动（`gimbal/prism/static/index.html` Steps `<section>`）

**删除**：
```html
<button id="expand-all">全部展开</button>
<button id="collapse-all">全部折叠</button>
<div class="import-row">
  <input id="import-path" placeholder="captures.ndjson 路径 或拖入 .ndjson 文件" />
  <button id="import-btn">导入</button>
</div>
```

**新增**：
```html
<input type="file" id="ndjson-file-input" accept=".ndjson,application/x-ndjson"
       hidden aria-hidden="true" />
```

**修改**：
```html
<div id="step-empty" class="empty-state clickable"
     role="button" tabindex="0" aria-label="点击导入 .ndjson 文件">
  尚无 Step — 点击导入 .ndjson
  <small>(拖入 .ndjson 也可)</small>
</div>
```

**修改**：`#step-list` 内部结构：
```html
<div id="step-list" class="step-layout">
  <nav id="step-sidebar" class="step-sidebar" aria-label="Step 分页"></nav>
  <div class="step-main">
    <div id="step-tags" class="step-tags" role="list"></div>
    <div id="step-detail" class="step-detail" hidden></div>
  </div>
</div>
```

### 1.4 工具栏调整

保留：
- `<span class="grow"></span>` （占位）
- `<button id="add-step">+ 新增 Step</button>`

删除：展开 / 折叠按钮（点击 tag 本身即展开 / 收起）。

---

## 2. UI 样式（与现有风格一致）

追加到 `gimbal/prism/static/style.css` 末尾。**不引入新 CSS 变量**，全部复用现有 token。

```css
/* ───────── Step Sidebar + Tag Layout ───────── */
.step-layout {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 14px;
  align-items: start;
}

.step-sidebar {
  display: flex; flex-direction: column; gap: 4px;
  position: sticky; top: 12px;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
  padding: 6px 4px;
  background: rgba(255,255,255,0.4);
  border: .5px solid var(--color-border-tertiary);
  border-radius: 9px;
  backdrop-filter: blur(3px);
}

.step-sidebar .page-tab {
  display: block; width: 100%;
  padding: 6px 10px; border: 0;
  background: transparent;
  color: var(--color-text-secondary);
  font-family: var(--font-mono); font-size: 11.5px;
  border-radius: 6px; cursor: pointer;
  text-align: left;
  transition: background .15s, color .15s;
}
.step-sidebar .page-tab:hover { background: var(--accent-soft); color: var(--accent); }
.step-sidebar .page-tab.active {
  background: var(--accent); color: #fff;
}
.step-sidebar .page-tab .page-count {
  display: block; font-size: 9.5px; opacity: .8;
  font-family: var(--font-mono);
}

.step-main { min-width: 0; }
.step-tags {
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 6px 0 12px;
  min-height: 36px;
}
.step-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px;
  background: rgba(255,255,255,0.6);
  border: .5px solid var(--color-border-tertiary);
  border-radius: 14px;
  font-size: 12px; cursor: pointer;
  user-select: none;
  max-width: 280px;
  transition: background .15s, border-color .15s, transform .1s;
}
.step-tag:hover { background: rgba(255,255,255,0.85); border-color: var(--accent-soft-border); }
.step-tag.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}
.step-tag.dragging { opacity: .5; }
.step-tag.drag-over { border-style: dashed; border-color: var(--accent); background: var(--accent-soft); }
.step-tag .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-tag .del {
  background: transparent; border: 0; color: var(--red);
  cursor: pointer; font-size: 13px; padding: 0 2px;
  opacity: 0; transition: opacity .15s;
}
.step-tag:hover .del { opacity: 1; }

.step-detail {
  margin-top: 8px;
}

.step-main.prism-drop-target,
#step-empty.prism-drop-target {
  outline: 2px dashed var(--accent);
  outline-offset: -4px;
  border-radius: 9px;
  background: var(--accent-soft);
}

#step-empty.clickable {
  cursor: pointer;
  transition: background .15s, transform .1s;
}
#step-empty.clickable:hover {
  background: var(--accent-soft);
  transform: translateY(-1px);
}
#step-empty small { display: block; margin-top: 4px; opacity: .75; font-size: 11.5px; }
```

**复用清单**：
- `.method-pill` — tag 内的 method 显示（既有 GET/POST/PUT/DELETE/PATCH 颜色）
- `.step-card` / `.shdr` / `.sbody` / `.sub-tabs` — 展开面板的内部结构原样保留
- `--accent` / `--accent-soft` / `--accent-soft-border` / `--red` / `--color-border-tertiary` / `--font-mono`
- tabler-icons CDN — 不引入新图标

---

## 3. 数据流

### 3.1 派生量（每次 render 重算）

```javascript
const hasSteps   = state.steps.length > 0;
const pageCount  = Math.max(1, Math.ceil(state.steps.length / PAGE_SIZE));
const pageRanges = []; // [{label: '1-10', start: 0, end: 10}, ...]
for (let p = 0; p < pageCount; p++) {
  const start = p * PAGE_SIZE;
  const end   = Math.min(start + PAGE_SIZE, state.steps.length);
  const from  = start + 1, to = end;
  pageRanges.push({ label: `${from}-${to}`, start, end });
}
const currentRange = pageRanges[state.currentPage - 1] || pageRanges[0];
const pageSteps    = hasSteps ? state.steps.slice(currentRange.start, currentRange.end) : [];
const expandedStep = state.expandedStepSid
  ? state.steps.find(s => s.__sid === state.expandedStepSid)
  : null;
```

**渲染门控**：
- `hasSteps === false` 时：`renderStepSidebar` 渲染空容器（`hidden`），`renderStepTags` / `renderStepDetail` 同样 `hidden`。整个 `.step-layout` 由 `syncStepEmpty` 切换：length=0 时只显示 `#step-empty`，不显示侧栏 / tag / detail。
- `hasSteps === true && pageCount === 1` 时：侧栏只显示一个「1-10」tab（仍可见，但占用空间小）。

### 3.2 操作矩阵

| 操作 | 触发器 | state 变更 | 渲染动作 | 副作用 |
|---|---|---|---|---|
| 点击空状态 | `#step-empty.clickable` click / Enter / Space | 无 | `$('ndjson-file-input').click()` | 选文件后走 §3.3 |
| 拖入 .ndjson 到空状态 / step-main | drop 事件 | (后续 merge) | (后续) | 走 §3.3 |
| 点击侧栏页码 `k` | `.page-tab` click | `state.currentPage = clamp(k, 1, pageCount)` | `renderSteps()` | 无 |
| 点击 step tag | `.step-tag` click | `state.expandedStepSid = (旧 === 新 ? null : 新)` | `renderSteps()` | 无 |
| 拖 tag 重排 | dragstart / dragover / drop | `state.steps.splice(from, 1); state.steps.splice(to, 0, moved)` | `renderSteps()` | `pushHistory()` + `scheduleSave()` + `_syncStepPagination()` |
| 点击 tag 上删除 | `.step-tag .del` click | 弹 confirmModal → `state.steps.splice(i, 1)` | `renderSteps()` | `pushHistory()` + `scheduleSave()` + `_syncStepPagination()` |
| 新增 step | `#add-step` click | `state.steps.push(ns); state.expandedStepSid = ns.__sid; state.currentPage = pageCount` | `renderSteps()` 滚到底部 | `pushHistory()` + `scheduleSave()` |
| 编辑 detail 字段 | `[data-sf]` input | 更新 `step.api / step.req / step.key_hint` | 局部更新当前 detail 卡片 | `scheduleSave()` |
| 删除 detail 中的 step | `.step-card .shdr .del` click | 弹 confirmModal → `state.steps.splice(i, 1)` | `renderSteps()` | `pushHistory()` + `scheduleSave()` + `_syncStepPagination()` |
| 自动注入 step (captures 面板 toggle) | `#auto-inject-toggle` 变化 | `_mergeCapturesIntoSteps()` append | `renderSteps()` 跳到新 step 所在页 | `pushHistory()` |

### 3.3 选中 .ndjson 文件的导入流程

```javascript
$('ndjson-file-input').addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  e.target.value = '';                              // 允许重选同一文件
  if (!file) return;
  if (!/\.ndjson$/i.test(file.name)) {
    toast('请选择 .ndjson 文件', 'error');
    return;
  }
  await _importNdjsonFile(file);                    // 复用现有 importFromFile
});

// 拖拽导入: 绑定到 #step-empty 和 .step-main
['dragenter','dragover'].forEach(evt => { /* 加 .prism-drop-target */ });
['dragleave','drop'].forEach(evt => { /* 去 .prism-drop-target */ });

#step-empty.addEventListener('drop', handleNdjsonDrop);
.step-main.addEventListener('drop', handleNdjsonDrop);

function handleNdjsonDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  if (!/\.ndjson$/i.test(file.name)) {
    toast('请拖入 .ndjson 文件', 'error');
    return;
  }
  _importNdjsonFile(file);
}
```

### 3.4 `_syncStepPagination()`

```javascript
function _syncStepPagination() {
  const pageCount = Math.max(1, Math.ceil(state.steps.length / PAGE_SIZE));
  if (state.currentPage > pageCount) state.currentPage = pageCount;
  if (state.currentPage < 1) state.currentPage = 1;
  if (state.expandedStepSid &&
      !state.steps.some(s => s.__sid === state.expandedStepSid)) {
    state.expandedStepSid = null;
  }
}
```

### 3.5 渲染顺序

```
renderSteps():
  _syncStepPagination()
  renderStepSidebar()    // 左侧 1-10, 11-20, ...
  renderStepTags()       // 当前页 10 个 tag
  renderStepDetail()     // 若 expandedStep, 渲染完整 step-card
  syncStepEmpty()        // 0 step 时显示 #step-empty
```

---

## 4. 错误处理

| 场景 | 用户表现 | 内部处理 |
|---|---|---|
| 选的文件不是 .ndjson (e.g. .json, .txt) | Toast: "请选择 .ndjson 文件" (error, 3s) | 不发起任何 fetch;`#ndjson-file-input.value` 已清空, 允许重选 |
| 选的文件是空文件 | Toast: "文件为空, 无可导入" (info) | `_importNdjsonFile` 内判断 `text === ''` 后提前返回 |
| 文件某行 JSON 解析失败 | Toast: "导入完成: server 收到 N 条, 新增 M 个 Step, 跳过 K 条无效" (info) | 沿用现有 `importFromFile` 的容错 (单行 try/catch 吞错) |
| 文件 IO 错误 (权限 / 不存在) | Toast: "读取失败: <err.message>" (error, 5s) | `await file.text()` 抛 → 捕获后 toast |
| 拖入非 .ndjson 文件 | Toast: "请拖入 .ndjson 文件" (error) | drop handler 内 `if (!/\.ndjson$/i.test(file.name))` 早返 |
| 拖入多个文件 | 只处理第一个 | `e.dataTransfer.files[0]`, 其余忽略 (不提示) |
| 删除最后一个 step | `_syncStepPagination` 把 `expandedStepSid` 置 null; 若 `state.steps.length === 0` 则 `currentPage` 重置 1; 若 `currentPage` 越界则截到 `pageCount` | 渲染 detail 区 `hidden=true`; `syncStepEmpty` 显示空状态 |
| `currentPage` 越界 (拖拽 / 删除导致) | 跳到最后一页有效页 | `_syncStepPagination` 校正 |
| tag 上的删除与 detail 内的删除同时点 | 同 `state.steps.splice(i, 1)`, 幂等 | detail 删 → renderSteps 会重建 tag; tag 删时 detail 同步消失 |
| 用户在 `#step-empty` 上按 Enter/Space | 同 click → 触发文件选择器 | keydown 处理 `e.key === 'Enter' \|\| e.key === ' '` |
| `state.steps` 长度 ≥ 1 但 `expandedStepSid === null` | detail 区域 `hidden`, tag 区域下方 8px 间距 | `renderStepDetail` 早返 |

**关键不变式**（在 renderSteps 入口 assert, 测试时验证）：

```
1. 1 ≤ state.currentPage ≤ pageCount                           (页码有效)
2. 0 ≤ pageRanges[currentPage-1].start ≤ state.steps.length   (切片起点有效)
3. pageSteps.length ≤ PAGE_SIZE                                (一页至多 10)
4. state.expandedStepSid === null
   || state.expandedStepSid ∈ state.steps.map(s => s.__sid)   (展开目标存在)
```

---

## 5. 测试策略

### 5.1 前端 / E2E

- **不引入新测试框架**。沿用现有 `pytest` + `requests` 模式。
- **新增** `tests/test_step_pagination.py` — 启动 prism, 通过 HTTP (`PUT /api/draft/{sid}`) 塞 25 个 step 进 state, 然后用 Playwright (`sync_playwright`) 加载 prism HTML, DOM 查询断言:
  - 侧栏有 `1-10`, `11-20`, `21-30` 三项
  - 当前页 `1-10` 高亮 (`.active` 类)
  - 切到 `11-20` 后 `#step-tags` 内 step 与 `state.steps[10:20]` 一一对应
  - 删除最后 5 个 step 后 `currentPage` 自动回 1
  - `expandedStepSid` 在 step 被删除后被置 null
- **新增** `tests/test_step_import_e2e.py` — 提供 .ndjson fixture, 模拟点击 `#step-empty` 触发文件选择器 (通过直接调用 `_importNdjsonFile`), 断言 steps 被 merge
- **现有** `test_frontend_declarative.py` — 不应回归 (4-Tab 渲染逻辑未变)
- **现有** `test_prism_server.py` — `/api/captures/inject` 路径不变

### 5.2 视觉回归

- 不引入新视觉 token, 复用现有变量; 手动确认 4 个 Tab (元信息 / 配置 / 资源 / Steps) 视觉一致
- 在 v0.5.3 综合设计文档第 5.2 节追加 Step 页布局图; `USER_MANUAL.md` 第 5.2 节更新为新截图说明（截图非本期要求）

### 5.3 后端

- `/api/captures/import-from-path` 端点保留（v0.5 历史已暴露）, 仅前端 `importFromPath` 不再被 UI 调用
- `importFromFile` 函数保留（新流程调用）
- `_mergeCapturesIntoSteps` 行为不变

---

## 6. 实施步骤（仅作记录, 实施时由 writing-plans 技能细化）

1. **`app.js` state 与常量**：在 `state = {}` 内追加 `currentPage` / `expandedStepSid`; 在文件顶部加 `const PAGE_SIZE = 10`。
2. **`app.js` 渲染函数**：实现 `_syncStepPagination` / `_computePageRanges` / `renderStepSidebar` / `renderStepTags` / `renderStepDetail` / `renderSteps`。
3. **`app.js` 交互绑定**：侧栏页码 click, tag click, tag drag, tag delete, 空状态 click, 拖拽到空状态 / step-main。
4. **`index.html`**：删除 expand-all / collapse-all 按钮, 删除 `.import-row`, 新增 `<input type="file">`, 修改 `#step-empty` 加 `.clickable` 类, 修改 `#step-list` 内部结构。
5. **`style.css`**：追加 §2 的 CSS 块。
6. **测试**：新增 `tests/test_step_pagination.py` 和 `tests/test_step_import_e2e.py`。
7. **文档**：更新 `USER_MANUAL.md` 第 5.2 节, 更新 `docs/superpowers/specs/2026-06-22-current-state-design.md` 第 5.2 节。
8. **CHANGELOG**：v0.5.5 一条, 描述 "Step 分页 + 空状态文件选择器"。

---

## 7. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 现有 v0.5 用户的肌肉记忆（输入路径）被打断 | 文档 / help modal 同步更新；新行为更快（少一次输入） |
| `state.expandedSteps` Set 字段保留但无人写，可能造成误解 | 代码注释说明：`expandedStepSid` 是新 SSOT；`expandedSteps` 仅保留以不破坏 undo 历史栈的 serialize 形状 |
| 拖 tag 重排时，索引计算跨页容易出错 | 拖拽仅在当前页 10 个 tag 内有效，跨页 drag-over 不接受 drop |
| 大量 step (e.g. 200+) 时侧栏页码过多 | 侧栏 `max-height: calc(100vh - 220px)` + `overflow-y: auto` 自动滚动；200 个 step = 20 个页码, 高度可控 |
| `state.expandedStepSid` 与 `state.expandedSteps` Set 不一致 | 渲染逻辑只读 `expandedStepSid`；Set 字段仅在 undo/redo 历史栈序列化为占位字段, 不参与渲染判断 |

---

## 8. 验收清单

- [ ] 空状态文本改为「尚无 Step — 点击导入 .ndjson」+ 「(拖入 .ndjson 也可)」
- [ ] 点击空状态弹出文件选择器，限定 `.ndjson`
- [ ] 拖入 `.ndjson` 到空状态 / step 区域触发导入
- [ ] 拖入非 `.ndjson` 文件被拒绝 + toast
- [ ] 步骤数 > 10 时显示侧栏，1-10, 11-20, ... 形式
- [ ] 步骤数 ≤ 10 时仅显示「1-10」
- [ ] 点击侧栏页码切换当前页
- [ ] 步骤数变化导致 currentPage 越界时自动跳到最后一页
- [ ] 步骤 tag 显示 method pill + path
- [ ] 点击 tag 展开 / 收起 detail；点击其他 tag 收起前一个
- [ ] detail 区域沿用现有 step-card 结构 (API/Request/Strategy)
- [ ] tag 可拖拽重排（当前页内）
- [ ] tag 上 hover 显示删除按钮，删除前弹确认
- [ ] 删除 detail 中的 step 同步更新 tag 区域
- [ ] 全部展开 / 全部折叠按钮已删除
- [ ] import-row 输入框 + 按钮已删除
- [ ] 「实时捕获」面板（含自动注入 toggle）保留，行为不变
- [ ] pytest 现有 165 passed / 4 skipped 仍通过
- [ ] 新增 `test_step_pagination.py` + `test_step_import_e2e.py` 通过
- [ ] 4 个 Tab 视觉风格与 v0.5 一致（无新 CSS 变量 / 字体）
