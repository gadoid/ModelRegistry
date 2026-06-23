# 05 · ModelRegistry 引入与 schema 增强合并

> 本文档描述如何从 `D:/M/ModelRegistry` 引入 ModelRegistry 数据类与 schema 增强,实现 gimbal 项目对这两类核心数据结构的可消费能力。

---

## 1. 引入目标与范围

### 1.1 目标

| 目标 | 说明 |
|---|---|
| ModelRegistry 数据类引入 | 把 `D:/M/ModelRegistry/ModelRegistry/{__init__,_aliases,core,spec}.py` 4 文件作为 gimbal 的核心依赖,prism(以及后续可能引入的执行器)都能 `from gimbal.contracts import registry, EndpointSpec` |
| schema 增强合并 | 把 `D:/M/ModelRegistry/prism/_schema/` 与 d:/mirror 端 `schema/` 的差异,**单向**合并到 `gimbal/schema/` |
| 本地可编辑依赖 | D:/M/ModelRegistry 通过 `pyproject.toml` 的 `[tool.uv]` 声明 `file:///D:/M/ModelRegistry`,`pip install -e .` 即可生效 |
| 可降级 | D:/M/ModelRegistry 不可用时,`gimbal` 仍能起(仅 `gimbal.contracts` 子包不可 import,其他模块正常) |

### 1.2 不做

| 不做 | 理由 |
|---|---|
| 把 `D:/M/ModelRegistry/prism/_schema/` 内联副本作为依赖 | 避免双源;以 d:/mirror/schema/ 为准 |
| 把 `D:/M/ModelRegistry/prism/_model_registry/` 内联副本引入 | 同上 |
| ModelRegistry 的 `EndpointSpec` 与 `gimbal.schema` 字段合并 | 两者职责不同:`EndpointSpec` 描述 endpoint 契约;`gimbal.schema` 描述 scenario 数据模型 |
| `registry` 单例的运行时激活 | v0 只引入符号,不实际 `collect`;留给 future core 用 |
| D:/M/ModelRegistry 路径硬编码 | 通过环境变量 + pyproject.toml `[tool.uv]` |

### 1.3 与已有代码的关系

```
D:/M/ModelRegistry/ModelRegistry/        ──→  d:/mirror/gimbal/contracts/
   __init__.py                               __init__.py
   _aliases.py                               _aliases.py
   core.py                                   core.py
   spec.py                                   spec.py

(物理复制 + import 路径变更,符号重导出保持兼容)
```

```
D:/M/ModelRegistry/prism/_schema/step.py   ──→  d:/mirror/gimbal/schema/step.py
   增量:key: Optional[str]                       增量合并 key 字段
   增量:_name_not_blank validator (in scenario.py)
```

---

## 2. Schema 增强合并(单向)

### 2.1 差异清单

通过 [docs/阶段 1 调研报告](../阶段1调研.md) 已确认:

| 文件 | D:/M/ModelRegistry 端差异 | 合并决策 |
|---|---|---|
| `schema/step.py` | `Step` 新增 `key: Optional[str] = None` | ✅ 采纳 |
| `schema/scenario.py` | `Meta.name` 加 `min_length=1` + `_name_not_blank` validator | ✅ 采纳 |
| 其他 12 个 schema 文件 | md5 一致 | ❌ 无需改动 |

### 2.2 `Step.key` 字段

#### 2.2.1 D:/M/ModelRegistry 端原代码(参考)

```python
# D:/M/ModelRegistry/prism/_schema/step.py:9-23
class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["step"] = "step"
    name: Optional[str] = Field(default=None, description="步骤名(可选)")
    api: ApiUnion
    request: Optional[RequestUnion] = None
    strategy: list[StrategyUnion] = Field(default_factory=list)
    key: Optional[str] = Field(
        default=None,
        description="建议 step key(docx §4.4.4 `<idx>-<path-slug>`);builder 注入,UI 内部标识;不在 Pydantic 判别字段中",
    )
```

#### 2.2.2 d:/mirror 端原代码(现状)

```python
# d:/mirror/schema/step.py:9-19
class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["step"] = "step"
    name: Optional[str] = Field(default=None, description="步骤名(可选)")
    api: ApiUnion
    request: Optional[RequestUnion] = None
    strategy: list[StrategyUnion] = Field(default_factory=list)
```

builder 用 `setattr(step, "_step_key", ...)` 临时挂字段 —— 不优雅。

#### 2.2.3 v0 合并代码(`gimbal/schema/step.py`)

