# gimbal 用户手册

> **gimbal v0.1.0** — 测试用例配置平台
> 把"浏览器真实流量"转成"可复用的 GIMBAL Scenario"。

本手册对应仓库根目录 `D:/M/ModelRegistry`，目录结构如下：

```
D:/M/ModelRegistry/
├── gimbal/                    # ★ gimbal 主包(capture + prism)
│   ├── capture/               # 流量捕获子模块
│   ├── prism/                 # Web 配置器子模块
│   ├── schema/                # Pydantic 静态描述层(SSOT)
│   ├── contracts/             # ModelRegistry 引入层
│   └── cli/                   # 顶层 CLI
├── ModelRegistry/             # 契约模型仓库(endpoint 注册中心)
├── tests/                     # pytest 测试套件
├── gimbal-design/             # 设计文档归档
├── pyproject.toml             # 项目元数据 + 依赖
├── requirements.txt           # 当前 venv 安装清单
├── README.md                  # 简要 README
└── CHANGELOG.md               # 变更历史
```

---

## 1. 项目定位

gimbal 由 **两个进程级独立的子命令** 组成，**无反向依赖**，**无进程间 API**，**文件系统是唯一契约**：

```
浏览器 ──→ capture 代理 (:8080) ──→ NDJSON 落盘 ──→ prism 配置器 (:8765) ──→ scenarios/{sid}.yaml
```

| 模块 | 入口命令 | 角色 |
|---|---|---|
| **capture** | `gimbal capture start` | mitmproxy 抓包 + NDJSON 落盘 + 归档 |
| **prism** | `gimbal prism start` | FastAPI Web 配置器，把捕获编辑成 Scenario YAML |

### v0 显式不做的事

- ❌ `gimbal run` 执行引擎
- ❌ AI 助手（不依赖 `anthropic` / `httpx`）
- ❌ 多 worker uvicorn（`--workers 1` 强制）
- ❌ `config.yaml` 加载（全部走 CLI 参数）
- ❌ 大规模 E2E 测试补全

---

## 2. 环境准备

### 2.1 Python 与虚拟环境

本仓库自带隔离虚拟环境（`.venv/`），使用 `.venv` 中的解释器运行：

```bash
# 激活虚拟环境
source .venv/Scripts/activate          # Git Bash
# 或直接调用 .venv 中的 python
D:/M/ModelRegistry/.venv/Scripts/python.exe -m pip install -e . --no-deps
```

### 2.2 安装 gimbal

```bash
# 标准安装
pip install -e .

# 启用 ModelRegistry 集成（可选，需要 D:/M/ModelRegistry）
pip install -e ".[model-registry]"
# 或通过环境变量指向 ModelRegistry 根目录
export GIMBAL_MODEL_REGISTRY_PATH=/path/to/D:/M/ModelRegistry
```

> **注意**：`pyproject.toml` 中 `model-registry = ["model-registry-local @ file:///D:/M/ModelRegistry"]` 是 Windows 开发环境的可编辑依赖；CI 跳过此 extras，代码走 `is_available()` 降级。

### 2.3 验证安装

```bash
python -c "from gimbal.contracts import is_available, EndpointSpec; print(is_available())"
```

未启用时 `is_available()` 返回 `False`，其他模块正常使用，仅 `/api/registry/ui-spec` 返回最小空 spec。

---

## 3. 数据目录（`$GIMBAL_HOME`）

默认 `~/.gimbal/`，可通过 `GIMBAL_HOME` 环境变量或 `--home` 参数覆盖：

```
$GIMBAL_HOME/
├── captures/
│   ├── active/
│   │   └── {session_id}.ndjson      # capture 正在写入（排他文件锁）
│   └── archive/
│       └── 2026-06-18/
│           └── {sid}-{epoch}.ndjson
├── scenarios/
│   └── {scenario_id}.yaml           # prism 导出
└── config.yaml                      # v0 暂未实现
```

---

## 4. `gimbal capture` 流量捕获模块

### 4.1 子命令一览

