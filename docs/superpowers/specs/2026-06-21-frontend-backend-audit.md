# 前后端业务流审计报告

> **日期**：2026-06-21
> **范围**：gimbal prism v0.5 (PR1SM 前端 + 适配后端)
> **方法**：列出所有前端用户操作 → 对应后端端点 → 数据模型契约 → 找出不对齐

---

## 1. 端点契约矩阵（前端操作 → 后端端点）

| # | 前端操作 | 端点 | 方法 | 状态 |
|---|---|---|---|---|
| 1 | 启动时 detectSession (URL/meta) | `/configure?session=...` | GET | ✅ HTML 注入 sid |
| 2 | 启动时 loadDraft | `/api/draft/{sid}` | GET | ✅ |
| 3 | 自动保存 (debounce 800ms) | `/api/draft/{sid}` | PUT | ✅ |
| 4 | Ctrl+S 立即保存 | `/api/draft/{sid}` | PUT | ✅ |
| 5 | undo/redo (本地 stack) | 无 | — | ✅ 纯前端 |
| 6 | meta 字段编辑 | PUT 草稿 | — | ✅ |
| 7 | tags 增删拖拽 | PUT 草稿 | — | ✅ |
| 8 | services 增删拖拽 | PUT 草稿 | — | ✅ |
| 9 | users 增删 + 密码脱敏 | PUT 草稿 | — | ✅ |
| 10 | timePolicy / retry 改 | PUT 草稿 | — | ✅ |
| 11 | resources 增删 | PUT 草稿 | — | ✅ |
| 12 | step 增 (来自 captures) | 通过 captures WS/inject → 推到 steps | — | ⚠️ 见 §3.1 |
| 13 | step 删 | 删 state.steps[i] | — | ⚠️ 见 §3.1 |
| 14 | step 拖拽重排 | splice state.steps | — | ⚠️ 见 §3.1 |
| 15 | step 折叠/展开 | 本地 Set | — | ✅ 纯前端 |
| 16 | step 编辑 api.method/path | 改 state.steps[i].api | — | ⚠️ **见 §3.2** |
| 17 | step 编辑 req (params/headers/body) | 改 state.steps[i].req | — | ⚠️ **见 §3.2** |
| 18 | strategy editor (assertions/extracts/assigns) | 改 state.steps[i].{assertions,extracts,assigns} | — | ⚠️ **见 §3.2** |
| 19 | step 编辑 key_hint | 改 state.steps[i].key_hint | — | ⚠️ **见 §3.2** |
| 20 | cURL 复制 | 纯前端 | — | ✅ |
| 21 | import captures (路径) | `/api/captures/import-from-path` | POST | ✅ |
| 22 | import captures (拖拽文件) | `/api/captures/inject` × N | POST | ✅ |
| 23 | captures 实时推送 | `/ws/captures?sid=` | WS | ✅ |
| 24 | clear captures | `/api/captures` | DELETE | ✅ |
| 25 | YAML 预览 | `/api/draft/{sid}/yaml` | POST | ✅ |
| 26 | YAML 导出 | `/api/draft/{sid}/export` | POST | ✅ |
| 27 | help modal | 纯前端 | — | ✅ |
| 28 | toast | 纯前端 | — | ✅ |

**结论**：28 个操作中，**24 个 ✅，4 个 ⚠️**（全部在 step 持久化路径上）。

---

## 2. 数据模型契约

### 2.1 Wire 格式（`DraftIn`）字段

```python
class DraftIn(BaseModel):
    scenario_id, name, description, module, priority,
    author, owner, tags, version, expire, requirement_ref
    services: dict[str, str]   # alias → URL
    users: list[UserIn]        # {key, url, username, password, expires_in, token_type, token, confirm_password}
    time_policy_kind, time_policy_seconds
    retry_enabled, retry_max_attempts, retry_backoff_seconds, retry_on
    setup_refs, teardown_refs
    resources: list[dict]      # {name, kind, image, config, port_mapping, path, ref, value}
    step_ids: list[str]        # 字符串索引列表
```