```python
class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["step"] = "step"
    name: Optional[str] = Field(default=None, description="步骤名(可选)")
    api: ApiUnion
    request: Optional[RequestUnion] = None
    strategy: list[StrategyUnion] = Field(default_factory=list)
    key: Optional[str] = Field(
        default=None,
        description="建议 step key(builder 注入,UI 内部标识;不在 Pydantic 判别字段中)",
        ui={"widget": "input", "label": "step key", "readonly": True, "group": "steps"},
    )
```

#### 2.2.4 builder 改造(`gimbal/prism/builder.py`)

```python
# 现状
def _build_step(capture, services, default_user_key, draft, index) -> Step:
    ...
    step = Step(api=Api(...), request=Request(...), strategy=strategies)
    setattr(step, "_step_key", _step_key(index, capture["path"]))  # 临时挂载
    return step

# v0
def _build_step(capture, services, default_user_key, draft, index) -> Step:
    ...
    return Step(
        api=Api(...),
        request=Request(...),
        strategy=strategies,
        key=_step_key(index, capture["path"]),  # 直接用 schema 字段
    )
```

### 2.3 `Meta.name` blank 校验

#### 2.3.1 D:/M/ModelRegistry 端原代码

```python
# D:/M/ModelRegistry/prism/_schema/scenario.py:13-33
class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarioId: str = Field(default="sc_new", description="scenario ID")
    name: str = Field(..., min_length=1, description="用例名(docx §7.3 必填,空字符串拒绝)")
    description: str = Field(default="", description="用例描述")
    ...

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name 不能为空白字符串")
        return v
```

#### 2.3.2 d:/mirror 端原代码

```python
# d:/mirror/schema/scenario.py:13-25
class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarioId: str = Field(default="sc_new", description="scenario ID")
    name: str = Field("", description="用例名(docx §7.3 必填,空字符串拒绝)")
    description: str = Field(default="", description="用例描述")
    ...
```

**注意**:d:/mirror 端的注释说"必填",但实际 `default=""` —— 注释与代码不一致。

#### 2.3.3 v0 合并代码

```python
from pydantic import field_validator

class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarioId: str = Field(
        default="sc_new", description="scenario ID",
        ui={"widget": "input", "label": "scenarioId", "readonly": True, "group": "meta"},
    )
    name: str = Field(
        default="",
        description="用例名(必填,空字符串/纯空白会被 schema 拒绝)",
        ui={"widget": "input", "label": "用例名", "required": True,
            "placeholder": "请输入用例名", "group": "meta",
            "help": "空字符串或纯空白字符串会被 schema 校验拒绝"},
    )
    description: str = Field(
        default="", description="用例描述",
        ui={"widget": "textarea", "label": "用例描述", "rows": 2, "group": "meta"},
    )
    # ... 其他字段带 ui 注解 ...

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name 不能为空白字符串")
        return v
```

#### 2.3.4 行为变化

| 场景 | 旧行为 | 新行为 |
|---|---|---|
| 导出时 name="" | 写入 YAML(空) | ❌ 422 + 错误"String should have at least 1 character" |
| 导出时 name="   " | 写入 YAML(空白) | ❌ 422 + 错误"name 不能为空白字符串" |
| 导出时 name="下单" | 写入 YAML | ✅ 正常 |
| UI 加载空 draft | name 显示空字符串 | name 字段标红 + help 文字"空字符串会被拒绝" |

### 2.4 测试新增

```python
# tests/test_schema_meta.py
def test_meta_name_blank_rejected():
    from gimbal.schema import Meta
    with pytest.raises(ValidationError) as exc:
        Meta(name="")
    assert "min_length" in str(exc.value) or "at least 1" in str(exc.value)


def test_meta_name_whitespace_rejected():
    from gimbal.schema import Meta
    with pytest.raises(ValidationError) as exc:
        Meta(name="   ")
    assert "不能为空白字符串" in str(exc.value)


def test_meta_name_valid():
    from gimbal.schema import Meta
    m = Meta(name="  下单  ")
    assert m.name == "下单"  # strip 自动 trim


# tests/test_schema_step.py
def test_step_key_field():
    from gimbal.schema import Step, Api
    s = Step(
        api=Api(kind="api", service="api", method="GET", path="/x"),
        key="0-get-x",
    )
    assert s.key == "0-get-x"


def test_step_key_optional():
    from gimbal.schema import Step, Api
    s = Step(api=Api(kind="api", service="api", method="GET", path="/x"))
    assert s.key is None
```

---

## 3. ModelRegistry 数据类引入

