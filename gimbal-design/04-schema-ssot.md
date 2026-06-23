# 04 · schema 单源化(SSOT)与 UI 注解体系

> 本文档描述 schema 作为 gimbal 平台**单一事实源**(SSOT)的设计:UI 注解体系、`/api/schema/ui-spec` 序列化、前端声明式渲染、dot-path 白名单生成。

---

## 1. 设计目标

### 1.1 现状:多处重复定义

| 字段名 | 出现位置 |
|---|---|
| `meta.name` / `meta.priority` / `meta.tags` / `timePolicy.kind` / `retry.enabled` / ... | `d:/mirror/schema/*.py`(权威) |
| 同样字段,顶层 snake_case | `d:/mirror/prism/server.py:150 DraftIn` |
| 同样字段,HTML id | `d:/mirror/prism/static/index.html:m-name` / `tp-kind` / ... |
| 同样字段,endpoint/auth/template 选项 | D:/M/ModelRegistry 的 `EndpointSpec` 等 dataclass(本次引入 `gimbal/contracts/ModelRegistry/`) |
| 同样字段,camelCase dot-path | `d:/mirror/prism/ai/tools.py:52 PATH_TO_FIELD`(`gimbal/prism/ai/` v0 删除,本表自动派生留 v0.1+) |
| 同样字段,自然语言描述 | `d:/mirror/prism/ai/prompts.py:15 SCHEMA_SUMMARY`(同上,v0 删除) |

**问题**:改 schema 后多处都得手动同步,容易遗漏。

### 1.2 目标

让 schema 成为**唯一权威定义**:
- 后端校验 / wire 序列化:直接 `from gimbal.schema import ...`(已具备)
- 前端字段渲染:从 schema 序列化 `/api/schema/ui-spec`,前端声明式消费(**本设计做**)
- 前端下拉/选项:从 ModelRegistry 序列化 `/api/registry/ui-spec`,前端消费(**本设计做**)
- dot-path 白名单端点:`/api/schema/dot-paths` 暴露只读路径(供未来 AI 工具 / 表单校验)

### 1.3 v0 范围

| 做 | 不做(后续 v0.1+) |
|---|---|
| ✅ schema 加 UI 注解(`ui=Field(...)`) | ❌ PATH_TO_FIELD 自动派生(原 AI 用) |
| ✅ `/api/schema/ui-spec` 端点 | ❌ AI 助手本身(用户明确"先不考虑 AI") |
| ✅ `/api/schema/dot-paths` 端点(只读,供未来使用) | ❌ SCHEMA_SUMMARY 自动生成(原 AI 用) |
| ✅ 前端声明式渲染引擎 | |
| ✅ Dot-path 白名单端点 | |
| ✅ `/api/registry/ui-spec` 端点(ModelRegistry → 下拉) | |

---

## 2. UI 注解体系

### 2.1 注解位置

Pydantic v2 推荐用 `Field(..., json_schema_extra={...})` 携带 UI 元数据。我们选用更直观的 `Field(..., ui={...})`,因为 `ui` 不与 JSON schema 输出冲突。

```python
# gimbal/schema/__init__.py(添加)
from typing import Any
from pydantic import Field

# 向 Field 注入 ui 参数支持
_orig_field = Field


def Field(  # type: ignore[no-redef]
    default: Any = ...,
    *,
    ui: dict[str, Any] | None = None,
    **kwargs,
):
    """在 pydantic.Field 基础上增加 ui 参数。

    ui 字典不进入 model_dump,只通过 model_json_schema() 的 ref 派生 UI spec。
    """
    if ui is not None:
        kwargs["json_schema_extra"] = {**(kwargs.get("json_schema_extra") or {}), "ui": ui}
    return _orig_field(default, **kwargs)
```

### 2.2 注解键集合(v0 限定 8 个)