### 2.2 缺失字段

`DraftIn` **没有** `steps` 字段，没有 `key_hint`，没有 `assertions`，没有 `extracts`，没有 `assigns`，没有 `api`/`req` 覆盖。

### 2.3 `_draft_from_in` 行为

```python
all_events = capture_reader.read(session_id, limit=None)  # 从文件读
id_to_event = {str(i): e for i, e in enumerate(all_events)}
steps: list[StepDraft] = []
for sid in payload.step_ids:
    if sid in id_to_event:
        steps.append(StepDraft(capture=id_to_event[sid]))  # 裸 StepDraft,无任何自定义
```

→ 后端用 step_ids 索引 captures 文件，**完全丢弃**任何 step 级别自定义。

---

## 3. 严重 Gap 详解

### 3.1 ⚠️ Gap #1: `step_ids` 来源错误

**位置**：`gimbal/prism/static/app.js:1221`

```js
// 当前代码:
step_ids: state.captures.map((_, i) => String(i)),
```

**问题**：
- `state.captures` 是 WS 推送的事件列表（**只增不删**）
- `state.steps` 才是用户编辑过的步骤
- 两者**不同步**：
  - 用户删 step → `state.steps` 变短但 `state.captures` 不变 → step_ids 仍指向 captures 索引
  - 用户拖拽重排 step → `state.steps` 顺序变了但 `state.captures` 顺序没变 → step_ids 反映的是 captures 顺序

**后果**：
- 拖拽重排 **无效**（保存后 backend 按 captures 顺序索引）
- 删 step **无效**（backend 仍按 step_ids 索引到 captures）

**修复方向**：
```js
// 方案 A: 用 state.steps 索引
step_ids: state.steps.map((s) => s.capture 
  ? `${state.captures.indexOf(s.capture)}`  // 反查 captures 索引
  : s.__sid)
```
但 A 仍受 3.2 影响（自定义字段丢失）。

### 3.2 ⚠️ Gap #2: Step 自定义字段**全部丢失**

**位置**：`gimbal/prism/static/app.js:1194-1223` (serializeDraft)

**Step 在前端有这些字段**（`state.steps[i]`）：
```js
{
  capture: {...},                  // 原始 capture
  api: {service, method, path},     // ← 用户可覆盖
  req: {params, headers, body},     // ← 用户可覆盖
  assertions: [...],                // ← strategy editor
  extracts: [...],
  assigns: [...],
  key_hint: '...',                  // ← 用户命名
  __sid: 'step-xxx',                // 本地 id
}
```

**serializeDraft 不发送上述任何字段**，只发 `step_ids`（标量字符串列表）。

**Wire 格式 `DraftIn` 也不接收这些字段**。

**后果**：
- 用户在 step 卡片里改的 `api.method = 'PUT'` → 保存后**丢失**
- 用户加的 assertion (e.g. `eq status 200`) → **丢失**
- 用户加的 extract (e.g. `extract token from response.body.token`) → **丢失**
- 用户命名 `key_hint = 'login_step'` → **丢失**
- 导出的 YAML 只包含 captures 原始信息，**不包含任何用户编辑**

**验证**（在导出 YAML 里看 `steps` 段）：
```yaml
steps:
  - capture:           # 仅原始 capture
      method: GET
      path: /api/...
    # 没有 api/req/assertions/extracts/assigns/key_hint
```

### 3.3 ⚠️ Gap #3: `get_draft` 永远返回空 `steps`

**位置**：`gimbal/prism/server.py:374`

```python
@app.get("/api/draft/{session_id}")
def get_draft(request: Request, session_id: str) -> dict[str, Any]:
    return _ensure_session(session_id)

def _ensure_session(session_id: str) -> dict:
    if session_id not in sessions:
        sessions[session_id] = {
            "draft": DraftIn().model_dump(),  # ← 全默认
        }
    return sessions[session_id]
```

**问题**：
- 保存后 `state.steps` 改不了（因为 saveDraft 也不发 steps）
- 重新加载时 `state.steps = d.steps` = `[]`
- 用户看到空 Steps tab，必须重新 import captures

