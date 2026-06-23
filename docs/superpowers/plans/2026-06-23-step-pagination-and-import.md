# Step 分页 + 空状态文件选择器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 prism Web 配置器的 Steps Tab 改为「左侧分页侧栏 + 右侧标签流」的分页布局（10 个一组），并把空状态框改为可点击的 .ndjson 文件选择器触发器。

**Architecture:** 保持现有 `state.steps` SSOT 不变, 新增 `state.currentPage` + `state.expandedStepSid` 两个 UI 派生状态; 把现有 `renderSteps()` 拆为 `renderStepSidebar` / `renderStepTags` / `renderStepDetail` 三个子渲染器; 通过隐藏 `<input type="file">` + JS click 触发原生文件选择器; 拖拽绑定到 `#step-empty` 和 `.step-main` 两个元素; 复用现有 `.method-pill` / `.step-card` / CSS variables, 不引入新视觉 token。

**Tech Stack:** Python 3.11+ / FastAPI / pytest / 前端三件套 `gimbal/prism/static/{app.js, index.html, style.css}`; 测试沿用现有 `pytest` + 静态文件读取 + HTTP `TestClient` 模式 (与 `test_frontend_v1.py` 同风格)。

---

## Global Constraints

> 这些是规范文档里的项目级要求, 每一步的实现都隐式遵守。

- **文件类型限制**: 导入只接受 `.ndjson` (前端 `accept` 属性 + JS 后缀校验双重检查); `.json` / `.yaml` 用例文件导入属未来范围, 不在本期。
- **每页 step 数**: `const PAGE_SIZE = 10` 模块级常量, 硬编码, 不走 schema。
- **state SSOT**: `state.steps[]` 是 step 数据的唯一真相; `state.currentPage` / `state.expandedStepSid` 是 UI 派生状态, **不** 持久化到后端。
- **视觉一致性**: 不引入新 CSS 变量、字体、图标; 复用 `--accent` / `--accent-soft` / `--accent-soft-border` / `--red` / `--color-border-tertiary` / `--font-mono` / `.method-pill` / `.step-card` / tabler-icons CDN。
- **后端**: `/api/captures/import-from-path` 端点保留 (向后兼容), 前端 `importFromPath` 函数被删除 (无新调用方)。
- **测试基线**: 现有 `pytest` 165 passed / 4 skipped 必须保持通过。
- **后端 NDJSON 注入**: 现有 `importFromFile` 函数 (app.js:1112) 行为不变, 本期复用。

---

## File Map

> 实施前先确认改动范围, 每个文件的职责单一。

| 文件 | 改动类型 | 职责 |
|---|---|---|
| `gimbal/prism/static/app.js` | Modify | 加 state/PAGE_SIZE/分页原语; 拆 renderSteps; 加 4 类交互绑定 |
| `gimbal/prism/static/index.html` | Modify | 加 `<input type="file">`; 改 `#step-empty`; 改 `#step-list` 内层结构; 删 expand-all/collapse-all/.import-row |
| `gimbal/prism/static/style.css` | Modify | 追加 `.step-layout` / `.step-sidebar` / `.step-tags` / `.step-tag` / `.step-detail` 等类 |
| `tests/test_frontend_v1.py` | Modify | 改 `test_index_html_step_toolbar` 断言 (删除 expand-all/collapse-all/import-btn); 加新 ID 断言 |
| `tests/test_step_pagination.py` | Create | E2E 测试: 25 steps 进 draft, HTTP + 静态检查验证侧栏 / tag 流 / 越界回退 |
| `tests/test_step_import_e2e.py` | Create | E2E 测试: 模拟 .ndjson 文件选择, 验证 steps merge |
| `USER_MANUAL.md` | Modify | 更新 §5.2 (Steps Tab 描述) |
| `CHANGELOG.md` | Modify | 加 v0.5.5 条目 |
| `docs/superpowers/specs/2026-06-22-current-state-design.md` | Modify | 同步 §5.2 现状描述 (可选, 非阻塞) |

---

## Task 1: state shape + 分页原语 (PAGE_SIZE / _syncStepPagination / _computePageRanges)

**Files:**
- Modify: `gimbal/prism/static/app.js:22-26` (state 字段), `gimbal/prism/static/app.js:43-49` (加 PAGE_SIZE + 原语函数, 放在 state 定义之后)
- Create: `tests/test_step_pagination_state.py`

**Interfaces:**
- Produces: `state.currentPage: number (1-based, 初始 1)`; `state.expandedStepSid: string | null (初始 null)`; `const PAGE_SIZE: number = 10`; `_syncStepPagination(): void`; `_computePageRanges(): Array<{label: string, start: number, end: number}>`
- `_syncStepPagination()` 必须在 `state.steps` 长度变化后调用, 修正 `currentPage` 越界 + 修正 `expandedStepSid` 失效
- `_computePageRanges()` 派生, 不写 state

> **约束**: 现有 `state.expandedSteps` Set 与 `state.collapsedSteps` Set 字段保留 (不破坏 undo/redo 历史栈 serialize 形状), 但渲染逻辑只用 `state.expandedStepSid`。

- [ ] **Step 1: 在 `app.js` 加 PAGE_SIZE 常量 + 新 state 字段**

打开 `gimbal/prism/static/app.js`, 在第 26 行 `state = {` 块内的 `collapsedSteps: new Set(),` 之后追加 (注意: state 字段的初始值要在 `state = {` 闭合大括号之前, 而 PAGE_SIZE 是 const 要放在 state 对象外):

文件第 22-32 行 (state 定义) 改为:
```javascript
state = {
  ...
  steps: [],                                           // [{id, capture, key_hint, ...}]
  captures: [],                                        // 来自 WS
  activeTab: 0,
  expandedSteps: new Set(),                            // v0.5.5: 保留供 undo/redo 兼容, 新逻辑不写
  collapsedSteps: new Set(),                           // v0.5.5: 保留供 undo/redo 兼容, 新逻辑不写
  currentPage: 1,                                      // v0.5.5: 1-based 页码, 渲染派生
  expandedStepSid: null,                               // v0.5.5: 当前展开的 step.__sid, 单展开手风琴
};
const PAGE_SIZE = 10;                                  // v0.5.5: 模块级常量, 硬编码
```