| 子命令 | 作用 |
|---|---|
| `gimbal capture start` | 启动 mitmproxy 抓包 |
| `gimbal capture list` | 列出 active 下的 session |
| `gimbal capture show <sid>` | 查看某 session 的事件（默认最近 50 条） |
| `gimbal capture archive <sid>` | 手动归档 |

### 4.2 启动抓包

```bash
# 终端 1：启动 capture
gimbal capture start --session dev-1 --port 8080
# [capture] session=dev-1  port=8080  filter=/api/
# [capture] out=C:\Users\me\.gimbal\captures\active\dev-1.ndjson
# [capture] 浏览器代理指向 127.0.0.1:8080, 信任 mitmproxy CA (http://mitm.it)
```

启动后浏览器走代理，HTTPS 请求会进入 `$GIMBAL_HOME/captures/active/dev-1.ndjson`。**按 Ctrl+C 停止，自动归档**到 `archive/{date}/dev-1-{ts}.ndjson`。

#### 4.2.1 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--session` / `-s` | （必填） | 会话 ID，用作文件名 |
| `--port` / `-p` | `8080` | 监听端口 |
| `--filter` / `-f` | `/api/` | path 前缀过滤，逗号分隔（如 `/api/order,/api/user`） |
| `--filter-file` | （自动查找） | YAML 筛选配置文件（v0.4 新增） |
| `--filter-profile` | （自动/默认） | YAML 中的 profile 名（v0.4 新增） |
| `--filter-mode` | `include` | CLI `--filter` 追加规则的默认 mode（v0.4 新增） |
| `--strict-files-only` | `false` | 关闭自动文件查找（v0.4 新增） |
| `--home` | `~/.gimbal` | 覆盖 `GIMBAL_HOME` |
| `--mitmdump` | `mitmdump` | mitmdump 可执行文件路径 |

#### 4.2.2 路径过滤规则（v0 CSV 模式，向后兼容）

- `/api/order` 匹配 `/api/order`、`/api/order/123`，**不匹配** `/api/orderlist`
- 多个前缀任一匹配即通过（OR 语义）
- 空 filter 字符串 → 不过滤（全部记录）

#### 4.2.3 YAML 筛选策略（v0.4 新增）

简单 CSV 模式只能按 path 前缀过滤。复杂场景（按 host/method/glob/regex，多 profile，include 复用）需要写 YAML 配置文件。

**自动查找顺序**（未传 `--filter-file` 时）：

1. `./.gimbal/filters.yaml`
2. `./filters.yaml`
3. `~/.gimbal/filters.yaml`
4. `$GIMBAL_FILTERS` 环境变量指向的文件

**单 profile 示例**：

```yaml
# filters.yaml
mode: include
default_profile: smoke

profiles:
  smoke:
    description: 日常冒烟
    rules:
      - host: api.example.com
        path: /api/order
        methods: [POST, PUT]
      - path_glob: "/api/v*/order/**"
```

```bash
gimbal capture start --session dev-1 \
  --filter-file filters.yaml \
  --filter-profile smoke
```

**include 复用示例**（公共黑名单放独立文件，团队配置 include 进来）：

```yaml
# _common.yaml — 公共黑名单，永不录
mode: exclude
profiles:
  _common:
    rules:
      - path: /api/auth/login
      - path_regex: "^/api/internal/.*"
      - host_regex: "internal\\.example\\.com"
```

```yaml
# filters.yaml — 团队主配置
mode: include
default_profile: smoke
includes:
  - ./_common.yaml

profiles:
  smoke:
    rules:
      - host: api.example.com
        path_glob: /api/**
  e2e:
    rules:
      - host_glob: "*.example.com"
        path_regex: "^/api/(order|user)/.*"
        methods: [GET, POST]
```

**CLI 临时追加**（在 profile 规则之后再追加 `--filter`，mode 由 `--filter-mode` 决定）：

```bash
# 临时多录一个路径
gimbal capture start --session dev-1 \
  --filter-file filters.yaml \
  --filter-profile smoke \
  --filter "/api/debug" \
  --filter-mode include
```