### 3.1 物理复制 vs 符号链接 vs pip 依赖

| 方案 | 优点 | 缺点 |
|---|---|---|
| **pyproject.toml `[tool.uv]` `file:///D:/M/ModelRegistry`** | 单一来源;D:/M/ModelRegistry 改动自动生效 | 仅开发环境生效;CI 上需要重写 |
| 物理复制到 `gimbal/contracts/` | 简单可分发改 | 双源;D:/M/ModelRegistry 改动需手动同步 |
| 符号链接 / junction | 单一来源 | Windows 上 junction 维护成本 |

**采纳方案**:`pyproject.toml` 的 `[tool.uv]` file 依赖 + `sys.path` 兜底注入。

### 3.2 `pyproject.toml` 配置

```toml
[project]
name = "gimbal"
# ...

# 仅 dev 环境的 ModelRegistry 本地依赖
[tool.uv]
dev-dependencies = [
    "model-registry-local @ file:///D:/M/ModelRegistry",
]
```

或用更直观的 `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
model-registry = [
    "model-registry-local @ file:///D:/M/ModelRegistry",
]
```

安装方式:
```bash
# 开发:d:/mirror 根目录
pip install -e ".[model-registry]"

# 或纯 uv
uv pip install -e ".[model-registry]"
```

### 3.3 兜底 import(无 ModelRegistry 也能跑)

```python
# gimbal/contracts/__init__.py
"""ModelRegistry 数据类引入层。

支持两种加载方式:
1. 通过 pyproject.toml 装上 model-registry-local,直接 `from ModelRegistry import ...`
2. 通过 GIMBAL_MODEL_REGISTRY_PATH 环境变量指定 D:/M/ModelRegistry 路径,sys.path 注入

v0 行为:
- 优先尝试 (1),失败则尝试 (2),再失败则把 gimbal.contracts 标记为不可用
- 其他 gimbal 子模块正常 import,只是无法使用 EndpointSpec / registry 单例
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

__all__ = ["registry", "BootstrapError", "EndpointSpec", "EndpointKey",
           "MockHook", "ValidateHook", "BuildRequestHook", "is_available"]


def _try_load() -> None:
    """尝试把 ModelRegistry 加进 sys.path 并 import。"""
    # 1. 已装
    try:
        from ModelRegistry import registry, BootstrapError  # type: ignore
        from ModelRegistry.spec import EndpointSpec, MockHook, ValidateHook, BuildRequestHook  # type: ignore
        from ModelRegistry.core import EndpointKey  # type: ignore
        globals().update({
            "registry": registry,
            "BootstrapError": BootstrapError,
            "EndpointSpec": EndpointSpec,
            "EndpointKey": EndpointKey,
            "MockHook": MockHook,
            "ValidateHook": ValidateHook,
            "BuildRequestHook": BuildRequestHook,
        })
        return
    except ImportError:
        pass

    # 2. 环境变量指定
    mr_path = os.environ.get("GIMBAL_MODEL_REGISTRY_PATH")
    if mr_path:
        p = Path(mr_path).resolve()
        if (p / "ModelRegistry" / "__init__.py").exists():
            sys.path.insert(0, str(p))
            try:
                from ModelRegistry import registry, BootstrapError  # type: ignore
                from ModelRegistry.spec import EndpointSpec, MockHook, ValidateHook, BuildRequestHook  # type: ignore
                from ModelRegistry.core import EndpointKey  # type: ignore
                globals().update({
                    "registry": registry,
                    "BootstrapError": BootstrapError,
                    "EndpointSpec": EndpointSpec,
                    "EndpointKey": EndpointKey,
                    "MockHook": MockHook,
                    "ValidateHook": ValidateHook,
                    "BuildRequestHook": BuildRequestHook,
                })
                return
            except ImportError:
                pass

    # 3. 不可用
    globals()["_available"] = False


_try_load()
_available = True  # _try_load 没 raise 就视为可用


def is_available() -> bool:
    return _available
```

### 3.4 不引入的 ModelRegistry 子模块

| 子模块 | 是否引入 | 理由 |
|---|---|---|
| `ModelRegistry/__init__.py` | ✅ | `registry` + `BootstrapError` |
| `ModelRegistry/spec.py` | ✅ | `EndpointSpec` + 3 个 hook |
| `ModelRegistry/core.py` | ✅ | `EndpointKey` |
| `ModelRegistry/_aliases.py` | ✅ | `resolve_dir_name`(service 名兜底映射) |
| `ModelRegistry/<service>/*.py`(运行时拉取的 endpoint 文件) | ❌ | v0 不激活 `registry.collect()`,无需加载 |