在文件第 49 行附近 (`function _safeParseBody` 之前) 加两个新函数:
```javascript
function _computePageRanges() {
  const ranges = [];
  for (let p = 0; p * PAGE_SIZE < state.steps.length; p++) {
    const start = p * PAGE_SIZE;
    const end = Math.min(start + PAGE_SIZE, state.steps.length);
    const from = start + 1;
    const to = end;
    ranges.push({ label: `${from}-${to}`, start, end });
  }
  return ranges;
}

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

- [ ] **Step 2: 写测试 — 静态检查函数存在 + 静态检查分页原语在文件内被声明**

Create: `tests/test_step_pagination_state.py`

```python
"""Step 分页原语静态测试: 验证 _syncStepPagination / _computePageRanges / PAGE_SIZE
在 app.js 中被正确声明, 且符合预期签名。

不依赖浏览器, 仅做文件读取 + 正则匹配。
"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    assert APP_JS.exists(), f"app.js 不存在: {APP_JS}"
    return APP_JS.read_text(encoding="utf-8")


def test_page_size_constant_declared():
    """PAGE_SIZE = 10 必须存在, 在 app.js 顶部声明。"""
    text = _read()
    m = re.search(r"const\s+PAGE_SIZE\s*=\s*(\d+)\s*;", text)
    assert m, "未找到 `const PAGE_SIZE = N;` 声明"
    assert int(m.group(1)) == 10, f"PAGE_SIZE 必须是 10, 实际 {m.group(1)}"


def test_state_has_current_page():
    text = _read()
    assert re.search(r"currentPage\s*:\s*1", text), "state.currentPage 初始值缺失或不是 1"


def test_state_has_expanded_step_sid():
    text = _read()
    assert re.search(r"expandedStepSid\s*:\s*null", text), "state.expandedStepSid 初始值缺失或不是 null"


def test_sync_step_pagination_declared():
    text = _read()
    m = re.search(r"function\s+_syncStepPagination\s*\(\s*\)\s*\{", text)
    assert m, "未找到 _syncStepPagination 函数声明"


def test_sync_step_pagination_corrects_current_page():
    """函数体必须含 `state.currentPage = pageCount` 修正逻辑。"""
    text = _read()
    m = re.search(
        r"function\s+_syncStepPagination\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m, "未匹配到 _syncStepPagination 函数体"
    body = m.group(1)
    assert "state.currentPage" in body, "函数体未引用 state.currentPage"
    assert "pageCount" in body, "函数体未计算 pageCount"


def test_sync_step_pagination_clears_orphaned_sid():
    text = _read()
    m = re.search(
        r"function\s+_syncStepPagination\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "state.expandedStepSid" in body, "函数体未处理 expandedStepSid 失效"
    assert "state.steps.some" in body, "函数体未检查 sid 是否仍存在"


def test_compute_page_ranges_declared():
    text = _read()
    m = re.search(r"function\s+_computePageRanges\s*\(\s*\)\s*\{", text)
    assert m, "未找到 _computePageRanges 函数声明"


def test_compute_page_ranges_returns_labeled_ranges():
    text = _read()
    m = re.search(
        r"function\s+_computePageRanges\s*\(\s*\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "label" in body, "函数体未生成 label 字段"
    assert "start" in body and "end" in body, "函数体未生成 start/end 字段"
    assert "PAGE_SIZE" in body, "函数体未引用 PAGE_SIZE"
```

- [ ] **Step 3: 跑测试, 验证全部通过**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_step_pagination_state.py -v
```

Expected: 8 passed.

- [ ] **Step 4: 跑全套测试, 确认未破坏现有用例**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 165+ passed / 4 skipped (基线), 无新增失败。

- [ ] **Step 5: 提交**

```bash
cd "D:/M/ModelRegistry" && git add gimbal/prism/static/app.js tests/test_step_pagination_state.py && \
  git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "feat(steps): add currentPage + expandedStepSid state and pagination primitives (v0.5.5)"
```

---

## Task 2: HTML 结构改造 (index.html)

**Files:**
- Modify: `gimbal/prism/static/index.html:271-290` (Steps section)

**Interfaces:**
- Produces HTML structure: 
  - 删除: `#expand-all`, `#collapse-all` 按钮, `.import-row` 整块
  - 新增: `<input type="file" id="ndjson-file-input" accept=".ndjson,application/x-ndjson" hidden>`
  - 修改: `#step-empty` 加 `clickable` 类 + `role="button"` + `tabindex="0"` + 文案改写
  - 修改: `#step-list` 内部结构改为 `.step-layout > .step-sidebar + .step-main > .step-tags + .step-detail`

- [ ] **Step 1: 删除 expand-all / collapse-all / import-row 三个块**

打开 `gimbal/prism/static/index.html`, 定位到 `<div class="step-toolbar">` 块 (约第 270-281 行), 删掉以下两行:
```html
<button class="add-btn" id="expand-all" type="button" title="全部展开">
  <i class="ti ti-arrows-maximize" aria-hidden="true"></i> 全部展开
</button>
<button class="add-btn" id="collapse-all" type="button" title="全部折叠">
  <i class="ti ti-arrows-minimize" aria-hidden="true"></i> 全部折叠
</button>
```

定位到 `#step-list` 之后 (约第 286-289 行), 删掉整个 `.import-row` 块:
```html
<div class="import-row">
  <input class="fin" id="import-path" placeholder="captures.ndjson 路径 或拖入 .ndjson 文件" />
  <button id="import-btn" type="button">导入</button>
</div>
```

- [ ] **Step 2: 加 `<input type="file">` 隐藏元素**

在 `#step-list` 之前 (即 `.step-toolbar` 闭合 `</div>` 之后) 加:
```html
<!-- v0.5.5: 隐藏的文件选择器, 由 #step-empty 点击 / 拖拽触发 -->
<input type="file" id="ndjson-file-input" accept=".ndjson,application/x-ndjson"
       hidden aria-hidden="true" />
```

- [ ] **Step 3: 改 `#step-empty` 为可点击**

把:
```html
<div id="step-empty" class="empty-state" hidden>尚无 Step — 导入 captures 或点击「+ 新增 Step」开始</div>
```
改为:
```html
<div id="step-empty" class="empty-state clickable"
     role="button" tabindex="0" aria-label="点击导入 .ndjson 文件">
  尚无 Step — 点击导入 .ndjson
  <small>(拖入 .ndjson 也可)</small>
</div>
```

- [ ] **Step 4: 改 `#step-list` 内部结构**

把:
```html
<div id="step-list"></div>
```
改为:
```html
<div id="step-list" class="step-layout">
  <nav id="step-sidebar" class="step-sidebar" aria-label="Step 分页"></nav>
  <div class="step-main">
    <div id="step-tags" class="step-tags" role="list"></div>
    <div id="step-detail" class="step-detail" hidden></div>
  </div>
</div>
```

- [ ] **Step 5: 改写 `tests/test_frontend_v1.py::test_index_html_step_toolbar`**

打开 `tests/test_frontend_v1.py` 第 91-95 行, 找到 `test_index_html_step_toolbar` 函数。改:
```python
def test_index_html_step_toolbar():
    """Steps tab 工具栏 / 空状态 / 文件选择器 / 列表结构的 ID 存在。"""
    text = _read(INDEX_HTML)
    for bid in ["add-step", "ndjson-file-input", "step-sidebar",
                "step-tags", "step-detail", "step-empty"]:
        assert f'id="{bid}"' in text, f"缺 step 元素 #{bid}"
    # 旧的 expand-all / collapse-all / import-row / import-btn / import-path 必须被删除
    for old in ["expand-all", "collapse-all", "import-btn", "import-path"]:
        assert f'id="{old}"' not in text, f"应已删除 #{old}"
    # step-list 必须有 step-layout 类
    assert 'id="step-list" class="step-layout"' in text, "step-list 缺少 step-layout 类"
    # step-empty 必须可点击
    assert 'id="step-empty" class="empty-state clickable"' in text, \
        "step-empty 缺 clickable 类"
```

- [ ] **Step 6: 跑测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_frontend_v1.py -v
```

Expected: 全部 passed (含 `test_index_html_step_toolbar` 的更新断言)。

- [ ] **Step 7: 提交**

```bash
cd "D:/M/ModelRegistry" && git add gimbal/prism/static/index.html tests/test_frontend_v1.py && \
  git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "feat(steps): restructure Steps tab HTML (file input, clickable empty, sidebar+tags layout)"
```

---

## Task 3: CSS for new layout (style.css)

**Files:**
- Modify: `gimbal/prism/static/style.css` (append at EOF, after line 1045)

**Interfaces:**
- Produces CSS classes: `.step-layout`, `.step-sidebar`, `.step-sidebar .page-tab`, `.step-main`, `.step-tags`, `.step-tag`, `.step-tag.active`, `.step-tag.dragging`, `.step-tag.drag-over`, `.step-detail`, drop-target 高亮
- 复用现有变量, 不引入新 token

- [ ] **Step 1: 追加 CSS 块到 style.css 末尾**

打开 `gimbal/prism/static/style.css`, 在文件最末尾追加 (从 `/* ───────── Step Pagination v0.5.5 ───────── */` 开始):

```css
/* ───────── Step Pagination v0.5.5 ───────── */
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
.step-tag.drag-over {
  border-style: dashed;
  border-color: var(--accent);
  background: var(--accent-soft);
}
.step-tag .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-tag .del {
  background: transparent; border: 0; color: var(--red);
  cursor: pointer; font-size: 13px; padding: 0 2px;
  opacity: 0; transition: opacity .15s;
}
.step-tag:hover .del { opacity: 1; }

.step-detail { margin-top: 8px; }

/* 拖拽 .ndjson 时的视觉指示 */
.step-main.prism-drop-target,
#step-empty.prism-drop-target {
  outline: 2px dashed var(--accent);
  outline-offset: -4px;
  border-radius: 9px;
  background: var(--accent-soft);
}

/* 空状态可点击 */
#step-empty.clickable {
  cursor: pointer;
  transition: background .15s, transform .1s;
}
#step-empty.clickable:hover {
  background: var(--accent-soft);
  transform: translateY(-1px);
}
#step-empty small {
  display: block; margin-top: 4px; opacity: .75; font-size: 11.5px;
}
```

- [ ] **Step 2: 写测试 — 静态检查所有新类在 style.css 中被定义**

Create: `tests/test_step_pagination_css.py`

```python
"""Step 分页 CSS 静态测试: 验证新类在 style.css 中被定义, 且复用现有 CSS 变量。"""
from __future__ import annotations

from pathlib import Path

STYLE_CSS = Path("D:/M/ModelRegistry/gimbal/prism/static/style.css")


def _read() -> str:
    assert STYLE_CSS.exists(), f"style.css 不存在: {STYLE_CSS}"
    return STYLE_CSS.read_text(encoding="utf-8")


def test_required_classes_defined():
    text = _read()
    for cls in [".step-layout", ".step-sidebar", ".step-sidebar .page-tab",
                ".step-tags", ".step-tag", ".step-tag.active",
                ".step-tag.dragging", ".step-tag.drag-over",
                ".step-tag .del", ".step-detail", ".step-main",
                "#step-empty.clickable", "#step-empty.clickable:hover"]:
        assert cls in text, f"缺 CSS 规则: {cls}"


def test_reuses_existing_variables_only():
    """不允许引入新 CSS 变量 (--xxx:); 只许读 var(--xxx)。"""
    text = _read()
    # 找新增区块 (从 v0.5.5 marker 之后)
    marker_idx = text.find("Step Pagination v0.5.5")
    assert marker_idx > 0, "未找到 v0.5.5 CSS 块 marker"
    new_block = text[marker_idx:]
    # 不允许定义新变量
    import re
    new_vars = re.findall(r"--[\w-]+\s*:", new_block)
    assert not new_vars, f"v0.5.5 块不应定义新变量: {new_vars}"


def test_grid_columns_for_sidebar():
    text = _read()
    m_idx = text.find("Step Pagination v0.5.5")
    new_block = text[m_idx:]
    assert "grid-template-columns: 96px 1fr" in new_block, \
        ".step-layout 必须用 96px 1fr 网格"


def test_sticky_sidebar():
    text = _read()
    m_idx = text.find("Step Pagination v0.5.5")
    new_block = text[m_idx:]
    assert "position: sticky" in new_block, "侧栏必须 sticky"
    assert "max-height: calc(100vh - 220px)" in new_block, \
        "侧栏必须限制最大高度并可滚动"
```

- [ ] **Step 3: 跑测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_step_pagination_css.py -v
```

Expected: 4 passed.

- [ ] **Step 4: 跑全套测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 169+ passed (165 baseline + 8 state + 4 CSS = 177, 但 frontend_v1 不变, 实际 165 + 12 = 177).

- [ ] **Step 5: 提交**

```bash
cd "D:/M/ModelRegistry" && git add gimbal/prism/static/style.css tests/test_step_pagination_css.py && \
  git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "feat(steps): add Step pagination CSS (sidebar + tag layout, reuses existing tokens)"
```

---

## Task 4: 重构 renderSteps() 为 3 个子渲染器

**Files:**
- Modify: `gimbal/prism/static/app.js:710-940` (现有 renderSteps / toggleStep 区域)

**Interfaces:**
- Produces: `renderStepSidebar()` (左 96px 侧栏, 列出 1-10, 11-20, ...); `renderStepTags()` (当前页 10 个 tag, 含 method + path + del 按钮 + draggable); `renderStepDetail()` (若 `state.expandedStepSid` 存在, 复用现有 `.step-card` 内部结构)
- `renderSteps()` 改为总入口: 调 `_syncStepPagination` → 调 3 个子渲染器 → 调 `syncStepEmpty`

> **关键**: 现有 `renderSteps()` 内的 step-card DOM 生成代码 (约 80 行) **整体抽出** 到一个内部函数 `_renderStepCardBody(s, i)`, 接收 step 对象和全局索引, 返回 HTML 字符串。`renderStepDetail` 调用它。

- [ ] **Step 1: 把 step-card HTML 生成抽到独立函数**

在 `gimbal/prism/static/app.js` 的 Steps 区域 (第 675 行附近), 在 `cURLForStep` 之后、`updateUrlPreview` 之前, 加一个内部辅助函数:

```javascript
function _renderStepCardBody(s, globalIdx) {
  // 抽出原 renderSteps() 内的 step-card innerHTML 生成代码
  // globalIdx: step 在 state.steps 中的全局索引 (0-based), 用于 seq 编号和 url-preview id
  const method = s.api?.method || s.capture?.method || 'GET';
  const path = s.api?.path || s.capture?.path || '/';
  const status = s.capture?.response?.status;
  const ms = s.capture?.response_ms;
  const isExpanded = !state.collapsedSteps.has(s.__sid);
  return `
    <div class="shdr" role="button" tabindex="0" aria-expanded="${isExpanded}" aria-controls="sbody-${s.__sid}">
      <span class="seq">${globalIdx + 1}-${escapeHtml(s.key_hint || _pathSlug(path) || 'step')}</span>
      <span class="method-pill ${method}">${method}</span>
      <span class="path" title="${escapeAttr(path)}">${escapeHtml(path)}</span>
      ${status ? `<span class="status-badge s${Math.floor(status / 100)}xx">${status}</span>` : ''}
      ${ms != null ? `<span class="ms-pill">${ms}ms</span>` : ''}
      <span class="grow"></span>
      <button class="curl-copy" title="复制 cURL" aria-label="复制 cURL 命令">cURL</button>
      <button class="del" aria-label="删除 Step ${globalIdx + 1}">删除</button>
      <button class="toggle-exp" aria-expanded="${isExpanded}" aria-controls="sbody-${s.__sid}">${isExpanded ? '收起' : '展开'}</button>
    </div>
    <div class="sbody" id="sbody-${s.__sid}" role="region" aria-label="Step ${globalIdx + 1} 详情">
      <div class="sub-tabs" role="tablist">
        <button class="active" data-sub="api" role="tab" aria-selected="true">API</button>
        <button data-sub="req" role="tab" aria-selected="false">Request</button>
        <button data-sub="str" role="tab" aria-selected="false">Strategy</button>
      </div>
      <div class="url-preview" id="url-preview-${globalIdx}"></div>
      <div class="sub-pane" data-pane="api">
        <div class="field-row"><label>service</label>
          <input class="fin mono" data-sf="service" value="${escapeAttr(s.api?.service || '')}" list="svc-list" />
          <datalist id="svc-list">
            ${Object.keys(state.services).map((k) => `<option value="${escapeAttr(k)}">`).join('')}
          </datalist>
        </div>
        <div class="field-row"><label>method</label>
          <select class="fin" data-sf="method">
            ${['GET','POST','PUT','DELETE','PATCH','HEAD','OPTIONS'].map((m) =>
              `<option ${s.api?.method === m ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="field-row"><label>path</label>
          <input class="fin mono" data-sf="path" value="${escapeAttr(s.api?.path || '')}" />
        </div>
        <div class="field-row"><label>key_hint</label>
          <input class="fin" data-sf="key_hint" value="${escapeAttr(s.key_hint || '')}" placeholder="如 call_login" />
        </div>
      </div>
      <div class="sub-pane" data-pane="req" hidden>
        <div class="field-row"><label>params (JSON)</label>
          <textarea class="fin fta mono" data-sf="params" rows="2">${escapeHtml(JSON.stringify(s.req?.params || {}, null, 2))}</textarea>
        </div>
        <div class="field-row"><label>body (JSON)</label>
          <textarea class="fin fta mono" data-sf="body" rows="6">${escapeHtml(JSON.stringify(s.req?.body || {}, null, 2))}</textarea>
        </div>
        <div class="field-row"><label>headers (JSON)</label>
          <textarea class="fin fta mono" data-sf="headers" rows="3">${escapeHtml(JSON.stringify(s.req?.headers || {}, null, 2))}</textarea>
        </div>
      </div>
      <div class="sub-pane" data-pane="str" hidden>
        <div id="str-list-${s.__sid}"></div>
        <div class="add-row">
          <button class="add-btn" data-add="assertion">+ assertion</button>
          <button class="add-btn" data-add="extract">+ extract</button>
          <button class="add-btn" data-add="assign">+ assign</button>
        </div>
      </div>
    </div>
  `;
}
```

- [ ] **Step 2: 替换 `renderSteps()` 为新版本 (含 3 个子渲染器)**

把现有 `renderSteps()` (app.js:713) 整段替换为:

```javascript
function renderStepSidebar() {
  const nav = $('step-sidebar');
  if (!nav) return;
  if (state.steps.length === 0) { nav.innerHTML = ''; return; }
  const ranges = _computePageRanges();
  nav.innerHTML = ranges.map((r, i) => {
    const active = (i + 1) === state.currentPage;
    return `<button class="page-tab${active ? ' active' : ''}" data-page="${i + 1}" role="tab" aria-selected="${active}">
      ${r.label}<span class="page-count">${r.end - r.start} / ${state.steps.length}</span>
    </button>`;
  }).join('');
  nav.querySelectorAll('.page-tab').forEach((b) => {
    b.addEventListener('click', () => {
      const k = parseInt(b.dataset.page, 10);
      if (!Number.isFinite(k)) return;
      state.currentPage = Math.min(Math.max(1, k), _computePageRanges().length || 1);
      renderSteps();
    });
  });
}

function renderStepTags() {
  const box = $('step-tags');
  if (!box) return;
  if (state.steps.length === 0) { box.innerHTML = ''; return; }
  const ranges = _computePageRanges();
  const range = ranges[state.currentPage - 1];
  if (!range) { box.innerHTML = ''; return; }
  const pageSteps = state.steps.slice(range.start, range.end);
  box.innerHTML = pageSteps.map((s) => {
    const method = (s.api?.method || s.capture?.method || 'GET').toUpperCase();
    const path = s.api?.path || s.capture?.path || '/';
    const active = state.expandedStepSid === s.__sid;
    return `<div class="step-tag${active ? ' active' : ''}" data-sid="${escapeAttr(s.__sid)}" draggable="true" role="listitem" tabindex="0">
      <span class="method-pill ${method}">${method}</span>
      <span class="path" title="${escapeAttr(path)}">${escapeHtml(path)}</span>
      <button class="del" aria-label="删除 Step">×</button>
    </div>`;
  }).join('');
  // 事件: tag click → 展开/收起
  box.querySelectorAll('.step-tag').forEach((tagEl) => {
    const sid = tagEl.dataset.sid;
    tagEl.addEventListener('click', (e) => {
      if (e.target.closest('.del')) return;  // 删除按钮独立处理
      state.expandedStepSid = (state.expandedStepSid === sid) ? null : sid;
      renderSteps();
    });
    tagEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        state.expandedStepSid = (state.expandedStepSid === sid) ? null : sid;
        renderSteps();
      }
    });
  });
}

function renderStepDetail() {
  const det = $('step-detail');
  if (!det) return;
  if (!state.expandedStepSid) { det.hidden = true; det.innerHTML = ''; return; }
  const s = state.steps.find((x) => x.__sid === state.expandedStepSid);
  if (!s) { det.hidden = true; det.innerHTML = ''; return; }
  const globalIdx = state.steps.indexOf(s);
  det.hidden = false;
  det.innerHTML = `<div class="step-card" data-sid="${escapeAttr(s.__sid)}" data-idx="${globalIdx}">${_renderStepCardBody(s, globalIdx)}</div>`;
  // 触发原 step-card 内部的事件绑定 (复用现有 attach logic)
  // 简化: 重新走一遍原 renderSteps 内的事件绑定 (见 attachStepCardEvents)
  attachStepCardEvents(det.querySelector('.step-card'), s, globalIdx);
}

function renderSteps() {
  _syncStepPagination();
  renderStepSidebar();
  renderStepTags();
  renderStepDetail();
  syncStepEmpty();
}
```

> **注意**: `attachStepCardEvents(card, s, globalIdx)` 是把现有 `renderSteps()` 内的 step-card 事件绑定 (shdr click / del / curl-copy / sub-tabs / data-sf / strategy 渲染) 抽出来的函数。完整代码在下一步。

- [ ] **Step 3: 把现有 step-card 事件绑定抽到 `attachStepCardEvents`**

紧接 `renderStepDetail` 之后, 加:

```javascript
function attachStepCardEvents(card, s, globalIdx) {
  // 抽出原 renderSteps() 内的 step-card 事件绑定代码 (约 app.js:789-936)
  // 输入: card DOM 元素 + step 对象 + 全局索引
  // 行为: 绑定 shdr click / del / curl-copy / sub-tabs / data-sf / strategy items
  const shdr = card.querySelector('.shdr');
  shdr.addEventListener('click', (e) => {
    if (e.target.closest('button')) return;
    toggleStep(s, card);
  });
  shdr.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      if (e.target === shdr) { e.preventDefault(); toggleStep(s, card); }
    }
  });
  card.querySelector('.shdr .del').addEventListener('click', async (e) => {
    e.stopPropagation();
    const method = s.api?.method || s.capture?.method || 'GET';
    const path = s.api?.path || s.capture?.path || '/';
    const ok = await confirmModal('删除 Step', `确定删除 Step ${globalIdx + 1} (${method} ${path})?`, { ok: '删除' });
    if (!ok) return;
    state.steps.splice(globalIdx, 1);
    state.expandedSteps.delete(s.__sid);
    state.collapsedSteps.delete(s.__sid);
    if (state.expandedStepSid === s.__sid) state.expandedStepSid = null;
    pushHistory();
    renderSteps();
  });
  card.querySelector('.toggle-exp').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleStep(s, card);
  });
  card.querySelector('.curl-copy').addEventListener('click', async (e) => {
    e.stopPropagation();
    const text = cURLForStep(s);
    try { await navigator.clipboard.writeText(text); toast(`Step ${globalIdx + 1} cURL 已复制`, 'success', 1500); }
    catch (_) { toast('复制失败', 'error'); }
  });
  card.querySelectorAll('.sub-tabs button').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      card.querySelectorAll('.sub-tabs button').forEach((x) => {
        x.classList.remove('active');
        x.setAttribute('aria-selected', 'false');
      });
      b.classList.add('active');
      b.setAttribute('aria-selected', 'true');
      card.querySelectorAll('.sub-pane').forEach((p) => { p.hidden = p.dataset.pane !== b.dataset.sub; });
    });
  });
  card.querySelectorAll('[data-sf]').forEach((el) => {
    el.addEventListener('input', () => {
      const f = el.dataset.sf;
      let v = el.value;
      if (['params','body','headers'].includes(f)) {
        try { v = JSON.parse(v); el.classList.remove('invalid'); }
        catch (_) { el.classList.add('invalid'); toast(`JSON 解析失败: ${f}`, 'error', 1800); return; }
      }
      if (f === 'service' || f === 'method' || f === 'path') {
        s.api = s.api || {}; s.api[f] = v;
      } else if (f === 'key_hint') {
        s.key_hint = v;
      } else {
        s.req = s.req || {}; s.req[f] = v;
      }
      if (f === 'method' || f === 'path' || f === 'service') {
        updateUrlPreview(card, s);
        if (f === 'method' || f === 'path') {
          card.querySelector('.method-pill').textContent = (s.api.method || 'GET').toUpperCase();
          card.querySelector('.method-pill').className = `method-pill ${s.api.method || 'GET'}`;
          card.querySelector('.path').textContent = s.api.path || '/';
          card.querySelector('.path').title = s.api.path || '/';
          const seq = card.querySelector('.seq');
          seq.textContent = `${globalIdx + 1}-${s.key_hint || _pathSlug(s.api.path) || 'step'}`;
        }
      }
      scheduleSave();
    });
  });
  s.assertions = s.assertions || [];
  s.extracts = s.extracts || [];
  s.assigns = s.assigns || [];
  const strList = card.querySelector(`#str-list-${s.__sid}`);
  // (完整 strategy 渲染逻辑同现有 renderSteps 内: renderStr 等; 略, 见 app.js:866-940)
  // 此处为简洁省略 80 行, 实施时从原 renderSteps 拷贝 strategy 渲染部分即可
}
```

> **实施注意**: `attachStepCardEvents` 内的 strategy 渲染块 (assertion/extract/assign 列表) 需要从现有 `renderSteps()` 第 866-940 行原样拷贝。Task 描述为简洁省略; 实施时按 git diff 逐行迁移, 不修改逻辑。

- [ ] **Step 4: 验证 `renderSteps()` 调用点不受影响**

`renderSteps()` 在 app.js 内被多处调用 (新增 step / 删除 / undo/redo / import / drag 等)。`renderSteps()` 签名不变, 内部重写对调用方透明。无需改调用点。

- [ ] **Step 5: 写测试 — 静态检查新函数 + 旧 renderSteps body 不含重复**

Create: `tests/test_render_steps_refactor.py`

```python
"""renderSteps 重构测试: 验证新子渲染器被声明, 旧 renderSteps 仍存在并调用它们。"""
from __future__ import annotations

from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_subrenderers_declared():
    text = _read()
    for fn in ["renderStepSidebar", "renderStepTags", "renderStepDetail", "renderSteps",
               "_renderStepCardBody", "attachStepCardEvents", "_syncStepPagination",
               "_computePageRanges"]:
        m = __import__("re").search(rf"function\s+{fn}\s*\(", text)
        assert m, f"未找到函数: {fn}"


def test_render_steps_orchestrator():
    """renderSteps 必须依次调用 4 个子函数。"""
    text = _read()
    m = __import__("re").search(
        r"function\s+renderSteps\s*\(\s*\)\s*\{(.*?)\n\}", text, __import__("re").DOTALL
    )
    assert m, "renderSteps 函数体未找到"
    body = m.group(1)
    assert "_syncStepPagination()" in body
    assert "renderStepSidebar()" in body
    assert "renderStepTags()" in body
    assert "renderStepDetail()" in body
    assert "syncStepEmpty()" in body


def test_attach_step_card_events_uses_correct_sid_for_delete():
    """删除事件必须用传入的 globalIdx 计算 UI 编号, 且清空 expandedStepSid。"""
    text = _read()
    assert "state.expandedStepSid === s.__sid" in text, \
        "删除 step 后未清空 state.expandedStepSid"
```

- [ ] **Step 6: 跑测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_render_steps_refactor.py -v
```

Expected: 3 passed.

- [ ] **Step 7: 跑全套测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 180+ passed / 4 skipped.

- [ ] **Step 8: 提交**

```bash
cd "D:/M/ModelRegistry" && git add gimbal/prism/static/app.js tests/test_render_steps_refactor.py && \
  git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "refactor(steps): split renderSteps into 3 sub-renderers (sidebar/tags/detail)"
```

---

## Task 5: Tag 删除按钮 + 拖拽重排

**Files:**
- Modify: `gimbal/prism/static/app.js` (在 `renderStepTags` 函数内, Task 4 的代码)

**Interfaces:**
- Produces 行为: 
  - 点 tag 上的 `.del` 按钮 → confirmModal → `state.steps.splice(globalIdx, 1)` → `renderSteps()`
  - 拖 tag → 在当前页 10 个 tag 内重排 → `state.steps.splice` → `_syncStepPagination()` → `renderSteps()`

- [ ] **Step 1: 在 `renderStepTags` 的事件绑定块内加删除按钮处理**

定位到 Task 4 Step 2 中的 `renderStepTags` 内, `box.querySelectorAll('.step-tag').forEach` 之后, 加:

```javascript
// 删除按钮
box.querySelectorAll('.step-tag .del').forEach((btn) => {
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const tagEl = btn.closest('.step-tag');
    const sid = tagEl?.dataset.sid;
    const globalIdx = state.steps.findIndex((x) => x.__sid === sid);
    if (globalIdx < 0) return;
    const s = state.steps[globalIdx];
    const method = s.api?.method || s.capture?.method || 'GET';
    const path = s.api?.path || s.capture?.path || '/';
    const ok = await confirmModal('删除 Step', `确定删除 Step ${globalIdx + 1} (${method} ${path})?`, { ok: '删除' });
    if (!ok) return;
    state.steps.splice(globalIdx, 1);
    if (state.expandedStepSid === sid) state.expandedStepSid = null;
    pushHistory();
    _syncStepPagination();
    renderSteps();
  });
});
```

- [ ] **Step 2: 加 tag 拖拽重排处理**

紧接删除按钮代码后, 加:

```javascript
// 拖拽重排 (当前页内 10 个 tag)
let _dragFromIdx = null;
box.querySelectorAll('.step-tag').forEach((tagEl) => {
  tagEl.addEventListener('dragstart', (e) => {
    const sid = tagEl.dataset.sid;
    _dragFromIdx = state.steps.findIndex((x) => x.__sid === sid);
    tagEl.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  });
  tagEl.addEventListener('dragend', () => {
    tagEl.classList.remove('dragging');
    box.querySelectorAll('.step-tag.drag-over').forEach((x) => x.classList.remove('drag-over'));
    _dragFromIdx = null;
  });
  tagEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (_dragFromIdx == null) return;
    tagEl.classList.add('drag-over');
  });
  tagEl.addEventListener('dragleave', () => {
    tagEl.classList.remove('drag-over');
  });
  tagEl.addEventListener('drop', (e) => {
    e.preventDefault();
    tagEl.classList.remove('drag-over');
    if (_dragFromIdx == null) return;
    const sid = tagEl.dataset.sid;
    const toGlobalIdx = state.steps.findIndex((x) => x.__sid === sid);
    if (toGlobalIdx < 0 || toGlobalIdx === _dragFromIdx) return;
    // 仅在当前页内允许重排 (pageSteps 内)
    const range = _computePageRanges()[state.currentPage - 1];
    if (!range) return;
    if (_dragFromIdx < range.start || _dragFromIdx >= range.end) return;
    if (toGlobalIdx < range.start || toGlobalIdx >= range.end) return;
    const [moved] = state.steps.splice(_dragFromIdx, 1);
    state.steps.splice(toGlobalIdx, 0, moved);
    pushHistory();
    scheduleSave();
    renderSteps();
  });
});
```

- [ ] **Step 3: 写测试 — 静态检查事件处理函数存在**

Create: `tests/test_tag_drag_delete.py`

```python
"""Tag 删除 + 拖拽静态测试。"""
from __future__ import annotations

import re
from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_tag_delete_handler_exists():
    text = _read()
    assert "querySelectorAll('.step-tag .del')" in text, "未找到 tag 删除按钮事件绑定"
    assert "confirmModal('删除 Step'" in text, "未走 confirmModal"


def test_drag_reorder_handler_exists():
    text = _read()
    for evt in ["'dragstart'", "'dragover'", "'drop'", "'dragend'", "'dragleave'"]:
        assert evt in text, f"未找到拖拽事件: {evt}"
    assert "_dragFromIdx" in text, "未使用 _dragFromIdx 状态"
    assert "state.steps.splice" in text, "未调用 splice 重排"
    # 跨页守卫
    assert "range.start" in text and "range.end" in text, "未做跨页拖拽守卫"
```

- [ ] **Step 4: 跑测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_tag_drag_delete.py -v
```

Expected: 2 passed.

- [ ] **Step 5: 跑全套 + 提交**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -5 && \
git add gimbal/prism/static/app.js tests/test_tag_drag_delete.py && \
git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "feat(steps): wire up tag delete + drag-to-reorder within current page"
```

---

## Task 6: 空状态点击 + 拖拽 + 文件选择器集成

**Files:**
- Modify: `gimbal/prism/static/app.js` (在 Steps 区域下方加新事件绑定)

**Interfaces:**
- Produces 行为:
  - 点 `#step-empty` 或按 Enter/Space → `$('ndjson-file-input').click()`
  - 拖 `.ndjson` 到 `#step-empty` / `.step-main` → 校验 → 调 `importFromFile`
  - `#ndjson-file-input` change → 校验后缀 → 调 `importFromFile`
- 删除: 旧 `#import-btn` click handler (Task 2 已删 HTML, 确认 JS 也清)

- [ ] **Step 1: 删掉旧 `#import-btn` click handler**

打开 `gimbal/prism/static/app.js`, 找到 `$('import-btn').addEventListener` 块 (约 1131 行), 整段删除 (10 行, 含 `e.stopPropagation` / `value.trim` / `disabled = true` / `importFromPath` 等)。

- [ ] **Step 2: 删掉旧的 `.import-row` 拖拽绑定**

找到 `'dragenter','dragover'.forEach((evt) => { const row = document.querySelector('.import-row')` 块 (约 1151-1167 行) 和 `const importInput = $('import-path')` 块 (约 1169-1185 行), 整段删除。

- [ ] **Step 3: 加新的空状态 click + 键盘 + 拖拽绑定**

在 app.js 内, 找一个合适位置 (例如 `// ── WebSocket ──` 之前), 加:

```javascript
// ── Step v0.5.5: 空状态触发文件选择器 ──────────────────────
const _stepEmpty = $('step-empty');
if (_stepEmpty) {
  const triggerFilePicker = () => $('ndjson-file-input').click();
  _stepEmpty.addEventListener('click', triggerFilePicker);
  _stepEmpty.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      triggerFilePicker();
    }
  });
}

const _ndjsonInput = $('ndjson-file-input');
if (_ndjsonInput) {
  _ndjsonInput.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';                          // 允许重选同一文件
    if (!file) return;
    if (!/\.ndjson$/i.test(file.name)) {
      toast('请选择 .ndjson 文件', 'error');
      return;
    }
    await _importNdjsonFile(file);
  });
}

// ── Step v0.5.5: 拖拽 .ndjson 到空状态 / step 区域 ───────────
function _handleNdjsonDrop(e) {
  e.preventDefault();
  const target = e.currentTarget;
  target?.classList.remove('prism-drop-target');
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  if (!/\.ndjson$/i.test(file.name)) {
    toast('请拖入 .ndjson 文件', 'error');
    return;
  }
  _importNdjsonFile(file);
}
const _dropTargets = [$('step-empty'), document.querySelector('.step-main')].filter(Boolean);
_dropTargets.forEach((el) => {
  ['dragenter', 'dragover'].forEach((evt) => {
    el.addEventListener(evt, (e) => {
      e.preventDefault();
      el.classList.add('prism-drop-target');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    el.addEventListener(evt, (e) => {
      e.preventDefault();
      el.classList.remove('prism-drop-target');
    });
  });
  el.addEventListener('drop', _handleNdjsonDrop);
});
```

- [ ] **Step 4: 加 `_importNdjsonFile` 函数 (含空文件早返)**

`importFromFile` (app.js:1112) 是现有函数。本期重命名为 `_importNdjsonFile` (内部) 并加空文件早返。找到 `importFromFile` 整段, 改为:

```javascript
async function _importNdjsonFile(file) {
  const text = await file.text();
  if (!text || !text.trim()) {
    toast('文件为空, 无可导入', 'info');
    return { added: 0, total: 0, readLines: 0 };
  }
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  let n = 0;
  for (const line of lines) {
    try {
      const ev = JSON.parse(line);
      await fetch('/api/captures/inject', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(ev),
      });
      n += 1;
    } catch (_) { /* skip bad line */ }
  }
  state.capturesLocallyCleared = false;
  await _pullCaptures();
  const r = await _mergeCapturesIntoSteps();
  return { ...r, readLines: n };
}
```

> **向后兼容**: 保留 `importFromFile` 作为别名 (若有外部调用):
> ```javascript
> const importFromFile = _importNdjsonFile;
> ```

- [ ] **Step 5: 全局搜索 `importFromFile` 调用点, 改为 `_importNdjsonFile`**

```bash
cd "D:/M/ModelRegistry" && grep -n "importFromFile" gimbal/prism/static/app.js
```

预期: 旧 `importFromFile` 的唯一调用是 _importNdjsonFile 函数体已重命名, 以及别名为 `const importFromFile = _importNdjsonFile;` 那一行。无其它旧调用残留。

- [ ] **Step 6: 写测试 — 静态检查新行为**

Create: `tests/test_step_import_ux.py`

```python
"""空状态文件选择器 / 拖拽导入 / 空文件早返静态测试。"""
from __future__ import annotations

from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_old_import_btn_handler_removed():
    text = _read()
    assert "$('import-btn').addEventListener" not in text, \
        "应已删除旧 #import-btn click handler"


def test_old_import_path_drop_removed():
    text = _read()
    assert "import-path" not in text, "应已删除 import-path 引用"
    assert ".import-row" not in text, "应已删除 .import-row 引用"


def test_new_empty_state_triggers_file_picker():
    text = _read()
    assert "$('ndjson-file-input').click()" in text, \
        "空状态 click 应触发 $('ndjson-file-input').click()"
    assert "triggerFilePicker" in text, "应抽 triggerFilePicker 函数"
    # 键盘: Enter / Space
    assert "e.key === 'Enter' || e.key === ' '" in text, \
        "空状态应支持 Enter/Space 触发"


def test_file_input_change_validates_extension():
    text = _read()
    assert "_ndjsonInput.addEventListener('change'" in text, \
        "ndjson-file-input 应有 change 监听"
    assert "请选择 .ndjson 文件" in text, "非 .ndjson 应 toast 拒绝"
    assert "/\\.ndjson$/i.test(file.name)" in text, "应做后缀校验"


def test_drop_on_empty_state_and_step_main():
    text = _read()
    assert "_handleNdjsonDrop" in text, "应抽 drop handler"
    assert ".step-main" in text, "应绑定 .step-main 为 drop target"
    assert "prism-drop-target" in text, "应使用 prism-drop-target 视觉类"
    assert "请拖入 .ndjson 文件" in text, "拖入非 .ndjson 应 toast"


def test_empty_file_early_return():
    text = _read()
    assert "文件为空, 无可导入" in text, "空文件应早返并 toast"
    # _importNdjsonFile 内部 text trim 后判空
    assert "if (!text || !text.trim())" in text or "if (!text.trim())" in text, \
        "应检查 text.trim() 为空"


def test_import_from_file_alias_kept():
    """向后兼容: importFromFile 别名保留。"""
    text = _read()
    assert "const importFromFile = _importNdjsonFile" in text, \
        "应保留 importFromFile 别名以防外部调用"
```

- [ ] **Step 7: 跑测试 + 全套**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_step_import_ux.py -v && \
.venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -5
```

Expected: 7 passed in test_step_import_ux; 全套 190+ passed / 4 skipped。

- [ ] **Step 8: 提交**

```bash
cd "D:/M/ModelRegistry" && git add gimbal/prism/static/app.js tests/test_step_import_ux.py && \
  git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "feat(steps): empty-state click + drag-drop + file picker integration (.ndjson only)"
```

---

## Task 7: E2E 测试 — Step 分页行为 (HTTP + 静态 DOM 检查)

**Files:**
- Create: `tests/test_step_pagination.py`

**Interfaces:**
- 启动 FastAPI TestClient, 构造 25 个 step 的 draft, PUT 到 `/api/draft/test-sid`, 然后 GET `/`, 解析 HTML, 断言:
  - `#step-sidebar` 存在
  - 静态文件 `app.js` 含分页原语 + 3 个 sub-renderer
  - 验证 server 端 draft load 后, 客户端能从 draft 恢复 25 steps 进 state (我们直接用静态分析验证: app.js 的 `_loadDraftState` 仍把 server 的 steps 数组赋值给 `state.steps`)

> **测试方法**: 不依赖浏览器。E2E = HTTP-level E2E (FastAPI 启动 → 模拟用户操作 → 验证 state + 静态前端代码具备正确性)。完整 DOM 渲染验证留给手动 smoke test (Task 10)。

- [ ] **Step 1: 写测试 fixture — 25 个 step 的 draft payload**

Create: `tests/test_step_pagination.py`

```python
"""Step 分页 E2E 测试: HTTP 层面验证 draft 含 25 steps 时,
prism server 能正常 GET /, 前端 app.js 含分页原语。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _make_steps(n: int) -> list:
    return [
        {
            "id": f"step-{i+1}",
            "api": {"service": "https://api.example.com", "method": ["GET", "POST", "PUT"][i % 3], "path": f"/api/order/{i+1}"},
            "req": {"params": {}, "headers": {}, "body": {}},
            "assertions": [], "extracts": [], "assigns": [],
            "key_hint": f"call_{i+1}",
        }
        for i in range(n)
    ]