**Rule 字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `mode` | `include` / `exclude` | 单条 rule 命中后的语义；缺省继承顶层 `mode` |
| `host` | string | 精确匹配 |
| `host_glob` | string | fnmatch 通配（`*.example.com`） |
| `host_regex` | string | 正则 |
| `path` | string | 前缀匹配（`/api/order` 不会误匹配 `/api/orderlist`） |
| `path_glob` | string | fnmatch 通配（`/api/**`） |
| `path_regex` | string | 正则 |
| `methods` | list[string] | HTTP method 白名单（自动大写） |

**匹配语义**：

- 同一 rule 内：所有填写的字段都必须满足（**AND**）
- 多条 rule 之间：任一命中即通过（**OR**）
- rule 命中后，`rule.mode` 决定 include/exclude
- 无 rule 命中时，文件顶层 `mode` 决定兜底方向（include → 不录；exclude → 录）
- host 三种形式、path 三种形式各自**三选一**，否则 Pydantic 校验失败
- 空 rule（无任何匹配字段）被拒绝

**配置文件错误**（YAML 错、正则错、include 循环、profile 找不到、空规则）→ 父进程打印红字并以**退出码 5** 退出，不会启动 mitmdump。

### 4.3 列出与查看

```bash
# 列出 active 下的 session
gimbal capture list

# 查看某 session 最近 50 条
gimbal capture show dev-1 --limit 50
```

### 4.4 手动归档

```bash
gimbal capture archive dev-1
# 已归档 → C:\Users\me\.gimbal\captures\archive\2026-06-18\dev-1-1718678400.ndjson
```

### 4.5 capture 模块实现要点

- **FileBus**：NDJSON 文件总线 + 跨进程文件锁（POSIX `fcntl.flock` / Windows `msvcrt.locking`）
- **归档策略**：`active/{sid}.ndjson` → `archive/{YYYY-MM-DD}/{sid}-{epoch}.ndjson`
  - 触发时机：capture Ctrl+C / SIGTERM、`gimbal capture archive` 手动归档
  - 崩溃（SIGKILL / 异常退出）**不归档**，下次 start 时检测残留
- **残留检测**：文件存在但锁未持有 → 试探性 lock → 提示用户如何处理

---

## 5. `gimbal prism` Web 配置器

### 5.1 启动配置器

```bash
# 终端 2：启动 prism
gimbal prism start --port 8765
# [prism] GIMBAL_HOME=C:\Users\me\.gimbal
# [prism] starting on http://127.0.0.1:8765
```

#### 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--host` / `-h` | `127.0.0.1` | 监听地址 |
| `--port` / `-p` | `8765` | 监听端口 |
| `--home` | `~/.gimbal` | 覆盖 `GIMBAL_HOME` |
| `--workers` / `-w` | `1` | uvicorn workers，v0 仅支持 1 |
| `--reload` | `False` | 开发模式热重载 |

### 5.2 Web UI（4 Tab Card Stack 视觉规范 v0.5）

浏览器打开 `http://127.0.0.1:8765`，主界面有 4 个 Tab（顶部固定栏 + tab 切换 + 卡片堆叠）：

| Tab | 标题 | 内容 |
|---|---|---|
| ① | 元信息 | `Meta` 字段：name、description、module、priority、author、owner、tags、version、expire、requirementRef、scenarioId |
| ② | 配置 | `Config` + 子结构：`Services`（alias → base URL）、`Users`（AuthSession）、`TimePolicy`、`Retry`（max / backoff / on）、`Setup` / `Teardown` refs |
| ③ | 资源 | 4 种资源 kind 网格：DB 接入、Mock 接口、文件上传、变量 |
| ④ | Steps | **分页布局**：左侧 1-10/11-20 侧栏 + 右侧 step 标签流（method + path）。**空状态可点击** 弹出 .ndjson 文件选择器，也支持拖入 .ndjson。点击 tag 展开完整编辑（API/Request/Strategy 三子 tab）。 |