| 键 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `widget` | `str` | 渲染控件类型 | `"input"` / `"textarea"` / `"select"` / `"number"` / `"toggle"` / `"tags"` / `"kv-list"` / `"step-list"` / `"resource-tile"` |
| `label` | `str` | UI 显示名(默认用字段名 camelCase 转 Title Case) | `"用例名"` |
| `placeholder` | `str` | 占位提示 | `"请输入用例名"` |
| `help` | `str` | 字段下方说明文字 | `"必填,空字符串会被 schema 拒绝"` |
| `required` | `bool` | 是否必填(前端校验,不替代 schema) | `true` |
| `options` | `list[{value, label}]` | select 候选项 | `[{value: 1, label: "1 (最高)"}, ...]` |
| `min` / `max` | `int` / `float` | number 范围 | `1` / `100` |
| `group` | `str` | 归属分组(决定 tab) | `"meta"` / `"config"` / `"timePolicy"` / `"retry"` |

### 2.3 示例:Meta 完整 UI 注解

```python
# gimbal/schema/scenario.py(v0)
from pydantic import BaseModel, ConfigDict
from typing import Annotated
from .__init__ import Field  # 上面定义的包装版


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarioId: Annotated[str, Field(
        "sc_new",
        ui={"widget": "input", "label": "scenarioId", "readonly": True, "group": "meta"},
    )]

    name: Annotated[str, Field(
        "",
        min_length=1,
        ui={"widget": "input", "label": "用例名", "required": True,
            "placeholder": "请输入用例名", "group": "meta"},
    )]

    description: Annotated[str, Field(
        "", ui={"widget": "textarea", "label": "用例描述", "rows": 2, "group": "meta"},
    )]

    module: Annotated[str, Field(
        "default", ui={"widget": "input", "label": "module", "group": "meta"},
    )]

    priority: Annotated[int, Field(
        1, ge=1, le=3,
        ui={"widget": "select", "label": "优先级", "options": [
            {"value": 1, "label": "1 (最高)"},
            {"value": 2, "label": "2"},
            {"value": 3, "label": "3"},
        ], "group": "meta"},
    )]

    author: Annotated[str, Field("prism", ui={"widget": "input", "group": "meta"})]
    owner: Annotated[str, Field("prism", ui={"widget": "input", "group": "meta"})]

    tags: Annotated[list[str], Field(
        default_factory=list,
        ui={"widget": "tags", "label": "tags",
            "hint": "回车/逗号添加 · 拖动重排", "group": "meta"},
    )]

    version: Annotated[str, Field("1.0.0", ui={"widget": "input", "group": "meta"})]
    expire: Annotated[bool, Field(False, ui={"widget": "toggle", "group": "meta"})]

    requirementRef: Annotated[list[str], Field(
        default_factory=list,
        ui={"widget": "tags", "label": "requirementRef",
            "hint": "需求 ID,如 REQ-123", "group": "meta"},
    )]
```

### 2.4 示例:TimePolicy / RetryPolicy

```python
# gimbal/schema/timepolicy.py(v0)
class RecordPolicy(TimePolicy):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["record"] = "record"


class TimeoutPolicy(TimePolicy):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["timeout"] = "timeout"
    seconds: Annotated[int, Field(
        60, ge=1,
        ui={"widget": "number", "label": "seconds", "min": 1, "unit": "秒",
            "show_if": {"path": "kind", "equals": "timeout"}},
    )]


TimePolicyUnion = Annotated[
    Union[RecordPolicy, TimeoutPolicy],
    Field(discriminator="kind", ui={"widget": "select", "label": "kind",
                                     "options_from": "kind"}),
]


# gimbal/schema/retrypolicy.py(v0)
class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Annotated[bool, Field(
        False, ui={"widget": "toggle", "label": "retry"},
    )]
    maxAttempts: Annotated[int, Field(
        3, ge=1,
        ui={"widget": "number", "show_if": {"path": "enabled", "equals": True}},
    )]
    backoffSeconds: Annotated[float, Field(
        20.0, ge=0,
        ui={"widget": "number", "unit": "s", "show_if": {"path": "enabled", "equals": True}},
    )]
    retryOn: Annotated[list[int], Field(
        default_factory=lambda: [500, 502, 503, 504],
        ui={"widget": "tags", "label": "retryOn (status codes)",
            "show_if": {"path": "enabled", "equals": True}},
    )]
```