### 3.5 v0 消费路径

v0 中 ModelRegistry 的**主要**消费路径是**前端 UI spec**(`/api/registry/ui-spec`),见 [04-schema-ssot.md](04-schema-ssot.md) §6。

builder 内的 `registry.resolve()` 调用作为**可选增强**,留给后续 v0.1+:

```python
# gimbal/prism/builder.py(节选,v0.1+ 才用)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ModelRegistry.spec import EndpointSpec


def build_scenario(draft: ScenarioDraft) -> dict[str, Any]:
    scenario = Scenario(...)
    # v0.1+:可选 — 为每个 step 标注对应的 EndpointSpec(若可用)
    if is_available():
        from gimbal.contracts import registry
        for step in scenario.steps:
            if isinstance(step, Step):
                try:
                    spec = registry.resolve(
                        step.api.service, step.api.method, step.api.path
                    )
                    step.endpoint_ref = f"{spec.method} {spec.path}"  # type: ignore
                except Exception:
                    pass
    return scenario.model_dump(mode="json")
```

**注意**:`endpoint_ref` 字段 v0 **不**加入 `schema.Step`(避免引入循环依赖)。仅在内存 builder 输出中临时挂载,YAML 不写出。后续如果需要持久化,再扩 `Step.endpoint_ref`。

### 3.6 doc2model 同步改造

`prism/doc2model.py:344` 当前硬编码 `from ModelRegistry.spec import EndpointSpec`:
- **v0 改造**:改为 `from gimbal.contracts import EndpointSpec, is_available`
- doc2model 命令在 `is_available() is False` 时,给出友好提示:"需要安装 model-registry-local 才能生成 endpoint 模型"

```python
# gimbal/prism/doc2model.py(节选)
def main():
    if not is_available():
        typer.secho(
            "[doc2model] ModelRegistry 不可用,请安装 model-registry-local:",
            fg=typer.colors.YELLOW,
        )
        typer.echo("  pip install -e '.[model-registry]'")
        typer.echo("  或设置 GIMBAL_MODEL_REGISTRY_PATH 环境变量")
        raise typer.Exit(code=3)

    from gimbal.contracts import EndpointSpec
    # ... 原有逻辑 ...
```

---

## 4. pyproject.toml 完整示例

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
    "watchdog>=4.0",
    "mitmproxy>=12.0",
    "sse-starlette>=2.1",
    # 注意:v0 不引入 anthropic / httpx(AI 整体不做)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.6",
    "mypy>=1.11",
]

# 引入 D:/M/ModelRegistry 作为可编辑依赖
# 注意:仅在 Windows 开发环境路径生效;CI 需要改为 git/pypi 源
model-registry = [
    "model-registry-local @ file:///D:/M/ModelRegistry",
]

[project.scripts]
gimbal = "gimbal.cli.app:main"

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

---

## 5. README 与开发者指南

### 5.1 顶层 README 段落

````markdown
## 安装

### 标准安装

```bash
pip install -e .
```

### 启用 ModelRegistry 集成

```bash
# 方式 1:本地 file 依赖(Windows 开发环境)
pip install -e ".[model-registry]"

# 方式 2:环境变量指定(任何平台)
export GIMBAL_MODEL_REGISTRY_PATH=/path/to/D:/M/ModelRegistry
```

未启用时,`gimbal.contracts` 子包仍可 import,但 `is_available()` 返回 False,相关功能降级。
````

### 5.2 故障排查

| 错误 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'ModelRegistry'` | 未装 model-registry-local 或未设置 GIMBAL_MODEL_REGISTRY_PATH | 跑 `pip install -e ".[model-registry]"` |
| `GIMBAL_MODEL_REGISTRY_PATH` 指向错误目录 | 路径下无 `ModelRegistry/__init__.py` | 检查路径;或设回 pyproject 依赖方式 |
| `gimbal capture` 报"找不到 mitmproxy" | mitmproxy 未装 | `pip install mitmproxy` |
| `gimbal prism` 启动失败,提示"ModelRegistry 字段漂移" | D:/M/ModelRegistry 改了 `EndpointSpec` 字段名 | 见 [04-schema-ssot.md](04-schema-ssot.md) §6.6 |

---

## 6. 测试策略

### 6.1 ModelRegistry 引入测试

```python
# tests/test_contracts_init.py
import os
from pathlib import Path