**v0.5 视觉规范**：
- 顶部 sticky 栏（深色）+ status dot（绿/黄/橙三态）+ captures badge + undo/redo/help 按钮
- Card Stack：每个 tab 一张大卡片，13px 圆角 + 12px 阴影
- 字段布局：左 label 130px + 右 input grid
- 设计 tokens：CSS 变量统一管理颜色 / 字体 / 间距
- tabler-icons CDN（`<i class="ti ti-info-circle">`）作为图标源
- 模态系统：YAML 预览（带 JSON 切换 / 复制 / 导出）+ Help 快捷键说明
- Toast 系统：右下角（实为 top-right `60px`）即时反馈
- 拖拽重排：tags / services / resources / steps 都支持
- 快捷键：`Ctrl+S` 保存 / `Ctrl+Z` 撤销 / `Ctrl+Y` 重做 / `Ctrl+1..4` 切 tab / `?` 打开 help / `Esc` 关闭 modal

#### 5.2.5 v0.5.5 Step 分页 + 文件选择器（v0.5.5 起）

**新增**：
- 左侧垂直侧栏按 10 个一组显示 `1-10`、`11-20`、`21-30` ...（鼠标 hover 高亮，点击切换）
- 右侧横向 tag 流，每 tag 仅显示 method pill + path，hover 出现删除 × 按钮
- 展开/收起：点 tag → 下方展开完整 step 编辑面板（API/Request/Strategy 三子 tab），再点同一 tag 收起
- 拖拽重排：拖 tag 在当前页 10 个内重排
- 拖入 `.ndjson` 到 step 区域 / 空状态框触发导入（限定 `.ndjson` 后缀）

**删除**：
- 「全部展开」/「全部折叠」按钮（单展开手风琴替代）
- 步骤导入行（输入框 + 导入按钮）；改由空状态框点击弹出文件选择器
- `.json` 文件导入支持（v0.5.5 起只接受 `.ndjson`）

**自动跳转**：删除 step 后，若 `currentPage` 越界，自动跳到最后一页有效页码。

### 5.3 HTTP 端点

`gimbal prism` 暴露的 HTTP 端点（默认 :8765）：

| 路径 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 配置器 HTML |
| `/configure?session=<sid>` | GET | 带 session 注入的 HTML |
| `/api/health` | GET | 健康检查 + 计数 |
| `/api/captures?sid=<sid>` | GET | 列出某 session 的 capture |
| `/api/captures?sid=<sid>` | DELETE | 清空（truncate） |
| `/api/captures/inject?sid=<sid>` | POST | 单 event 追加（测试 / replay 用） |
| `/api/captures/import-from-path` | POST | 从 NDJSON 路径导入（**沙箱限制 CWD 内**） |
| `/api/captures/stream?sid=<sid>` | GET | **SSE** 实时推送 capture 增量 |
| `/api/draft/{sid}` | GET / PUT | 草稿读写（带 undo/redo 历史栈） |
| `/api/draft/{sid}/export` | POST | 写 Scenario YAML 到 `$GIMBAL_HOME/scenarios/{sid}.yaml` |
| `/api/draft/{sid}/yaml` | POST | 只读 YAML 预览（422 on invalid） |
| `/api/schema/ui-spec` | GET | **schema → 前端 JSON（SSOT）** |
| `/api/schema/dot-paths` | GET | **合法 dot-path 白名单** |
| `/api/registry/ui-spec` | GET | **ModelRegistry → UI spec** |

### 5.4 SSE 实时推送

```
GET /api/captures/stream?sid=<sid>
event: capture
id: 1718678400.123
data: {"method":"GET","host":"api.example.com","path":"/api/order",...}
```

启动时先发一帧现有所有事件（让前端一次性补齐），之后通过 watchdog 监听 NDJSON 文件 modify 事件推送增量。

---

## 6. ModelRegistry 契约模型仓库

### 6.1 加载方式

`gimbal.contracts` 双路径加载：