**条件渲染注解 `show_if`**:
- `{path, equals}` 表示"父对象的 path 字段等于 equals 时显示"
- 前端用 `if (getValue(show_if.path) === show_if.equals) render()`
- 复杂条件(B5 后续):支持 `and` / `or` / `not`

---

## 3. `/api/schema/ui-spec` 端点

### 3.1 端点实现(`gimbal/prism/server.py`)

```python
from gimbal.schema.scenario import Scenario
from gimbal.prism.render.ui_spec import build_ui_spec


@app.get("/api/schema/ui-spec")
def schema_ui_spec() -> dict[str, Any]:
    """返回 schema → 前端可消费 JSON。

    返回结构:
    {
      "version": 1,
      "groups": [
        {
          "id": "meta",
          "label": "用例元信息",
          "icon": "info-circle",
          "fields": [
            {"path": "meta.name", "widget": "input", "required": true, ...},
            ...
          ]
        },
        ...
      ]
    }
    """
    return build_ui_spec(Scenario)
```

### 3.2 `build_ui_spec` 实现(`gimbal/prism/render/ui_spec.py`)

```python
from __future__ import annotations
from typing import Any, Type
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from gimbal.prism.render.walk_model import walk_fields


GROUP_DEFS = {
    # group id → (显示 label, icon)
    "meta": ("用例元信息", "info-circle"),
    "config": ("用例配置", "settings-2"),
    "timePolicy": ("Time Policy", "clock"),
    "retry": ("Retry", "refresh"),
    "services": ("Services", "server"),
    "users": ("Users", "users"),
    "resource": ("资源", "box"),
    "steps": ("Steps", "list-check"),
    "default": ("其他", "settings"),
}


def build_ui_spec(root_model: Type[BaseModel]) -> dict[str, Any]:
    """遍历 root_model 的所有字段,按 group 聚合。"""
    groups: dict[str, dict[str, Any]] = {}

    for path, field_info, parent_model in walk_fields(root_model):
        ui = (field_info.json_schema_extra or {}).get("ui") if field_info.json_schema_extra else None
        if not ui:
            continue  # 无 UI 注解的字段跳过(如 internal 字段)

        group_id = ui.get("group", "default")
        if group_id not in groups:
            label, icon = GROUP_DEFS.get(group_id, (group_id.title(), "settings"))
            groups[group_id] = {
                "id": group_id,
                "label": label,
                "icon": icon,
                "fields": [],
            }

        groups[group_id]["fields"].append({
            "path": path,
            "widget": ui.get("widget", "input"),
            "label": ui.get("label", _camel_to_label(path.split(".")[-1])),
            "required": ui.get("required", False),
            "placeholder": ui.get("placeholder"),
            "help": ui.get("help"),
            "options": ui.get("options"),
            "options_from": ui.get("options_from"),
            "min": ui.get("min"),
            "max": ui.get("max"),
            "unit": ui.get("unit"),
            "show_if": ui.get("show_if"),
            "rows": ui.get("rows"),
            "hint": ui.get("hint"),
            "readonly": ui.get("readonly", False),
            # 字段默认值,前端用它预填空白 draft
            "default": _extract_default(field_info),
        })

    # 按 GROUP_DEFS 中定义的顺序输出
    ordered_groups = []
    for gid in GROUP_DEFS:
        if gid in groups:
            ordered_groups.append(groups[gid])
    # 剩余未定义 group
    for gid, g in groups.items():
        if gid not in GROUP_DEFS:
            ordered_groups.append(g)

    return {"version": 1, "groups": ordered_groups}


def _camel_to_label(name: str) -> str:
    """camelCase / snake_case → Title Case。如 timePolicy → Time Policy。"""
    s = name.replace("_", " ")
    # 简单驼峰切分:小写-大写 处插入空格
    out = []
    for i, ch in enumerate(s):
        if i > 0 and ch.isupper() and s[i - 1].islower():
            out.append(" ")
        out.append(ch)
    return "".join(out).title()


def _extract_default(field_info: FieldInfo) -> Any:
    if field_info.default is not PydanticUndefined:
        return field_info.default
    if field_info.default_factory is not None:
        try:
            return field_info.default_factory()
        except Exception:
            return None
    return None
```