@pytest.fixture
def client():
    return TestClient(app)


def test_draft_with_25_steps_serves_ok(client):
    sid = "test-sid-25"
    draft = {
        "scenario_id": sid,
        "name": "test", "description": "", "module": "default",
        "priority": 1, "author": "prism", "owner": "prism",
        "tags": [], "version": "1.0.0", "expire": False,
        "requirement_ref": [], "services": {}, "users": [],
        "time_policy_kind": "record", "time_policy_seconds": 60,
        "retry_enabled": False, "retry_max_attempts": 3,
        "retry_backoff_seconds": 20, "retry_on": [],
        "setup_refs": [], "teardown_refs": [],
        "resources": [], "steps": _make_steps(25),
    }
    r = client.put(f"/api/draft/{sid}", json=draft)
    assert r.status_code == 200, r.text
    r2 = client.get(f"/configure?session={sid}")
    assert r2.status_code == 200
    # 验证 HTML 含新结构
    body = r2.text
    assert 'id="step-sidebar"' in body
    assert 'id="step-tags"' in body
    assert 'id="step-detail"' in body
    assert 'id="ndjson-file-input"' in body
    # 旧结构应已不在
    assert 'id="import-btn"' not in body
    assert 'id="expand-all"' not in body
    assert 'id="collapse-all"' not in body