1. 已装 `model-registry-local`（`pip install -e ".[model-registry]"`）→ `from ModelRegistry import ...`
2. 环境变量 `GIMBAL_MODEL_REGISTRY_PATH` 指向 D:/M/ModelRegistry 根目录 → `sys.path` 注入
3. 全部失败 → `is_available() == False`，降级运行

### 6.2 核心符号

| 符号 | 来源 | 用途 |
|---|---|---|
| `registry` | `ModelRegistry.core` | 进程级单例（线程安全、按需加载、拉式收集） |
| `EndpointKey` | `ModelRegistry.core` | 索引键 dataclass（service / method / path） |
| `EndpointSpec` | `ModelRegistry.spec` | endpoint 契约（`@final` + `frozen=True`） |
| `MockHook` / `ValidateHook` / `BuildRequestHook` | `ModelRegistry.spec` | 三个 `@runtime_checkable Protocol`（本期不实装） |
| `BootstrapError` | `ModelRegistry.core` | `warm()` 失败时的聚合错误类 |

### 6.3 EndpointSpec 字段

```python
EndpointSpec(
    method="POST",                        # 必填
    path="/api/order",                    # 必填
    request=RequestModel,                 # BaseModel 子类或 None
    responses={200: ResponseModel},       # {status: BaseModel}
    summary="...",
    description="...",
    tags=[...],
    auth_required=False,
    default_response=None,                # 预留槽位
    response_union={},                    # 预留槽位
    mock_hook=None,                       # 能力 hook
    validate_hook=None,
    build_request_hook=None,
)
```

### 6.4 注册约定

每个 service 对应 `ModelRegistry/<service_dir>/` 目录。目录名 = service 名（合法 Python 标识符），或在 `ModelRegistry/_aliases.py` 的 `SERVICE_ALIASES` 中显式声明映射（连字符 / 数字开头时使用）。

---

## 7. Pydantic Schema（SSOT）

`gimbal/schema/` 共 14 个文件，全部带 `model_config = ConfigDict(extra="forbid")`。

### 7.1 主要 Model

| 文件 | 导出 |
|---|---|
| `scenario.py` | `Scenario`, `Meta`, `Config`, `Suite`, `ScenarioRef`, `SuiteRef` |
| `step.py` | `Step`, `StepRef`, `StepUnion` |
| `api.py` | `Api`, `ApiRef`, `ApiUnion` |
| `request.py` | `Request`, `RequestRef`, `RequestUnion` |
| `strategy.py` | `Extract`, `Assign`, `Assertion`, `StrategyRef`, `StrategyUnion`, `Scope`, `AssertOperator`, `StrategyPhase`, `FailurePolicy` |
| `timepolicy.py` | `TimePolicy`, `TimeoutPolicy`, `RecordPolicy` |
| `retrypolicy.py` | `RetryPolicy` |
| `resource.py` | `Resource`, `Mock`, `File`, `MockRef`, `FileRef` |
| `auth.py` | `AuthSession`（带 `apply_token` / `clear_token` / `is_authenticated` 方法） |
| `setup.py` / `teardown.py` | `Setup`, `SetupRef`, `Teardown`, `TeardownRef` |
| `ref.py` | `RefBase`, `Ref` |
| `states.py` | `StepState` 枚举 |

### 7.2 Field 包装与 UI 注解

```python
from gimbal.schema import Field

class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(
        "",
        min_length=1,
        ui={
            "widget": "input", "label": "用例名", "required": True,
            "placeholder": "请输入用例名", "group": "meta",
        },
    )
```

**关键点**：UI 元数据走 `json_schema_extra["ui"]`，**不进入 `model_dump`**。schema 通过 `/api/schema/ui-spec` 反射为前端 JSON（SSOT）。

### 7.3 支持的 UI widget