### 3.3 `walk_fields` 遍历算法(`gimbal/prism/render/walk_model.py`)

```python
from __future__ import annotations
from typing import Any, Iterator, Type
from pydantic import BaseModel
from pydantic.fields import FieldInfo


def walk_fields(
    root_model: Type[BaseModel],
    prefix: str = "",
    parent_model: Type[BaseModel] | None = None,
) -> Iterator[tuple[str, FieldInfo, Type[BaseModel]]]:
    """递归遍历 root_model 的所有字段,产出 (dot-path, field_info, parent_model)。

    - 嵌套 model:进入嵌套,prefix 加 "."
    - list of model:产出 list 字段本身(具体元素由 UI 渲染时实例化)
    - discriminated Union:产出整个 Union 字段,UI 按 kind 派发
    """
    if parent_model is None:
        parent_model = root_model

    for name, field_info in parent_model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name

        yield path, field_info, parent_model

        # 嵌套 model
        annotation = field_info.annotation
        if _is_base_model(annotation):
            yield from walk_fields(annotation, prefix=path, parent_model=annotation)
            continue

        # list[X] / dict[str, X] / Union:不递归,UI 单独处理
        # 但若 list[X] 中 X 是 model,需要让 UI 知道子类型
        # (留给前端 schema 文档,不再服务端展开)
```

### 3.4 输出示例

```json
// GET /api/schema/ui-spec
{
  "version": 1,
  "groups": [
    {
      "id": "meta",
      "label": "用例元信息",
      "icon": "info-circle",
      "fields": [
        {"path": "meta.scenarioId", "widget": "input", "label": "Scenarioid",
         "required": false, "readonly": true, "default": "sc_new"},
        {"path": "meta.name", "widget": "input", "label": "用例名",
         "required": true, "placeholder": "请输入用例名", "default": ""},
        {"path": "meta.description", "widget": "textarea", "label": "用例描述",
         "rows": 2, "default": ""},
        {"path": "meta.priority", "widget": "select", "label": "优先级",
         "options": [
           {"value": 1, "label": "1 (最高)"},
           {"value": 2, "label": "2"},
           {"value": 3, "label": "3"}
         ], "default": 1},
        {"path": "meta.tags", "widget": "tags", "label": "Tags",
         "hint": "回车/逗号添加 · 拖动重排", "default": []},
        ...
      ]
    },
    {
      "id": "config",
      "label": "用例配置",
      "icon": "settings-2",
      "fields": []
    },
    ...
  ]
}
```

---

## 4. 前端声明式渲染

### 4.1 渲染引擎骨架(`gimbal/prism/static/app.js`,取代 d:/mirror/prism/static/app.js)