---

## 4. Minor Gap

### 4.1 Minor: `clear_captures` 后 step_ids 错位

DELETE `/api/captures` → 服务端 captures 文件清空 → 下次 loadDraft 拉空 captures → 前端 `state.captures = []` → `step_ids = []`。OK。

但**中间状态**：用户 clear captures 后立即保存（不 refresh），`state.captures` 仍非空（locally cleared 标记），`step_ids` 仍非空 → backend 用空 captures 文件 + 非空 step_ids → 全空 steps。OK 但反直觉。

### 4.2 Minor: `locally_cleared` 标记未持久化

前端 `state.capturesLocallyCleared` 是 UI-only 标记，刷新后丢失。重新连接 WS 时会重新灌入。

---

## 5. PR1SM 原版 vs gimbal 行为差异

PR1SM 的 server.py 也是同样的设计：
- `_draft_from_in` 用 step_ids 索引 capture 文件
- wire 格式只有 step_ids，没有 steps 自定义

**所以这些 gap 是 PR1SM 原版就有的**，不是 v0.5 引入。但 v0 老的声明式 schema 渲染前端也未提供 step 级别编辑（只有 capture 列表），所以 v0 没暴露这个问题。

**v0.5 引入新前端后**（带 step 卡片 + strategy editor），这些 gap 第一次被用户感知到。

---

## 6. 修复优先级

| 优先级 | Gap | 修复方案 |
|---|---|---|
| **P0** | #2 step 自定义字段丢失 | 改 `DraftIn` 加 `steps: list[dict]`, serializeDraft 发 steps 完整对象, `_draft_from_in` 用 payload.steps |
| **P1** | #1 step_ids 错位 | 同上 (P0 修了之后, step_ids 概念可废弃) |
| **P2** | #3 get_draft 返空 steps | 跟随 P0 修复 (loadDraft 拿到 draft.steps 直接用) |
| P3 | #4.1 clear_captures UX | 文档化行为 |
| P3 | #4.2 locally_cleared 持久化 | localStorage 暂存 |

---

## 7. 端到端验证 (P0 修复前)

**当前实际表现**（用户视角）：
1. ✅ 启动 prism，看到 4 tab 视觉规范
2. ✅ 元信息 / 配置 / 资源 编辑正常保存
3. ✅ captures 通过 WS 实时推送，badge 数量更新
4. ✅ 导入 captures 后，Steps tab 自动出现 step 卡片
5. ❌ 改 step.api.method → 保存 → 刷新 → **改回原值**
6. ❌ 加 assertion → 保存 → 导出 YAML → **看不到 assertion**
7. ❌ 拖拽 step 重排 → 保存 → 刷新 → **顺序回到 captures 顺序**
8. ✅ YAML 导出文件可写，路径返回正确
9. ✅ 密码脱敏（confirm_password=False → `<REDACTED>`）

**P0 修复前 v0.5 不可用于生产**（用户编辑的 step 字段全丢）。

---

## 8. 建议下一步

**选项 A（推荐）**: 立即修 P0，加 1 个端点 + 改 1 个 model
- 改 `DraftIn` 加 `steps: list[dict[str, Any]]`
- 改 `serializeDraft` 发 `state.steps` 完整对象
- 改 `_draft_from_in` 用 payload.steps 直接构造，不再从文件读
- 改 `ScenarioDraft.steps` 类型接受自定义字段
- 改 `StepDraft` 加 `key_hint`, `assertions`, `extracts`, `assigns`, `api_override`, `req_override`

**选项 B（v0.6 再说）**: 当前版本标注"v0.5-preview"，禁用 step 级别编辑，只保留 capture → YAML 导出
- 前端 `renderSteps` 去掉 api/req/strategy 编辑 tab
- 或在 strategy editor 弹 modal 时显示 "v0.6 才支持保存"

**选项 C（回滚）**: 保留 v0 声明式前端（不替换），不引入此问题
- 失去 PR1SM 视觉规范
- 但保持"所见即所得"的稳定性