| widget | 适用字段类型 | 说明 |
|---|---|---|
| `input` | str | 普通输入 |
| `textarea` | str（多行） | 多行文本 |
| `password` | str | 密码（默认 `<REDACTED>`） |
| `select` | enum / Literal | 下拉（options 静态或 options_from 动态） |
| `number` | int / float | 数字（min/max/unit） |
| `toggle` | bool | 开关 |
| `tags` | list[str] | 标签（回车/逗号添加 · 拖动重排） |
| `kv-list` | dict[str, X] | 键值对列表（key_label / value_label） |

**show_if 联动**：例如 `timePolicy.seconds` 字段在 `timePolicy.kind == "timeout"` 时才显示。

---

## 8. Scenario YAML 导出

### 8.1 导出流程

1. 编辑器表单 → `/api/draft/{sid}` PUT（自动保存）
2. 点 "导出 YAML" → `/api/draft/{sid}/export` POST
3. 服务端构造 Pydantic 模型 → `Scenario.model_validate(scenario)` 校验
4. 校验失败 → 422 + 字段错误
5. 校验通过 → `yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False)` → `$GIMBAL_HOME/scenarios/{sid}.yaml`

### 8.2 YAML 预览（只读）

`POST /api/draft/{sid}/yaml` 返回 YAML 文本，校验失败返回 422 + 字段错误，不写盘。

### 8.3 builder 关键行为

- **resource kind 派发表**（痛点 12）：`mock` / `mock_ref` / `file` / `file_ref` 通过 `_RESOURCE_KIND_DISPATCH` 字典派发
- **默认 assertion name**（痛点 13）：`assert_status_{idx}` 形式（替代 `hash(path)` 不可复现）
- **AuthSession password**：默认走 `<REDACTED>`，仅 `confirm_password=True` 才落明文
- **Step.key**：`{idx}-{slug}` 形式（如 `1-call_login`），slug 来源 `key_hint` 优先，否则用 path

---

## 9. doc2model 工具

`gimbal/prism/doc2model.py` 从捕获样本推断 Pydantic 模型：

```bash
python -m gimbal.prism.doc2model \
  --in captures/active/dev-1.ndjson \
  --service order-service \
  --method GET \
  --path /api/order \
  --into-registry    # 直接写到 ModelRegistry/{service}/
```

| 参数 | 说明 |
|---|---|
| `--in` | 输入 NDJSON / JSON 文件（与 `--in-dir` 互斥） |
| `--in-dir` | 输入目录（每个 JSON 文件一个样本） |
| `--service` | service 名（用于 ModelRegistry 目录） |
| `--method` | HTTP 方法（默认 `GET`） |
| `--path` | URL 路径（默认 `/`） |
| `--out-dir` | 默认 `./generated/` |
| `--into-registry` | 直接写到 `ModelRegistry/{service}/`（需 is_available()） |
| `--required-ratio` | 字段出现率 ≥ 此值视为必填（默认 0.8） |
| `--dry-run` | 只打印到 stdout，不写盘 |

**类型推断规则**：

- 数字：出现小数 → `float`，否则 `int`
- bool：所有出现值都在 `{true, false}` 且至少出现一次 → `bool`
- null：记成 `Optional[...]`
- dict：递归生成嵌套 BaseModel（类名 `<父>_<key>Model`）
- list：`list[<elem>]`，空列表记为 `list[Any]`

**ModelRegistry 不可用时**：`--into-registry` 退出码 3，提示安装 `model-registry-local` 或设置 `GIMBAL_MODEL_REGISTRY_PATH`。

---

## 10. 开发与测试

### 10.1 在隔离 venv 中开发

```bash
# 安装依赖
D:/M/ModelRegistry/.venv/Scripts/python.exe -m pip install -e . --no-deps

# 跑测试
D:/M/ModelRegistry/.venv/Scripts/python.exe -m pytest tests/

# 静态分析
D:/M/ModelRegistry/.venv/Scripts/python.exe -m ruff check gimbal/
```

### 10.2 测试统计（v0.3）

- **测试**：84 passed, 4 skipped（含 1 个 contracts unavailable, 1 个 doc2model unavailable, 2 个 v0 historical）
- **覆盖**：schema ui-spec、capture smoke、prism server、builder、registry spec、E2E