```javascript
// app.js(v0 顶层结构)
const UI_SPEC = await fetch('/api/schema/ui-spec').then(r => r.json());

const state = {
  draft: {},
  ui: {},          // 当前激活的 tab
};

// 工具:set nested value
function setNested(obj, path, value) {
  const segs = path.split('.');
  let cur = obj;
  for (let i = 0; i < segs.length - 1; i++) {
    if (!(segs[i] in cur)) cur[segs[i]] = {};
    cur = cur[segs[i]];
  }
  cur[segs[segs.length - 1]] = value;
}

// 工具:get nested value
function getNested(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

// 渲染单个字段
function renderField(field) {
  const el = document.createElement('div');
  el.className = 'field-row';
  if (field.required) el.classList.add('req');

  const label = document.createElement('label');
  label.textContent = field.label;
  el.appendChild(label);

  // 按 widget 派发
  const widget = renderWidget(field);
  el.appendChild(widget);
  return el;
}

function renderWidget(field) {
  switch (field.widget) {
    case 'input': return renderInput(field);
    case 'textarea': return renderTextarea(field);
    case 'select': return renderSelect(field);
    case 'number': return renderNumber(field);
    case 'toggle': return renderToggle(field);
    case 'tags': return renderTags(field);
    case 'kv-list': return renderKVList(field);
    case 'step-list': return renderStepList(field);
    case 'resource-tile': return renderResourceTile(field);
    default: return renderInput(field);
  }
}

// 渲染整个 group(对应一个 tab)
function renderGroup(group) {
  const container = document.createElement('section');
  container.className = 'page';
  for (const field of group.fields) {
    container.appendChild(renderField(field));
  }
  return container;
}

// 入口
function mountAll() {
  const main = document.getElementById('card-stack');
  main.innerHTML = '';  // 清空旧 DOM
  for (const group of UI_SPEC.groups) {
    main.appendChild(renderGroup(group));
  }
}

// 双向绑定:draft 改变 → 重渲染对应字段
function applyDraftToUI(draft) {
  state.draft = draft;
  for (const group of UI_SPEC.groups) {
    for (const field of group.fields) {
      const el = document.querySelector(`[data-path="${field.path}"]`);
      if (el) updateWidget(el, field, getNested(draft, field.path));
    }
  }
}
```

### 4.2 各 widget 实现要点

#### input

```javascript
function renderInput(field) {
  const el = document.createElement('input');
  el.className = 'fin';
  el.id = `f_${field.path.replace(/\./g, '_')}`;
  el.placeholder = field.placeholder || '';
  el.readOnly = !!field.readonly;
  el.dataset.path = field.path;
  el.value = field.default ?? '';
  el.addEventListener('input', () => {
    setNested(state.draft, field.path, el.value);
    queueSave();
  });
  return el;
}
```

#### select

```javascript
function renderSelect(field) {
  const el = document.createElement('select');
  el.className = 'fin';
  el.dataset.path = field.path;
  for (const opt of field.options || []) {
    const o = document.createElement('option');
    o.value = String(opt.value);
    o.textContent = opt.label;
    if (opt.value === field.default) o.selected = true;
    el.appendChild(o);
  }
  el.addEventListener('change', () => {
    const v = el.value;
    setNested(state.draft, field.path, isNaN(Number(v)) ? v : Number(v));
    queueSave();
  });
  return el;
}
```

#### tags(复制 d:/mirror/prism/static/app.js 的现有实现,稍作修改)

```javascript
function renderTags(field) {
  const wrap = document.createElement('div');
  wrap.className = 'tags-wrap';
  wrap.dataset.path = field.path;
  const input = document.createElement('input');
  input.className = 'tag-input';
  input.placeholder = '+ tag';
  wrap.appendChild(input);
  // 复用 d:/mirror 现有 tags 逻辑:enter/comma 添加、backspace 删除、拖动重排
  attachTagsLogic(wrap, field);
  return wrap;
}
```

#### toggle

```javascript
function renderToggle(field) {
  const label = document.createElement('label');
  label.className = 'tog';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.dataset.path = field.path;
  cb.checked = !!field.default;
  const slider = document.createElement('span');
  slider.className = 'tog-slider';
  const text = document.createElement('span');
  text.className = 'tog-text';
  text.dataset.on = cb.checked;
  text.textContent = cb.checked ? 'true' : 'false';
  cb.addEventListener('change', () => {
    text.dataset.on = cb.checked;
    text.textContent = cb.checked ? 'true' : 'false';
    setNested(state.draft, field.path, cb.checked);
    queueSave();
  });
  label.append(cb, slider, text);
  return label;
}
```