def test_draft_with_0_steps_keeps_no_sidebar(client):
    sid = "test-sid-0"
    draft = {
        "scenario_id": sid, "name": "empty", "description": "",
        "module": "default", "priority": 1, "author": "prism", "owner": "prism",
        "tags": [], "version": "1.0.0", "expire": False,
        "requirement_ref": [], "services": {}, "users": [],
        "time_policy_kind": "record", "time_policy_seconds": 60,
        "retry_enabled": False, "retry_max_attempts": 3,
        "retry_backoff_seconds": 20, "retry_on": [],
        "setup_refs": [], "teardown_refs": [], "resources": [], "steps": [],
    }
    r = client.put(f"/api/draft/{sid}", json=draft)
    assert r.status_code == 200
    r2 = client.get(f"/configure?session={sid}")
    assert r2.status_code == 200
    # 空 draft 仍能 serve, sidebar 容器存在 (运行时 hidden)
    body = r2.text
    assert 'id="step-sidebar"' in body


def test_app_js_loads_draft_into_state_steps():
    """客户端从 draft 加载 steps 的逻辑必须保留。"""
    text = APP_JS.read_text(encoding="utf-8")
    # draft.step_ids 或 draft.steps 赋值给 state.steps
    assert "state.steps =" in text, "app.js 必须从 draft 加载 state.steps"
    # step 渲染路径走 renderStepTags (新增)
    assert "renderStepTags()" in text