### 10.3 关键测试文件

- `test_capture_smoke.py` — capture FileBus / 归档
- `test_prism_server.py` / `test_prism_state.py` / `test_prism_builder.py` — prism 后端
- `test_schema_ui_spec.py` / `test_schema_ui_annotations_v021.py` / `test_schema_ui_annotations_v024.py` — schema 反射
- `test_registry_spec.py` — ModelRegistry 引入
- `test_contracts_init.py` — contracts 双路径加载
- `test_frontend_declarative.py` — 前端声明式渲染
- `test_e2e.py` — 端到端

---

## 11. 设计文档索引

详见 [`gimbal-design/`](gimbal-design/) 目录（6 份文档）：

| 编号 | 文档 | 范围 |
|---|---|---|
| 01 | `01-architecture.md` | 总体架构 · 两个模块拆分 · 顶层 CLI · 文件系统契约 |
| 02 | `02-capture-module.md` | `gimbal capture` 模块详细设计 |
| 03 | `03-prism-module.md` | `gimbal prism` 配置器设计 |
| 04 | `04-schema-ssot.md` | schema SSOT 与 UI 注解体系 |
| 05 | `05-model-registry-integration.md` | ModelRegistry 引入 |
| 06 | `06-migration-plan.md` | M1-M4 迁移计划 |

**阅读建议**：理解整体架构 → `01`；负责 capture → `02`；负责 prism → `03`；负责 schema/前端 → `04`；负责 ModelRegistry 引入 → `05`；想知道执行节奏 → `06`。

---

## 12. 故障排查

### 12.1 capture 启动失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `session 'X' 已有残留数据` | 上次崩溃未归档 | 选 y 清空，或 y 后退出 |
| `session 'X' 已被另一个进程占用` | 已有 capture 进程持有锁 | 退出码 4，停止其他进程 |
| `mitmdump: command not found` | PATH 中找不到 mitmdump | 用 `--mitmdump` 指定完整路径 |

### 12.2 prism 启动失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `prism UI not built` | `static/index.html` 缺失 | 检查 `gimbal/prism/static/` 目录 |
| `sse-starlette 未装` | 依赖缺失 | `pip install sse-starlette` |
| 422 schema 错误 | draft 字段不合法 | 检查 `meta.name`（必填非空白）、priority 等 |

### 12.3 ModelRegistry 集成

```bash
# 验证 ModelRegistry 是否可用
python -c "from gimbal.contracts import is_available; print(is_available())"

# 不可用时:
# 1) pip install -e ".[model-registry]"
# 2) export GIMBAL_MODEL_REGISTRY_PATH=/path/to/D:/M/ModelRegistry
```

不可用时 `/api/registry/ui-spec` 返回最小空 spec（`available: false`），其他模块正常工作。

---

## 13. 常见问题（FAQ）

**Q：capture 和 prism 必须在同一台机器吗？**

A：不需要。它们通过文件系统通信，可在两台机器上各跑一个，共享 `$GIMBAL_HOME`（NFS / 共享盘）即可。

**Q：能同时运行多个 capture 进程吗？**

A：每个 session 独占文件锁，不同 session 可并行。同 session 重复启动会被拒（退出码 4）。

**Q：怎么启用多 worker uvicorn？**

A：v0 不支持。`--workers 1` 强制，因为 sessions 是进程内状态。

**Q：怎么禁用敏感字段落盘？**

A：在 prism 端编辑 AuthSession 时不勾 `confirm_password`，password 会以 `<REDACTED>` 形式存进 YAML。

**Q：怎么自定义 widget？**

A：当前版本固定 7 widget（input/textarea/select/number/toggle/tags/kv-list）。扩展需在 `gimbal/prism/static/app.js` 的 `renderWidget` switch 中加 case + schema 注解中用 `ui={"widget": "your-widget"}`。

**Q：怎么扩展 resource kind？**