### 4.3 条件渲染 `show_if`

```javascript
function shouldRender(field) {
  if (!field.show_if) return true;
  const { path, equals } = field.show_if;
  return getNested(state.draft, path) === equals;
}

// 监听 path 变化,重渲染受影响的字段
function onDraftChange(changedPath) {
  for (const group of UI_SPEC.groups) {
    for (const field of group.fields) {
      if (field.show_if?.path === changedPath) {
        const el = document.querySelector(`[data-path="${field.path}"]`)
          ?.closest('.field-row');
        if (el) el.style.display = shouldRender(field) ? '' : 'none';
      }
    }
  }
}
```

### 4.4 tab 结构

| tab id | 对应 group |
|---|---|
| 01 meta | `meta` |
| 02 config | `services` / `users` / `timePolicy` / `retry` / `config` |
| 03 resource | `resource` |
| 04 steps | `steps` |

```javascript
const TAB_MAP = {
  0: ['meta'],
  1: ['services', 'users', 'timePolicy', 'retry'],
  2: ['resource'],
  3: ['steps'],
};

function activateTab(idx) {
  const activeGroups = new Set(TAB_MAP[idx] || []);
  for (const group of UI_SPEC.groups) {
    const pageEl = document.querySelector(`[data-group="${group.id}"]`);
    if (pageEl) pageEl.style.display = activeGroups.has(group.id) ? '' : 'none';
  }
}
```

---

## 5. `/api/schema/dot-paths` 端点(供前端校验 / 未来 AI 工具)

### 5.1 端点实现

```python
@app.get("/api/schema/dot-paths")
def schema_dot_paths() -> dict[str, list[str]]:
    """返回所有合法的 dot-path(供 AI tools 校验输入)。"""
    paths = []
    for path, _fi, _model in walk_fields(Scenario):
        paths.append(path)
    return {"paths": paths, "count": len(paths)}
```

### 5.2 输出示例

```json
{
  "paths": [
    "scenarioId",
    "kind",
    "meta.scenarioId",
    "meta.name",
    "meta.description",
    "meta.module",
    "meta.priority",
    "meta.author",
    "meta.owner",
    "meta.tags",
    "meta.version",
    "meta.expire",
    "meta.requirementRef",
    "config.setup",
    "config.teardown",
    "config.services",
    "config.users",
    "config.timePolicy.kind",
    "config.timePolicy.seconds",
    "config.retry.enabled",
    "config.retry.maxAttempts",
    "config.retry.backoffSeconds",
    "config.retry.retryOn",
    "resource",
    "steps",
    ...
  ],
  "count": 47
}
```

### 5.3 v0 用途

- 前端表单提交前的 dot-path 合法性校验
- 未来 AI 助手(v0.1+) 启用时,自动派生 PATH_TO_FIELD 取代 `prism/ai/tools.py` 静态表
- 测试断言:确保 schema 字段在加 / 改时不被遗漏

---

## 6. ModelRegistry → UI spec(`/api/registry/ui-spec`)

### 6.1 目标

schema 只定义"字段长什么样",但**字段值从哪里来**(已注册的 endpoint、auth、mock 模板)由 ModelRegistry 提供。本节定义 ModelRegistry → 前端可消费 JSON 的转换。

### 6.2 入口

```python
# gimbal/prism/render/registry_spec.py
from __future__ import annotations
from typing import Any
from gimbal.contracts import registry


def build_registry_spec() -> dict[str, Any]:
    """启动时反射 ModelRegistry 一次,生成前端可消费的 spec。

    字段漂移 → AttributeError → prism 启动失败(显式优于隐式)。
    """
    return {
        "version": 1,
        "kinds": ["mock", "mock_ref", "file", "file_ref"],
        "endpoints": [
            {
                "id": ep.id,
                "method": ep.method,
                "host": ep.host,
                "path": ep.path,
            }
            for ep in registry.list_endpoints()
        ],
        "auth_keys": list(registry.list_auth_keys()),
        "mock_templates": [
            {"name": t.name, "image": t.image, "config": t.config}
            for t in registry.list_mock_templates()
        ],
        "file_templates": [
            {"name": t.name, "path": t.path}
            for t in registry.list_file_templates()
        ],
    }
```