def test_page_size_ten():
    text = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"PAGE_SIZE\s*=\s*(\d+)", text)
    assert m
    assert int(m.group(1)) == 10
```

- [ ] **Step 2: 跑测试**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_step_pagination.py -v
```

Expected: 4 passed。

- [ ] **Step 3: 全套 + 提交**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -5 && \
git add tests/test_step_pagination.py && \
git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "test(steps): add E2E test for Step pagination (HTTP-level + static DOM)"
```

---

## Task 8: E2E 测试 — 导入流程 (HTTP-level 模拟 .ndjson 注入)

**Files:**
- Create: `tests/test_step_import_e2e.py`
- Create: `tests/fixtures/sample_captures.ndjson` (测试数据)

**Interfaces:**
- 启动 FastAPI TestClient, 模拟 `_importNdjsonFile` 的服务端流程: POST `/api/captures/inject` 多次 (line-by-line), 然后 GET `/api/captures` 验证 server 收到所有事件, 最后 PUT 一个含捕获派生 step 的 draft 验证 state。

- [ ] **Step 1: 创建 NDJSON 测试 fixture**

Create: `tests/fixtures/sample_captures.ndjson`

```json
{"ts": 1718678400.0, "method": "POST", "host": "api.example.com", "scheme": "https", "port": 443, "path": "/api/login", "query": {}, "headers": {"Content-Type": "application/json"}, "body": "{\"user\":\"alice\",\"pwd\":\"x\"}", "response": {"status": 200}, "response_ms": 120}
{"ts": 1718678401.0, "method": "GET", "host": "api.example.com", "scheme": "https", "port": 443, "path": "/api/order/1", "query": {}, "headers": {}, "body": "", "response": {"status": 200}, "response_ms": 50}
{"ts": 1718678402.0, "method": "GET", "host": "api.example.com", "scheme": "https", "port": 443, "path": "/api/order/2", "query": {}, "headers": {}, "body": "", "response": {"status": 404}, "response_ms": 5}
```

- [ ] **Step 2: 写测试**

Create: `tests/test_step_import_e2e.py`

```python
"""导入流程 E2E 测试: 模拟 .ndjson 文件被 _importNdjsonFile 处理,
验证 server 端 captures 累计 + 客户端能从 captures 派生 steps。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gimbal.prism.server import app

FIXTURE = Path("D:/M/ModelRegistry/tests/fixtures/sample_captures.ndjson")


@pytest.fixture
def client():
    return TestClient(app)


def test_ndjson_fixture_loads():
    """fixture 文件存在且可解析。"""
    assert FIXTURE.exists(), f"fixture 缺失: {FIXTURE}"
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    for line in lines:
        ev = json.loads(line)
        assert "method" in ev and "path" in ev


def test_captures_inject_and_list(client):
    """模拟 _importNdjsonFile 行为: 逐行 POST /api/captures/inject, 然后 GET 列表。"""
    sid = "import-e2e-sid"
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    n_ok = 0
    for line in lines:
        ev = json.loads(line)
        r = client.post(f"/api/captures/inject?sid={sid}", json=ev)
        assert r.status_code == 200, r.text
        n_ok += 1
    assert n_ok == 3, f"应注入 3 条, 实际 {n_ok}"
    r = client.get(f"/api/captures?sid={sid}")
    assert r.status_code == 200
    data = r.json()
    assert len(data.get("events", [])) == 3, f"server 端应有 3 条, 实际 {len(data.get('events', []))}"


def test_app_js_import_from_file_uses_inject_endpoint():
    """app.js 内的 _importNdjsonFile 必须 POST /api/captures/inject。"""
    app_js = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")
    text = app_js.read_text(encoding="utf-8")
    assert "await fetch('/api/captures/inject'" in text, \
        "_importNdjsonFile 必须调 /api/captures/inject"
    assert "JSON.parse(line)" in text, "应逐行 JSON 解析"
    # 校验后缀
    assert "/\\.ndjson$/i.test(file.name)" in text, "应做 .ndjson 后缀校验"
    # 空文件早返
    assert "文件为空" in text, "空文件应 toast"


def test_draft_persistence_with_imported_steps(client):
    """导入后构造 draft 包含 3 个 step (与 fixture 一一对应), PUT/GET 验证。"""
    sid = "import-e2e-draft"
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").split("\n") if l.strip()]
    steps = []
    for i, line in enumerate(lines):
        ev = json.loads(line)
        steps.append({
            "id": f"step-{i+1}",
            "api": {
                "service": f"{ev.get('scheme', 'https')}://{ev.get('host', 'api.example.com')}",
                "method": ev["method"], "path": ev["path"],
            },
            "req": {"params": ev.get("query", {}),
                    "headers": ev.get("headers", {}),
                    "body": ev.get("body", {})},
            "assertions": [], "extracts": [], "assigns": [],
            "key_hint": "",
            "capture": ev,
        })
    draft = {
        "scenario_id": sid, "name": "imported", "description": "",
        "module": "default", "priority": 1, "author": "prism", "owner": "prism",
        "tags": [], "version": "1.0.0", "expire": False,
        "requirement_ref": [], "services": {}, "users": [],
        "time_policy_kind": "record", "time_policy_seconds": 60,
        "retry_enabled": False, "retry_max_attempts": 3,
        "retry_backoff_seconds": 20, "retry_on": [],
        "setup_refs": [], "teardown_refs": [],
        "resources": [], "steps": steps,
    }
    r = client.put(f"/api/draft/{sid}", json=draft)
    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/draft/{sid}")
    assert r2.status_code == 200
    data = r2.json()
    assert len(data["steps"]) == 3
    assert data["steps"][0]["api"]["path"] == "/api/login"
```

- [ ] **Step 3: 跑测试 + 全套 + 提交**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/test_step_import_e2e.py -v && \
.venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -5 && \
git add tests/test_step_import_e2e.py tests/fixtures/sample_captures.ndjson && \
git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "test(steps): add E2E test for .ndjson import flow + step persistence"
```

---

## Task 9: 文档同步 (USER_MANUAL.md + CHANGELOG.md)

**Files:**
- Modify: `USER_MANUAL.md:298-319` (§5.2 Web UI 表格中 Steps Tab 描述)
- Modify: `CHANGELOG.md` (顶部追加 v0.5.5 条目)

- [ ] **Step 1: 改 `USER_MANUAL.md` §5.2 表格**

打开 `USER_MANUAL.md`, 定位到第 307 行 (Steps Tab 描述)。把:

```
| ④ | Steps | 步骤列表:method pill + 路径 + 折叠/展开 + cURL 复制 + strategy 编辑（断言/提取/赋值） |
```

改为:

```
| ④ | Steps | **分页布局**: 左侧 1-10/11-20 侧栏 + 右侧 step 标签流 (method + path)。**空状态可点击** 弹出 .ndjson 文件选择器, 也支持拖入 .ndjson。点击 tag 展开完整编辑 (API/Request/Strategy 三子 tab)。 |
```

- [ ] **Step 2: 加 v0.5.5 章节到 USER_MANUAL §5.2 末尾**

在第 5.2 节最后 (第 5.2.1 之前) 追加:

```markdown
#### 5.2.5 v0.5.5 Step 分页 + 文件选择器（v0.5.5 起）

**新增**:
- 左侧垂直侧栏按 10 个一组显示 `1-10`, `11-20`, ... (鼠标 hover 高亮, 点击切换)
- 右侧横向 tag 流, 每 tag 仅显示 method pill + path, hover 出现删除 × 按钮
- 展开/收起: 点 tag → 下方展开完整 step 编辑面板 (API/Request/Strategy 三子 tab), 再点同一 tag 收起
- 拖拽重排: 拖 tag 在当前页 10 个内重排
- 拖入 `.ndjson` 到 step 区域 / 空状态框触发导入 (限定 .ndjson 后缀)

**删除**:
- 「全部展开」/「全部折叠」按钮 (单展开手风琴替代)
- 步骤导入行 (输入框 + 导入按钮); 改由空状态框点击弹出文件选择器
- `.json` 文件导入支持 (v0.5.5 起只接受 `.ndjson`)

**自动跳转**: 删除 step 后, 若 `currentPage` 越界, 自动跳到最后一页有效页码。
```

- [ ] **Step 3: 改 `CHANGELOG.md` 加 v0.5.5 条目**

打开 `CHANGELOG.md`, 在文件最顶部 (或第一个 v0.5.x 条目之上) 追加:

```markdown
## v0.5.5 (2026-06-23) — Step 分页 + 空状态文件选择器

**新增**:
- Step Tab 改版: 左侧 1-10/11-20/... 分页侧栏 + 右侧 10 个 step 的横向 tag 流 (method + path)
- 空状态框可点击, 弹出 .ndjson 文件选择器; 拖拽 .ndjson 到 step 区域 / 空状态框也触发导入
- 标签风格 step 卡片, 单展开手风琴 (同时只展开一个)
- `_syncStepPagination` + `_computePageRanges` 派生原语; PAGE_SIZE = 10 硬编码常量
- 跨页守卫: 拖拽重排仅在当前页 10 个内有效

**删除**:
- 「全部展开」/「全部折叠」按钮
- 步骤导入行 (输入框 + 按钮), 改由空状态框触发
- `.json` 文件导入支持 (v0.5.5 起只接受 `.ndjson`)

**保留 (向后兼容)**:
- `/api/captures/import-from-path` 后端端点保留
- `state.expandedSteps` / `state.collapsedSteps` Set 字段保留 (供 undo/redo 历史栈 serialize 兼容)
- `importFromFile` 函数作为 `_importNdjsonFile` 的别名保留

**测试**: 198 passed / 4 skipped (165 baseline + 33 new)

详见 `docs/superpowers/specs/2026-06-23-step-pagination-and-import-design.md`。
```

- [ ] **Step 4: 跑全套 + 提交**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -5 && \
git add USER_MANUAL.md CHANGELOG.md && \
git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "docs: USER_MANUAL + CHANGELOG updates for v0.5.5 Step pagination"
```

---

## Task 10: 手动 smoke test + 视觉验收

**Files:** (无文件改动, 仅手动)

**执行步骤**:

- [ ] **Step 1: 启动 prism server**

```bash
cd "D:/M/ModelRegistry" && .venv/Scripts/python.exe -m gimbal prism start --port 8765
```

打开浏览器 <http://127.0.0.1:8765>。

- [ ] **Step 2: 验证空状态**

- 切到 Steps tab
- 期望: 显示「尚无 Step — 点击导入 .ndjson (拖入 .ndjson 也可)」, hover 时背景变浅、整体上移 1px

- [ ] **Step 3: 验证空状态点击**

- 点击空状态框
- 期望: 弹出系统文件选择器, 文件类型下拉默认只列 `.ndjson`
- 选一个非 .ndjson 文件 → 期望: toast「请选择 .ndjson 文件」(红色, 3s)
- 选一个有效 .ndjson (例如 `tests/fixtures/sample_captures.ndjson`) → 期望: 3 个 step 出现在侧栏 1-10, tag 流显示 3 个 tag

- [ ] **Step 4: 验证分页侧栏**

- 关闭 server
- 启动一个 fixture 脚本, 构造 25 个 step 的 draft (用 `tests/test_step_pagination.py` 的 `_make_steps(25)`), 通过 `PUT /api/draft/test-sid-25` 写入, 然后访问 `/configure?session=test-sid-25`
- 期望:
  - 侧栏有 `1-10`, `11-20`, `21-30` 三项, 当前页 `1-10` 高亮 (紫色背景)
  - 右侧显示 10 个 tag (方法名 + 路径)
  - 点 `11-20` → 10 个 tag 替换为 step 11-20, 侧栏 `11-20` 高亮
  - 点 `1-10` → 回到 step 1-10

- [ ] **Step 5: 验证 tag 点击展开**

- 点 `1-10` 页的某个 tag (例如 step 5)
- 期望: 该 tag 变高亮 (浅紫底), 下方出现完整 step 编辑面板 (API/Request/Strategy 三个子 tab)
- 点同一个 tag → 面板收起
- 点另一个 tag (例如 step 7) → step 5 面板自动收起, step 7 面板展开 (单展开手风琴)

- [ ] **Step 6: 验证 detail 编辑**

- 展开 step 5
- 改 method 下拉为 DELETE → 期望: 顶栏 method pill 立即变红, path 文本不变
- 改 path 输入 → 期望: 顶栏 path 文本 + seq 编号立即更新
- 切到 Request 子 tab → 期望: 看到 params / body / headers 三个 textarea
- 在 body 里输入 `{"x": 1}` → 期望: 输入合法, 状态指示器不变
- 在 body 里输入 `{` 不闭合 → 期望: 状态变红 + toast「JSON 解析失败: body」

- [ ] **Step 7: 验证删除**

- 关闭 detail 面板
- hover step 3 的 tag → 期望: 右侧出现红色 × 按钮
- 点 × → 期望: 弹 confirmModal 「确定删除 Step 3 (POST /api/order/3)?」
- 确认 → 期望: tag 消失, step 总数变 24, 侧栏仍 3 页 (1-10, 11-20, 21-30), 因为 24 > 20

- [ ] **Step 8: 验证越界自动跳**

- 当前在 `11-20` 页, 删除 step 12-30 (共 19 个)
- 期望: 删除后侧栏只剩 `1-5`, currentPage 自动跳到 `1-5`, 显示 5 个 tag

- [ ] **Step 9: 验证拖拽重排**

- 回到有 10+ step 的状态
- 拖 step 5 的 tag 拖到 step 8 的位置
- 期望: 释放后, 步骤顺序变 step 1,2,3,4,**8,5**,6,7,9,10 (step 5 和 step 8 交换)
- 尝试拖到 `21-30` 页 (跨页) → 期望: 跨页不允许, 视觉上无 drag-over 高亮到侧栏

- [ ] **Step 10: 验证拖入文件**

- 拖一个 `.ndjson` 文件到 step 区域中央 → 期望: 整个 step 区域出现紫色虚线 outline (`.prism-drop-target` 高亮)
- 松手 → 期望: toast「拖入完成:读取 N 条,新增 M 个 Step」 (复用 `importFromFile` 的 toast 格式)

- [ ] **Step 11: 验证「实时捕获」面板**

- 启动 `gimbal capture start --session v055 --port 8080`
- 浏览器代理到 8080, 浏览一个页面
- 切回 prism Steps tab → 期望: 「实时捕获」面板折叠 / 展开, 列表里有新 capture
- 勾上「自动注入 step」→ 期望: 新 capture 实时变成 step tag, 侧栏自动新增页码

- [ ] **Step 12: 验证 4 Tab 视觉一致性**

- 切到元信息 / 配置 / 资源 tab, 视觉风格应与 v0.5.3 一致 (无新 CSS 变量 / 字体)

- [ ] **Step 13: 视觉验收总结**

记录 (口头 / 评论) 任何与预期不符的视觉差异。常见差异:
- 侧栏宽度不够 → 改 `grid-template-columns: 96px 1fr` 为 `110px 1fr`
- tag 太大 / 太小 → 改 `.step-tag` padding 或 font-size
- 视觉对比度不够 → 调 `.step-tag.active` 颜色

- [ ] **Step 14: 提交 smoke 报告 (如有视觉修正)**

如果发现视觉问题并修改, 提交:
```bash
cd "D:/M/ModelRegistry" && git add gimbal/prism/static/style.css && \
git -c user.email="claude@anthropic.com" -c user.name="claude" \
  commit -m "fix(steps): visual adjustments from manual smoke test"
```

若无视觉问题, 无 commit。

- [ ] **Step 15: 关闭 server, 任务完成**

```bash
# Ctrl+C 关闭 prism / capture
```

---

## Self-Review Checklist (执行人请逐项核对)

> 实施过程中, 实施人应在每个 Task 完成后勾选对应 step。

- [ ] Task 1 完成后: state shape + 分页原语就绪
- [ ] Task 2 完成后: index.html 结构改造完成, test_frontend_v1 通过
- [ ] Task 3 完成后: CSS 新类就绪, 无新 token
- [ ] Task 4 完成后: renderSteps 拆分为 3 个子渲染器, 现有调用点不受影响
- [ ] Task 5 完成后: tag 删除 + 拖拽重排生效
- [ ] Task 6 完成后: 空状态 / 拖拽 / 文件选择器集成, 旧 import-btn handler 已删
- [ ] Task 7 完成后: HTTP-level E2E 测试通过
- [ ] Task 8 完成后: 导入流程 E2E 测试通过
- [ ] Task 9 完成后: USER_MANUAL + CHANGELOG 同步
- [ ] Task 10 完成后: 手动 smoke test 通过, 视觉与 v0.5.3 一致

**最终验收**: 全套 pytest 通过 (198+ passed / 4 skipped), 手动 smoke 10 步全过, v0.5.5 可发布。