A：在 `gimbal/prism/builder.py` 的 `_RESOURCE_KIND_DISPATCH` 字典中加一行，并在 `gimbal/schema/resource.py` 加对应 Pydantic 子类（`Literal["xxx"]` 触发 discriminator）。

---

## 14. 版本与变更

- **当前版本**：v0.1.0（platform 首发）
- **最新变更**：v0.3（2026-06-18）— 删除旧 `prism/` 顶层包 + 收尾
- 完整变更记录见 [`CHANGELOG.md`](CHANGELOG.md)

---

## §X Headless CLI (v0.6+)

`gimbal prism` 提供 9 个 headless 子命令, 无需启动 web 服务器。

### §X.1 Pipeline 子命令

- `gimbal prism convert -i foo.ndjson [-c cfg.yaml] [-o out.yaml]` — NDJSON + 配置 → Scenario YAML (stdout 缺省)
- `gimbal prism inspect -i foo.ndjson [--json]` — 统计 (event 数 / method 分布 / host 分布 / status 分布) + 前 3 条样本
- `gimbal prism validate -c cfg.yaml` — 校验 config YAML 是否合法
- `gimbal prism to-steps -i foo.ndjson [-o steps.json]` — NDJSON → step 片段 JSON (中间产物)
- `gimbal prism explain <scenario.yaml> [--section meta]` — 输出结构化摘要

### §X.2 Edit 子命令 (按 section 分组)

- `gimbal prism meta get <sc> [--field name]`
- `gimbal prism meta set <sc> [--name ...] [--description ...] [--module ...] [--priority N] [--dry-run]`
- `gimbal prism user list <sc>`
- `gimbal prism user add <sc> --key K [--url ... --username ... --password ... --expires-in N]`
- `gimbal prism user remove <sc> --key K`
- `gimbal prism resource list <sc>`
- `gimbal prism resource add <sc> --name N [--kind mock|mock_ref|file|file_ref] [--image ...] [--port HOST:CONT]`
- `gimbal prism resource remove <sc> --name N`
- `gimbal prism config get <sc> [--field timePolicy|retry|...]`
- `gimbal prism config set <sc> [--time-policy-kind ... --time-policy-seconds N --retry-enabled --retry-max-attempts N ...]`

### §X.3 Config YAML Schema

```yaml
scenario_id: sc_id           # 缺省: 从 NDJSON 文件名派生
name: "用例名"                # 缺省: 同 scenario_id
description: ""              # 缺省: ""
module: default              # 缺省: "default"
priority: 1
tags: [smoke]
services:
  api.example.com: auth-api
users:
  admin:
    url: https://api.example.com/auth/login
    username: admin
    password: ${env:ADMIN_PWD}    # v1 支持 env 占位符
    expires_in: 7200
    token_type: Authorization
time_policy:
  kind: record                   # record | timeout
  seconds: 60
retry:
  enabled: false
  max_attempts: 3
  backoff_seconds: 20
resources:
  - name: redis
    kind: mock
    image: redis:7
    port_mapping: {"6379": 6379}
```

### §X.4 退出码

| Code | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 参数错误 |
| 2 | 输入文件不存在 |
| 3 | NDJSON/YAML 空或损坏 |
| 4 | scenario/config 校验失败 |
| 5 | 内部异常 |
| 6 | edit 冲突 (如 remove 不存在的 user) |

### §X.5 常见工作流

```bash
# CI: NDJSON → scenarios/foo.yaml
gimbal prism convert -i captures/dev-1.ndjson -c cfg.yaml -o scenarios/dev-1.yaml

# 调试: 看 NDJSON 里有什么
gimbal prism inspect -i captures/dev-1.ndjson

# 调试: 看现有 scenario 长啥样
gimbal prism explain scenarios/dev-1.yaml --section meta

# 编辑: 加一个 user
gimbal prism user add scenarios/dev-1.yaml --key admin --username admin --password-env ADMIN_PWD

# 验证: 改完再 validate
gimbal prism validate -c cfg.yaml
```

---

## 15. 许可

Proprietary（仅限团队内部使用）。