### 6.3 HTTP 暴露

```python
# gimbal/prism/server.py
from gimbal.prism.render.registry_spec import build_registry_spec


@app.get("/api/registry/ui-spec")
def get_registry_ui_spec(request: Request) -> dict[str, Any]:
    """返回 ModelRegistry → UI spec(供前端下拉/选项用)。"""
    cache = getattr(request.app.state, "registry_spec_cache", None)
    if cache is None:
        cache = build_registry_spec()
        request.app.state.registry_spec_cache = cache
    return cache
```

### 6.4 schema 字段如何引用 ModelRegistry

`ui.options_from` 注解把 schema 字段与 ModelRegistry 关联:

```python
# gimbal/schema/api.py
class Api(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: Annotated[str, Field(
        "", ui={"widget": "input", "label": "host", "options_from": "registry.endpoints[].host",
                "hint": "从 ModelRegistry 已有 endpoint 选择或输入新值"},
    )]


# gimbal/schema/resource.py
class Mock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: Annotated[str, Field(
        "nginx:latest", ui={"widget": "select", "label": "image",
                            "options_from": "registry.mock_templates[].image"},
    )]
```

`walk_model` 走完 schema 后,前端拿到 spec 知道:"这个字段的选项从 `registry.endpoints[].host` 取"。

### 6.5 前端消费

```javascript
// app.js
const REG_SPEC = await fetch("/api/registry/ui-spec").then(r => r.json());

// 渲染 schema spec 中带 options_from 的 select
function renderSelect(field) {
  const el = document.createElement("select");
  el.dataset.path = field.path;
  const options = field.options_from
    ? resolveOptionsFrom(field.options_from)   // 从 REG_SPEC 提取
    : field.options || [];
  for (const opt of options) {
    const o = document.createElement("option");
    o.value = opt.value;
    o.textContent = opt.label || opt.value;
    el.appendChild(o);
  }
  // ...
}

function resolveOptionsFrom(path) {
  // "registry.endpoints[].host" → REG_SPEC.endpoints.map(e => ({value: e.host, label: `${e.method} ${e.host}`}))
  if (path === "registry.endpoints[].host") {
    return REG_SPEC.endpoints.map(e => ({
      value: e.host,
      label: `${e.method} ${e.host}${e.path}`,
    }));
  }
  // ...其他 path ...
}
```

### 6.6 字段漂移防护

D:/M/ModelRegistry 后续若重命名 `EndpointSpec.host` 为 `EndpointSpec.hostname`,本文件 `build_registry_spec` 启动时会抛 AttributeError,直接阻止 prism 启动——这是**显式优于隐式**的取舍,避免线上配置错位。

### 6.7 与 04 §3 schema → UI spec 的关系

| 维度 | `/api/schema/ui-spec` | `/api/registry/ui-spec` |
|---|---|---|
| 数据源 | Pydantic schema 字段定义 | D:/M/ModelRegistry runtime registry |
| 决定 | 字段"长什么样"(widget / label / required) | 字段"值从哪来"(options_from) |
| 失效模式 | 改 schema 不改 spec → 字段渲染错(可视化报错) | 改 ModelRegistry 字段名 → 启动失败 |
| v0 必备 | ✅ | ✅ |

---

### 7.2 前端测试

```javascript
// tests/frontend/test_ui_spec_render.test.js(可选 jest/vitest)
import { describe, it, expect } from 'vitest';
// 假设 app.js 导出纯函数 _renderField(field, draft)
describe('renderField', () => {
  it('renders input widget', () => {
    const html = _renderField({ path: 'meta.name', widget: 'input' }, {});
    expect(html.querySelector('input')).toBeTruthy();
  });
});
```