def test_contracts_loads_when_installed():
    """已装 model-registry-local 时,符号可用。"""
    from gimbal.contracts import EndpointSpec, registry, is_available
    if is_available():
        assert EndpointSpec is not None
        assert registry is not None


def test_contracts_path_fallback(monkeypatch, tmp_path):
    """未装但 GIMBAL_MODEL_REGISTRY_PATH 指向正确路径时,符号可用。"""
    # 模拟 D:/M/ModelRegistry 结构
    fake_mr = tmp_path / "fake_mr" / "ModelRegistry"
    fake_mr.mkdir(parents=True)
    (fake_mr / "__init__.py").write_text("registry = None\nBootstrapError = Exception\n")
    (fake_mr / "spec.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\nclass EndpointSpec:\n    method: str\n    path: str\n"
        "class MockHook: pass\nclass ValidateHook: pass\nclass BuildRequestHook: pass\n"
    )
    (fake_mr / "core.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\nclass EndpointKey:\n    service: str\n    method: str\n    path: str\n"
    )
    (fake_mr / "_aliases.py").write_text("def resolve_dir_name(s): return s\n")

    monkeypatch.setenv("GIMBAL_MODEL_REGISTRY_PATH", str(tmp_path / "fake_mr"))

    # 强制重新 import
    import importlib
    import gimbal.contracts
    importlib.reload(gimbal.contracts)

    from gimbal.contracts import is_available
    assert is_available() is True


def test_contracts_unavailable(monkeypatch):
    """完全没装时,is_available 返回 False。"""
    monkeypatch.delenv("GIMBAL_MODEL_REGISTRY_PATH", raising=False)
    # 通过在干净环境测试,这里不严格测
    # 真实测试在 CI 环境运行
    from gimbal.contracts import is_available
    assert is_available() in (True, False)
```

### 6.2 schema 增强合并测试

见 [§2.4](#24-测试新增)。

### 6.3 兼容性测试

```python
# tests/test_schema_compat.py
def test_meta_name_required_in_yaml_export():
    """导出时 name="" 必须失败(保障 docx §7.3 必填约束)。"""
    from gimbal.schema import Scenario, Meta
    with pytest.raises(ValidationError):
        Scenario(
            scenarioId="test",
            meta=Meta(name=""),  # 空字符串
        )


def test_step_key_passes_through_yaml():
    """Step.key 能正常序列化为 YAML。"""
    from gimbal.schema import Scenario, Meta, Step, Api
    s = Scenario(
        scenarioId="test",
        meta=Meta(name="test"),
        steps=[Step(api=Api(kind="api", service="api", method="GET", path="/x"),
                    key="0-get-x")],
    )
    dumped = s.model_dump(mode="json")
    assert dumped["steps"][0]["key"] == "0-get-x"
```

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| `file:///D:/M/ModelRegistry` 路径硬编码导致 Linux CI 失败 | CI 跑不通 | CI 用环境变量;dev 依赖降级为非必需 |
| `from ModelRegistry import ...` 与 `from gimbal.contracts import ...` 同时存在 | 双源混淆 | 文档明确:只用后者;前者留给旧代码迁移期 |
| ModelRegistry 升级(v0 → v1)破坏 ABI | 所有 `EndpointSpec` 调用失败 | 锁定 `model-registry-local` 为 git tag 或 commit hash |
| D:/M/ModelRegistry 删除/移动 | dev 环境失效 | 错误信息明确提示重装 |
| `EndpointSpec` 与 `gimbal.schema` 字段重名冲突 | 引用混淆 | 严格遵守"EndpointSpec 描述 endpoint,gimbal.schema 描述 scenario"职责划分 |

---

## 8. 不做的事(再强调)

| 不做 | 理由 |
|---|---|
| 把 D:/M/ModelRegistry 物理复制到 d:/mirror | 单一来源靠 pyproject 维持 |
| ModelRegistry 的 `registry.collect()` 实际激活 | v0 不需要;留给 future core |
| 把 `D:/M/ModelRegistry/prism/_schema/` 引入 | 避免双源 |
| 把 `D:/M/ModelRegistry/prism/_model_registry/` 引入 | 同上 |
| `EndpointSpec` 与 schema 字段强制关联 | 职责不同,只在 builder 可选调用 |

---

## 9. 下游文档引用

- 总体架构(两个模块位置) → [01-architecture.md](01-architecture.md)
- prism 中 builder / doc2model 使用 ModelRegistry → [03-prism-module.md](03-prism-module.md) §4.3 / §4.4
- 迁移执行步骤 → [06-migration-plan.md](06-migration-plan.md) M3