---

## 7. 测试

### 7.1 单元测试

```python
# tests/test_schema_ui_spec.py
def test_ui_spec_groups_in_order():
    spec = build_ui_spec(Scenario)
    assert spec["version"] == 1
    assert [g["id"] for g in spec["groups"][:4]] == ["meta", "config", "resource", "steps"]


def test_ui_spec_meta_has_name_field():
    spec = build_ui_spec(Scenario)
    meta = next(g for g in spec["groups"] if g["id"] == "meta")
    name_field = next(f for f in meta["fields"] if f["path"] == "meta.name")
    assert name_field["widget"] == "input"
    assert name_field["required"] is True


def test_ui_spec_priority_options():
    spec = build_ui_spec(Scenario)
    meta = next(g for g in spec["groups"] if g["id"] == "meta")
    priority = next(f for f in meta["fields"] if f["path"] == "meta.priority")
    assert priority["widget"] == "select"
    assert {o["value"] for o in priority["options"]} == {1, 2, 3}


# tests/test_schema_dot_paths.py
def test_dot_paths_includes_meta():
    resp = client.get("/api/schema/dot-paths")
    assert "meta.name" in resp.json()["paths"]


# tests/test_registry_spec.py
def test_registry_spec_has_endpoints():
    spec = build_registry_spec()
    assert "endpoints" in spec
    assert isinstance(spec["endpoints"], list)


def test_registry_spec_starts_fail_on_missing_field(monkeypatch):
    """字段漂移:若 D:/M/ModelRegistry 改了 EndpointSpec 字段名,启动应失败。"""
    from gimbal.contracts import registry
    monkeypatch.delattr(registry.EndpointSpec, "host", raising=False)
    with pytest.raises(AttributeError):
        build_registry_spec()
```

### 7.2 前端测试

```javascript
// tests/frontend/test_ui_spec_render.test.js(可选 jest/vitest)
import { describe, it, expect } from 'vitest';
// 假设 app.js 导出纯函数 _renderField(field, draft)
describe('renderField', () => {
  it('renders input widget', () => {
    const html = _renderField({ path: 'meta.name', widget: 'input' }, {});
    expect(html.querySelector('input')).toBeTruthy();
  });
});
```

---

## 8. 边界与不做的事

| 不做 | 理由 |
|---|---|
| 动态发现 schema 变更 → 热重载 UI | 性能开销,schema 改动一般随版本发布 |
| `show_if` 支持 and/or/not | v0 仅 `{path, equals}`,复杂条件留 v0.1+ |
| 服务端 schema 文档自动生成(Swagger 替代) | 用 FastAPI 自带 OpenAPI |
| `/api/schema/ui-spec` 支持多版本 | 加 `version` 字段但 v0 仅 1 |
| 前端 schema 校验(zod / yup 镜像) | 仅前端展示层,后端 schema 校验是权威 |
| AI 助手本身(v0 不做,用户明确"先不考虑 AI") | 见 [01-architecture.md](01-architecture.md) §1.2 |
| PATH_TO_FIELD 自动派生(原 AI 用) | AI 整体未实现,无消费方 |
| SCHEMA_SUMMARY 自动生成(原 AI 用) | AI 整体未实现,无消费方 |

---

## 9. 下游文档引用

- 总架构(两个模块位置) → [01-architecture.md](01-architecture.md)
- prism HTTP API → [03-prism-module.md](03-prism-module.md) §2
- ModelRegistry → UI spec → [03-prism-module.md](03-prism-module.md) §6
- ModelRegistry 引入的 schema 增强(Step.key / Meta.name blank) → [05-model-registry-integration.md](05-model-registry-integration.md) §2
- 迁移执行步骤 → [06-migration-plan.md](06-migration-plan.md) M2