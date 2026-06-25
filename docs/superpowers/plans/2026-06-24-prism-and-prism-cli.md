# prism & prism-cli 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `gimbal prism` 下新增 9 个 headless CLI 子命令 (5 pipeline + 4 edit groups)，全部走新的 `gimbal.prism.core` 共享模块（复用以有的 `builder.build_scenario()`）；web prism 一行不动。

**Architecture:**
- `gimbal/prism/core.py` 新增：(A) pipeline 函数 `parse_ndjson / load_config / render / write / inspect_ndjson / validate_config / ndjson_to_step_fragments`；(B) edit 原语 `load_scenario / save_scenario / validate_scenario / explain_scenario / get_meta / set_meta / list_users / add_user / remove_user / list_resources / add_resource / remove_resource / get_config_section / set_config_section`。
- `gimbal/prism/cli.py` (单文件含 `start_cmd`) 拆为 `gimbal/prism/cli/` 子包：`start.py` 保留 `start_cmd`，新加 `_shared.py` + 7 个 subcommand 文件 + `edit/` 子目录。
- `gimbal/cli/prism.py` 在现有 `prism_app` 上挂载 9 个新子命令。
- Parity canary 测试断言 web 与 CLI 输出 byte-identical。

**Tech Stack:** Python 3.11+ / Typer (CLI) / Pydantic v2 / pytest / `pyyaml` / `json`（标准库）。无新第三方依赖。

---

## Global Constraints

- **Web prism 不动**: `gimbal/prism/server.py` / `builder.py` / `state.py` / `convert.py` / `render/` / `static/` 本期一行不改。
- **核心复用**: `core.py` 必须**调用** `gimbal.prism.builder.build_scenario()`，不重新实现 scenario 拼装。
- **CLI 子包迁移**: `gimbal/prism/cli.py` 旧文件迁到 `gimbal/prism/cli/start.py`；`gimbal/prism/cli/__init__.py` re-export `start_cmd` 以保持 `from gimbal.prism.cli import start_cmd` 兼容。
- **退出码统一**: 0 / 1 / 2 / 3 / 4 / 5 / 6 (见 spec §5.3)。
- **流划分**: data → stdout / logs & errors → stderr。
- **CLI config YAML 字段**: snake_case (`time_policy`, `retry`)，与 Pydantic camelCase 字段 (`timePolicy`, `retry`) 在 `core.py` 内部映射。
- **Step 来源**: 仅 NDJSON；CLI 不提供 step-level 编辑（推迟到 §6.2）。
- **占位符**: v1 仅支持 `${env:VAR}` 一种环境变量引用；密码字段可填 `${env:ADMIN_PWD}`，加载时 `os.environ` 解析。
- **测试基线**: 现有 237 passed / 4 skipped 必须保持绿。
- **不引入新依赖**: `requirements.txt` 不变。
- **分支**: 本期工作在 `feature/prism-cli` 分支（已创建）。
- **commit 约定**: 中文 commit 前缀，参考最近历史 (`fix(steps): ...`、`refactor(steps): ...`)。

---

## File Map

| 文件 | 改动 | 职责 |
|---|---|---|
| `gimbal/prism/core.py` | NEW | Pipeline + edit 原语（§5.1） |
| `gimbal/prism/cli/__init__.py` | NEW | Typer app 装配 + re-export `start_cmd` |
| `gimbal/prism/cli/_shared.py` | NEW | 共享工具（load_yaml / save_yaml / exit / error formatter） |
| `gimbal/prism/cli/start.py` | NEW (from old `cli.py`) | `start_cmd`（web 启动） |
| `gimbal/prism/cli/convert.py` | NEW | `convert_cmd` (full pipeline) |
| `gimbal/prism/cli/inspect.py` | NEW | `inspect_cmd` (NDJSON 统计) |
| `gimbal/prism/cli/validate.py` | NEW | `validate_cmd` (config 校验) |
| `gimbal/prism/cli/to_steps.py` | NEW | `to_steps_cmd` (NDJSON → step fragments JSON) |
| `gimbal/prism/cli/explain.py` | NEW | `explain_cmd` (scenario 结构摘要) |
| `gimbal/prism/cli/edit/__init__.py` | NEW | (空, 仅占位) |
| `gimbal/prism/cli/edit/meta.py` | NEW | `meta get/set` |
| `gimbal/prism/cli/edit/user.py` | NEW | `user list/add/remove` |
| `gimbal/prism/cli/edit/resource.py` | NEW | `resource list/add/remove` |
| `gimbal/prism/cli/edit/config.py` | NEW | `config get/set` |
| `gimbal/prism/cli.py` | DELETE | 移到 `cli/start.py` |
| `gimbal/cli/prism.py` | MODIFY | 挂载新子命令 |
| `tests/test_prism_core.py` | NEW | core 单元测试 (~14 cases) |
| `tests/test_prism_core_builder_parity.py` | NEW | parity canary (2 cases) |
| `tests/test_prism_cli_convert.py` | NEW | convert CLI 测试 |
| `tests/test_prism_cli_inspect.py` | NEW | inspect CLI 测试 |
| `tests/test_prism_cli_validate.py` | NEW | validate CLI 测试 |
| `tests/test_prism_cli_to_steps.py` | NEW | to-steps CLI 测试 |
| `tests/test_prism_cli_explain.py` | NEW | explain CLI 测试 |
| `tests/test_prism_cli_meta.py` | NEW | meta CLI 测试 |
| `tests/test_prism_cli_user.py` | NEW | user CLI 测试 |
| `tests/test_prism_cli_resource.py` | NEW | resource CLI 测试 |
| `tests/test_prism_cli_config.py` | NEW | config CLI 测试 |
| `tests/fixtures/sample_config.yaml` | NEW | 测试用完整 config |
| `tests/fixtures/minimal_captures.ndjson` | NEW | 测试用最小 NDJSON (1 event) |
| `README.md` | MODIFY | 子命令表更新 |
| `USER_MANUAL.md` | MODIFY | 新增 §X "Headless CLI" |
| `CHANGELOG.md` | MODIFY | 加 v0.6.0 条目 |

---

## Task 1: core.py 基础 - parse_ndjson

**Files:**
- Create: `gimbal/prism/core.py`
- Create: `tests/test_prism_core.py`
- Create: `tests/fixtures/minimal_captures.ndjson`

**Interfaces:**
- `parse_ndjson(path: Path) -> list[dict[str, Any]]`
- Raises: `FileNotFoundError` if path missing; `ValueError("no events")` if file empty; `json.JSONDecodeError` propagated for malformed lines.

- [ ] **Step 1: 创建最小 NDJSON fixture**

`tests/fixtures/minimal_captures.ndjson`:
```json
{"ts": 1.0, "method": "GET", "host": "api.example.com", "scheme": "https", "port": 443, "path": "/health", "query": {}, "headers": {}, "body": "", "response": {"status": 200}}
```

- [ ] **Step 2: 创建空 `core.py` 文件**

`gimbal/prism/core.py`:
```python
"""gimbal.prism.core — shared pipeline + edit primitives used by prism-cli.

OBLIGATION: This module must call builder.build_scenario() under the hood
and stay in sync with it. tests/test_prism_core_builder_parity.py is the
canary that detects drift.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
```

- [ ] **Step 3: 写失败的测试**

`tests/test_prism_core.py`:
```python
"""Unit tests for gimbal.prism.core."""
from __future__ import annotations

from pathlib import Path

import pytest

from gimbal.prism import core

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ndjson_returns_list_of_events():
    result = core.parse_ndjson(FIXTURES / "minimal_captures.ndjson")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["method"] == "GET"
    assert result[0]["path"] == "/health"


def test_parse_ndjson_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        core.parse_ndjson(tmp_path / "nope.ndjson")


def test_parse_ndjson_empty_file_raises(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.write_text("")
    with pytest.raises(ValueError, match="no events"):
        core.parse_ndjson(p)
```

- [ ] **Step 4: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py -v`
Expected: FAIL (function `parse_ndjson` not defined → ImportError or AttributeError).

- [ ] **Step 5: 实现 `parse_ndjson`**

追加到 `gimbal/prism/core.py`:
```python
def parse_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read an NDJSON file and return all events as a list of dicts.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if file is empty (no events).
        json.JSONDecodeError: propagated from json.loads for malformed lines.
    """
    if not path.exists():
        raise FileNotFoundError(f"ndjson not found: {path}")
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if not events:
        raise ValueError(f"ndjson has no events: {path}")
    return events
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (3 cases).

- [ ] **Step 7: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py tests/fixtures/minimal_captures.ndjson
git commit -m "feat(prism-core): add parse_ndjson primitive (TDD)"
```

---

## Task 2: core.py - load_config

**Files:**
- Modify: `gimbal/prism/core.py`
- Modify: `tests/test_prism_core.py`
- Create: `tests/fixtures/sample_config.yaml`

**Interfaces:**
- `load_config(path: Path | None, events: list[dict[str, Any]]) -> ScenarioDraft`
- Returns a `gimbal.prism.builder.ScenarioDraft` populated from config YAML.
- If `path is None`: returns default draft with steps filled from events.
  - scenario_id derived from first event's `host` + `path` via `_scenario_id_from_events(events)` (e.g., `host=api.example.com, path=/x` → `sc_api_example_com_x`).
  - If `events` is empty → `sc_default`.
- Field mapping: `time_policy.kind` → `timePolicyKind`, `retry.max_attempts` → `retryMaxAttempts`, etc. (snake_case in YAML, camelCase on draft).

- [ ] **Step 1: 创建 sample config fixture**

`tests/fixtures/sample_config.yaml`:
```yaml
scenario_id: sc_sample
name: "Sample scenario"
description: "Used in tests"
module: auth
priority: 1
author: tester
owner: team
tags: [smoke]
version: "1.0.0"
expire: false
requirement_ref: []

services:
  api.example.com: auth-api

users:
  admin:
    url: https://api.example.com/auth/login
    username: admin
    password: secret123
    expires_in: 7200
    token_type: Authorization

time_policy:
  kind: record
  seconds: 60

retry:
  enabled: false
  max_attempts: 3
  backoff_seconds: 20
  retry_on: []

setup_refs: []
teardown_refs: []

resources: []
```

- [ ] **Step 2: 加失败的测试**

追加到 `tests/test_prism_core.py`:
```python
from gimbal.prism.builder import ScenarioDraft


def test_load_config_none_returns_default_draft():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    assert isinstance(draft, ScenarioDraft)
    # scenario_id 从 first event 的 host + path 派生
    assert draft.scenario_id == "sc_api_example_com_x"
    assert len(draft.steps) == 1


def test_load_config_none_with_empty_events_uses_sc_default():
    draft = core.load_config(None, [])
    assert draft.scenario_id == "sc_default"
    assert draft.steps == []


def test_load_config_full_yaml():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(FIXTURES / "sample_config.yaml", events)
    assert draft.scenario_id == "sc_sample"
    assert draft.name == "Sample scenario"
    assert "admin" in draft.users
    assert draft.services == {"api.example.com": "auth-api"}
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py::test_load_config_none_returns_default_draft -v`
Expected: FAIL (`load_config` not defined).

- [ ] **Step 4: 实现 `load_config`**

追加到 `gimbal/prism/core.py`:
```python
import yaml

from gimbal.prism.builder import (
    AuthDraft,
    ResourceDraft,
    ScenarioDraft,
    StepDraft,
)


def _scenario_id_from_events(events: list[dict[str, Any]]) -> str:
    """Derive scenario_id from first event's host/path. Default: 'sc_default'."""
    if not events:
        return "sc_default"
    first = events[0]
    host = (first.get("host") or "default").replace(".", "_").replace("-", "_")
    path = (first.get("path") or "").replace("/", "_").strip("_") or "x"
    return f"sc_{host}_{path}"[:64]


def load_config(
    path: Path | None, events: list[dict[str, Any]],
) -> ScenarioDraft:
    """Load scenario config YAML into a ScenarioDraft.

    If path is None, returns a default draft populated only with steps from events.
    Field names in YAML use snake_case (time_policy, retry); translated to
    camelCase (timePolicyKind, retryMaxAttempts) on the draft.
    """
    if path is None:
        sid = _scenario_id_from_events(events)
        return ScenarioDraft(
            scenario_id=sid,
            name=sid,
            steps=[StepDraft(capture=e) for e in events],
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    users: dict[str, AuthDraft] = {}
    for k, v in (raw.get("users") or {}).items():
        users[k] = AuthDraft(
            url=v.get("url", ""),
            username=v.get("username", ""),
            password=v.get("password", ""),
            expires_in=v.get("expires_in", 7200),
            token_type=v.get("token_type", "Authorization"),
            token=v.get("token"),
        )
    resources: dict[str, ResourceDraft] = {}
    for r in (raw.get("resources") or []):
        resources[r["name"]] = ResourceDraft(
            name=r["name"],
            kind=r.get("kind", "mock"),
            image=r.get("image", ""),
            config=r.get("config") or {},
            port_mapping={str(k): v for k, v in (r.get("port_mapping") or {}).items()},
            path=r.get("path", ""),
            ref=r.get("ref", ""),
            value=r.get("value"),
        )
    tp = raw.get("time_policy") or {}
    rt = raw.get("retry") or {}
    return ScenarioDraft(
        scenario_id=raw.get("scenario_id", _scenario_id_from_events(events)),
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        module=raw.get("module", "default"),
        priority=raw.get("priority", 1),
        author=raw.get("author", "prism"),
        owner=raw.get("owner", "prism"),
        tags=raw.get("tags") or ["smoke"],
        version=raw.get("version", "1.0.0"),
        expire=raw.get("expire", False),
        requirement_ref=raw.get("requirement_ref") or [],
        services=raw.get("services") or {},
        users=users,
        time_policy_kind=tp.get("kind", "record"),
        time_policy_seconds=tp.get("seconds", 60),
        retry_enabled=rt.get("enabled", False),
        retry_max_attempts=rt.get("max_attempts", 3),
        retry_backoff_seconds=rt.get("backoff_seconds", 20.0),
        retry_on=rt.get("retry_on") or [],
        setup_refs=raw.get("setup_refs") or [],
        teardown_refs=raw.get("teardown_refs") or [],
        resources=resources,
        steps=[StepDraft(capture=e) for e in events],
    )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (5 cases total).

- [ ] **Step 6: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py tests/fixtures/sample_config.yaml
git commit -m "feat(prism-core): add load_config with snake_case YAML schema"
```

---

## Task 3: core.py - render + ConvertResult

**Files:**
- Modify: `gimbal/prism/core.py`
- Modify: `tests/test_prism_core.py`

**Interfaces:**
- `ConvertResult` dataclass: `scenario: dict`, `output_path: Path | None`, `yaml_text: str`, `warnings: list[str]`, `event_count: int`, `step_count: int`.
- `render(draft: ScenarioDraft) -> dict[str, Any]` — calls `builder.build_scenario(draft).model_dump(mode="json")`; validates with `Scenario.model_validate`.

- [ ] **Step 1: 加失败的测试**

追加到 `tests/test_prism_core.py`:
```python
from gimbal.schema import Scenario


def test_render_minimal_produces_valid_scenario():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    result = core.render(draft)
    assert isinstance(result, dict)
    # 必须能被 Scenario 验证
    Scenario.model_validate(result)
    assert result["scenarioId"].startswith("sc_")


def test_render_full_yaml():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(FIXTURES / "sample_config.yaml", events)
    result = core.render(draft)
    assert result["scenarioId"] == "sc_sample"
    assert "admin" in result["config"]["users"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py::test_render_minimal_produces_valid_scenario -v`
Expected: FAIL.

- [ ] **Step 3: 实现 `render` + `ConvertResult`**

追加到 `gimbal/prism/core.py`:
```python
from dataclasses import dataclass, field

from gimbal.prism.builder import build_scenario
from gimbal.schema import Scenario


@dataclass
class ConvertResult:
    scenario: dict[str, Any]
    output_path: Path | None
    yaml_text: str
    warnings: list[str] = field(default_factory=list)
    event_count: int = 0
    step_count: int = 0


def render(draft: ScenarioDraft) -> dict[str, Any]:
    """Render ScenarioDraft to a validated scenario dict.

    Calls builder.build_scenario() and validates against Scenario schema.
    Raises pydantic.ValidationError on invalid scenarios.
    """
    scenario = build_scenario(draft)
    Scenario.model_validate(scenario)
    return scenario
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (7 cases).

- [ ] **Step 5: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py
git commit -m "feat(prism-core): add render() wrapping builder + ConvertResult"
```

---

## Task 4: core.py - write + convert_ndjson_to_scenario

**Files:**
- Modify: `gimbal/prism/core.py`
- Modify: `tests/test_prism_core.py`

**Interfaces:**
- `write(result: ConvertResult, output_path: Path | None) -> None` — mutates `result.yaml_text` and writes file if `output_path` is given.
- `convert_ndjson_to_scenario(ndjson_path, config_path, output_path=None) -> ConvertResult` — full pipeline orchestrator.

- [ ] **Step 1: 加失败的测试**

追加到 `tests/test_prism_core.py`:
```python
def test_write_returns_yaml_when_no_output():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    result = core.ConvertResult(scenario=scenario, output_path=None, yaml_text="",
                                event_count=1, step_count=1)
    core.write(result, None)
    assert "scenarioId:" in result.yaml_text
    assert result.output_path is None


def test_write_writes_file_when_output_given(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    result = core.ConvertResult(scenario=scenario, output_path=None, yaml_text="",
                                event_count=1, step_count=1)
    out = tmp_path / "out.yaml"
    core.write(result, out)
    assert out.exists()
    assert "scenarioId:" in out.read_text(encoding="utf-8")
    assert result.output_path == out


def test_convert_ndjson_to_scenario_full_pipeline(tmp_path):
    out = tmp_path / "sc.yaml"
    result = core.convert_ndjson_to_scenario(
        FIXTURES / "minimal_captures.ndjson",
        None, out,
    )
    assert result.event_count == 1
    assert result.step_count == 1
    assert out.exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py::test_write_returns_yaml_when_no_output -v`
Expected: FAIL.

- [ ] **Step 3: 实现 `write` + `convert_ndjson_to_scenario`**

追加到 `gimbal/prism/core.py`:
```python
def write(result: ConvertResult, output_path: Path | None) -> None:
    """Serialize result.scenario to YAML and write to output_path (if given).

    Mutates result.yaml_text and result.output_path.
    """
    yaml_text = yaml.safe_dump(
        result.scenario, allow_unicode=True, sort_keys=False,
    )
    result.yaml_text = yaml_text
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_text, encoding="utf-8")
        result.output_path = output_path


def convert_ndjson_to_scenario(
    ndjson_path: Path,
    config_path: Path | None,
    output_path: Path | None = None,
) -> ConvertResult:
    """Full pipeline: NDJSON + optional config → Scenario YAML.

    Pipeline: parse → load_config → render → write.
    """
    events = parse_ndjson(ndjson_path)
    draft = load_config(config_path, events)
    scenario = render(draft)
    enabled_steps = [s for s in draft.steps if s.enabled]
    result = ConvertResult(
        scenario=scenario,
        output_path=None,
        yaml_text="",
        event_count=len(events),
        step_count=len(enabled_steps),
    )
    write(result, output_path)
    return result
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (10 cases).

- [ ] **Step 5: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py
git commit -m "feat(prism-core): add write + convert_ndjson_to_scenario pipeline"
```

---

## Task 5: core.py - inspect_ndjson + validate_config + ndjson_to_step_fragments

**Files:**
- Modify: `gimbal/prism/core.py`
- Modify: `tests/test_prism_core.py`

**Interfaces:**
- `NdjsonStats` dataclass: `event_count: int`, `method_counts: dict[str,int]`, `host_counts: dict[str,int]`, `status_counts: dict[int,int]`, `sample_events: list[dict]`.
- `inspect_ndjson(path: Path, sample_limit: int = 3) -> NdjsonStats`.
- `validate_config(path: Path) -> list[str]` — returns list of error messages (empty = valid).
- `ndjson_to_step_fragments(ndjson_path, config_path) -> list[dict[str, Any]]`.

- [ ] **Step 1: 加失败的测试**

追加到 `tests/test_prism_core.py`:
```python
def test_inspect_ndjson_stats():
    stats = core.inspect_ndjson(FIXTURES / "sample_captures.ndjson", sample_limit=2)
    assert stats.event_count == 3
    assert stats.method_counts == {"POST": 1, "GET": 2}
    assert stats.host_counts == {"api.example.com": 3}
    assert stats.status_counts == {200: 2, 404: 1}
    assert len(stats.sample_events) == 2


def test_validate_config_returns_empty_for_valid():
    errors = core.validate_config(FIXTURES / "sample_config.yaml")
    assert errors == []


def test_validate_config_returns_errors_for_invalid(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenario_id: 123\nname: ''\n")  # name 不能为空
    errors = core.validate_config(bad)
    assert any("name" in e.lower() for e in errors)


def test_ndjson_to_step_fragments_returns_list():
    frags = core.ndjson_to_step_fragments(FIXTURES / "minimal_captures.ndjson", None)
    assert isinstance(frags, list)
    assert len(frags) == 1
    assert "api" in frags[0]
    assert "request" in frags[0]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py::test_inspect_ndjson_stats -v`
Expected: FAIL.

- [ ] **Step 3: 实现三个函数**

追加到 `gimbal/prism/core.py`:
```python
from collections import Counter


@dataclass
class NdjsonStats:
    event_count: int
    method_counts: dict[str, int]
    host_counts: dict[str, int]
    status_counts: dict[int, int]
    sample_events: list[dict[str, Any]]


def inspect_ndjson(path: Path, sample_limit: int = 3) -> NdjsonStats:
    """Compute stats over NDJSON events."""
    events = parse_ndjson(path)
    methods: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    statuses: Counter[int] = Counter()
    for e in events:
        methods[(e.get("method") or "GET").upper()] += 1
        hosts[e.get("host") or ""] += 1
        st = (e.get("response") or {}).get("status")
        if st is not None:
            statuses[st] += 1
    return NdjsonStats(
        event_count=len(events),
        method_counts=dict(methods),
        host_counts=dict(hosts),
        status_counts=dict(statuses),
        sample_events=events[:sample_limit],
    )


def validate_config(path: Path) -> list[str]:
    """Validate a config YAML against Scenario schema (after loading events).

    Returns a list of error strings; empty list means valid.
    For pure config validation without events, we use a synthetic event so
    build_scenario doesn't reject on empty steps.
    """
    events = [{"host": "_validate", "method": "GET", "path": "/_validate",
               "headers": {}, "body": "", "response": {"status": 200}}]
    try:
        draft = load_config(path, events)
        render(draft)
        return []
    except Exception as e:  # noqa: BLE001
        return [str(e)]


def ndjson_to_step_fragments(
    ndjson_path: Path, config_path: Path | None,
) -> list[dict[str, Any]]:
    """Convert NDJSON to step fragment dicts (no scenario assembly)."""
    from gimbal.prism.convert import convert_record, load_rules  # noqa: PLC0415

    events = parse_ndjson(ndjson_path)
    rules = load_rules(None)  # default rules; config file's services handled later
    if config_path is not None:
        cfg_raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        rules["services"].update(cfg_raw.get("services") or {})
    return [convert_record(e, rules) for e in events]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (14 cases).

- [ ] **Step 5: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py
git commit -m "feat(prism-core): add inspect_ndjson + validate_config + ndjson_to_step_fragments"
```

---

## Task 6: core.py - edit primitives (load/save/validate_scenario + explain)

**Files:**
- Modify: `gimbal/prism/core.py`
- Modify: `tests/test_prism_core.py`

**Interfaces:**
- `load_scenario(path: Path) -> dict[str, Any]` — read YAML, return dict.
- `save_scenario(scenario: dict, path: Path) -> None` — write dict to YAML.
- `validate_scenario(scenario: dict) -> None` — raises `ValidationError` on invalid.
- `explain_scenario(scenario: dict) -> dict[str, Any]` — produce structured summary.

- [ ] **Step 1: 加失败的测试**

追加到 `tests/test_prism_core.py`:
```python
def test_load_save_scenario_roundtrip(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    p = tmp_path / "sc.yaml"
    core.save_scenario(scenario, p)
    loaded = core.load_scenario(p)
    assert loaded["scenarioId"] == scenario["scenarioId"]


def test_validate_scenario_passes_for_valid():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    core.validate_scenario(scenario)  # 不抛 = 通过


def test_explain_scenario_returns_summary():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    summary = core.explain_scenario(scenario)
    assert "meta" in summary
    assert "steps_count" in summary
    assert summary["steps_count"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py::test_load_save_scenario_roundtrip -v`
Expected: FAIL.

- [ ] **Step 3: 实现四个函数**

追加到 `gimbal/prism/core.py`:
```python
from pydantic import ValidationError as PydanticValidationError


def load_scenario(path: Path) -> dict[str, Any]:
    """Load scenario YAML into a plain dict. Does NOT validate."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_scenario(scenario: dict[str, Any], path: Path) -> None:
    """Write scenario dict back to YAML. Preserves key order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def validate_scenario(scenario: dict[str, Any]) -> None:
    """Validate scenario dict against gimbal.schema.Scenario.

    Raises pydantic.ValidationError on failure.
    """
    Scenario.model_validate(scenario)


def explain_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Produce structured summary of a scenario."""
    return {
        "scenarioId": scenario.get("scenarioId"),
        "meta": scenario.get("meta", {}),
        "config": {
            "services": list((scenario.get("config") or {}).get("services", {}).keys()),
            "users": list((scenario.get("config") or {}).get("users", {}).keys()),
            "timePolicy": (scenario.get("config") or {}).get("timePolicy"),
            "retry": (scenario.get("config") or {}).get("retry"),
        },
        "steps_count": len(scenario.get("steps") or []),
        "resources": list((scenario.get("resource") or {}).keys()),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (17 cases).

- [ ] **Step 5: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py
git commit -m "feat(prism-core): add load/save/validate_scenario + explain_scenario"
```

---

## Task 7: core.py - section edit primitives (meta / users / resources / config)

**Files:**
- Modify: `gimbal/prism/core.py`
- Modify: `tests/test_prism_core.py`

**Interfaces:**
- `get_meta(scenario) -> dict`
- `set_meta(scenario, **fields) -> dict`
- `list_users(scenario) -> list[tuple[str, dict]]`
- `add_user(scenario, key, **fields) -> dict`
- `remove_user(scenario, key) -> dict`
- `list_resources(scenario) -> list[tuple[str, dict]]`
- `add_resource(scenario, name, **fields) -> dict`
- `remove_resource(scenario, name) -> dict`
- `get_config_section(scenario, field) -> Any`
- `set_config_section(scenario, **fields) -> dict`

**Important:** all are **pure functions** — take dict, return new dict, no I/O. CLI layer does load → apply → validate → save.

- [ ] **Step 1: 加失败的测试**

追加到 `tests/test_prism_core.py`:
```python
def _make_scenario():
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    return core.render(core.load_config(None, events))


def test_set_meta_roundtrip():
    sc = _make_scenario()
    sc2 = core.set_meta(sc, name="New name", description="New desc")
    assert sc2["meta"]["name"] == "New name"
    assert sc2["meta"]["description"] == "New desc"


def test_user_add_remove_roundtrip():
    sc = _make_scenario()
    sc = core.add_user(sc, "ops", url="https://x", username="ops", password="p")
    assert "ops" in sc["config"]["users"]
    users = core.list_users(sc)
    assert any(k == "ops" for k, _ in users)
    sc = core.remove_user(sc, "ops")
    assert "ops" not in sc["config"]["users"]


def test_remove_user_raises_for_missing():
    sc = _make_scenario()
    with pytest.raises(KeyError):
        core.remove_user(sc, "ghost")


def test_resource_add_remove_roundtrip():
    sc = _make_scenario()
    sc = core.add_resource(sc, "redis", kind="mock", image="redis:7",
                           port_mapping={"6379": 6379})
    assert "redis" in sc["resource"]
    resources = core.list_resources(sc)
    assert any(n == "redis" for n, _ in resources)
    sc = core.remove_resource(sc, "redis")
    assert "redis" not in sc["resource"]


def test_config_get_set_section():
    sc = _make_scenario()
    tp = core.get_config_section(sc, "timePolicy")
    assert tp is not None
    sc = core.set_config_section(sc, timePolicyKind="timeout", timePolicySeconds=120)
    tp = core.get_config_section(sc, "timePolicy")
    assert tp["kind"] == "timeout"
    assert tp["seconds"] == 120
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_prism_core.py::test_set_meta_roundtrip -v`
Expected: FAIL.

- [ ] **Step 3: 实现所有 section edit primitives**

追加到 `gimbal/prism/core.py`:
```python
def _deep_copy(d: dict[str, Any]) -> dict[str, Any]:
    import copy
    return copy.deepcopy(d)


def get_meta(scenario: dict[str, Any]) -> dict[str, Any]:
    return dict(scenario.get("meta") or {})


def set_meta(scenario: dict[str, Any], **fields: Any) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    sc.setdefault("meta", {}).update(fields)
    validate_scenario(sc)
    return sc


def list_users(scenario: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    users = (scenario.get("config") or {}).get("users") or {}
    return [(k, dict(v)) for k, v in users.items()]


def add_user(
    scenario: dict[str, Any], key: str, **fields: Any,
) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    sc.setdefault("config", {}).setdefault("users", {})[key] = fields
    validate_scenario(sc)
    return sc


def remove_user(scenario: dict[str, Any], key: str) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    users = sc.setdefault("config", {}).setdefault("users", {})
    if key not in users:
        raise KeyError(f"user not found: {key}")
    del users[key]
    validate_scenario(sc)
    return sc


def list_resources(scenario: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    res = scenario.get("resource") or {}
    return [(k, dict(v)) for k, v in res.items()]


def add_resource(
    scenario: dict[str, Any], name: str, **fields: Any,
) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    sc.setdefault("resource", {})[name] = fields
    validate_scenario(sc)
    return sc


def remove_resource(scenario: dict[str, Any], name: str) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    res = sc.setdefault("resource", {})
    if name not in res:
        raise KeyError(f"resource not found: {name}")
    del res[name]
    validate_scenario(sc)
    return sc


def get_config_section(scenario: dict[str, Any], field: str) -> Any:
    return (scenario.get("config") or {}).get(field)


# set_config_section 的字段名以 Pydantic Config 字段为准 (camelCase)
def set_config_section(scenario: dict[str, Any], **fields: Any) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    sc.setdefault("config", {}).update(fields)
    validate_scenario(sc)
    return sc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_core.py -v`
Expected: PASS (22 cases).

- [ ] **Step 5: Commit**

```bash
git add gimbal/prism/core.py tests/test_prism_core.py
git commit -m "feat(prism-core): add section edit primitives (meta/users/resources/config)"
```

---

## Task 8: parity canary test

**Files:**
- Create: `tests/test_prism_core_builder_parity.py`

**Interfaces:** the canary asserts byte-identical output between web and CLI for given NDJSON + config.

- [ ] **Step 1: 写 parity canary**

`tests/test_prism_core_builder_parity.py`:
```python
"""Parity canary: web (_draft_from_in + build_scenario) and CLI (core) must
produce identical scenario dicts for the same inputs.

Fails CI on any drift between gimbal.prism.core and gimbal.prism.builder.
"""
from __future__ import annotations

from pathlib import Path

from gimbal.prism.builder import (
    ResourceDraft,
    ScenarioDraft,
    StepDraft,
    build_scenario,
)
from gimbal.prism.server import DraftIn  # 用 web 端 DraftIn wire form
from gimbal.prism import core

FIXTURES = Path(__file__).parent / "fixtures"


def _events():
    return [
        {"host": "api.example.com", "method": "GET", "path": "/x",
         "headers": {}, "body": "", "response": {"status": 200}},
        {"host": "api.example.com", "method": "POST", "path": "/y",
         "headers": {}, "body": "{}", "response": {"status": 201}},
    ]


def test_parity_default_scenario():
    events = _events()
    cli_draft = core.load_config(None, events)
    cli_scenario = core.render(cli_draft)
    # web 路径: 直接构造 ScenarioDraft + build_scenario
    web_draft = ScenarioDraft(
        scenario_id=cli_draft.scenario_id,
        name=cli_draft.name,
        steps=[StepDraft(capture=e) for e in events],
    )
    web_scenario = build_scenario(web_draft).model_dump(mode="json")
    assert web_scenario == cli_scenario


def test_parity_with_config():
    events = _events()
    cli_draft = core.load_config(FIXTURES / "sample_config.yaml", events)
    cli_scenario = core.render(cli_draft)
    # web 路径: 直接构造 ScenarioDraft + build_scenario (与 load_config 同字段)
    web_scenario = build_scenario(cli_draft).model_dump(mode="json")
    assert web_scenario == cli_scenario
```

- [ ] **Step 2: 跑测试确认通过**

Run: `pytest tests/test_prism_core_builder_parity.py -v`
Expected: PASS (2 cases).

- [ ] **Step 3: Commit**

```bash
git add tests/test_prism_core_builder_parity.py
git commit -m "test(prism-core): add parity canary (web vs CLI byte-identical)"
```

---

## Task 9: migrate cli.py → cli/ subpackage

**Files:**
- Create: `gimbal/prism/cli/__init__.py`
- Create: `gimbal/prism/cli/start.py` (content from old `gimbal/prism/cli.py`)
- Delete: `gimbal/prism/cli.py`

**Interfaces:**
- `gimbal/prism/cli/__init__.py` re-exports `start_cmd` from `start` for backward compat: `from gimbal.prism.cli import start_cmd` still works.

- [ ] **Step 1: 创建 `cli/start.py` (复制旧 `cli.py` 内容)**

`gimbal/prism/cli/start.py`:
```python
"""gimbal prism 子命令实现 — start (web server launcher).

Moved from gimbal/prism/cli.py to make room for the new cli/ subpackage
(start, convert, inspect, validate, to_steps, explain, meta, user,
resource, config). The old single-file module is removed in Task 9.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from gimbal.prism.server import app as fastapi_app


def start_cmd(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
    home: Optional[Path] = typer.Option(None, "--home"),
    workers: int = typer.Option(1, "--workers", "-w", help="uvicorn workers, v0 仅支持 1"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
) -> None:
    """启动 prism 配置器 web UI。"""
    if workers != 1:
        typer.secho("[prism] v0 仅支持 --workers 1, 已强制设 1", fg=typer.colors.YELLOW)
        workers = 1

    if home is not None:
        os.environ["GIMBAL_HOME"] = str(home.expanduser())
    home_path = Path(os.environ.get("GIMBAL_HOME", "~/.gimbal")).expanduser()
    if not home_path.exists():
        typer.secho(f"[prism] 警告: {home_path} 不存在, 自动创建", fg=typer.colors.YELLOW)
        home_path.mkdir(parents=True, exist_ok=True)

    typer.echo(f"[prism] GIMBAL_HOME={home_path}")
    typer.echo(f"[prism] starting on http://{host}:{port}")

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level="info",
    )
```

- [ ] **Step 2: 创建 `cli/__init__.py`**

`gimbal/prism/cli/__init__.py`:
```python
"""gimbal.prism.cli — Typer subcommands for `gimbal prism`.

v0.6+ adds: convert, inspect, validate, to_steps, explain, meta, user,
resource, config. The legacy `start` command (web server launcher) is
re-exported here for backward compatibility with code that did
`from gimbal.prism.cli import start_cmd`.
"""
from __future__ import annotations

import typer

from .start import start_cmd

# 各子命令的 cmd 函数在 Task 10+ 由对应模块注册到 prism_app。
# 现阶段只注册 start。
prism_app = typer.Typer(help="gimbal prism CLI 子命令", no_args_is_help=True)
prism_app.command("start")(start_cmd)

__all__ = ["prism_app", "start_cmd"]
```

- [ ] **Step 3: 更新 `gimbal/cli/prism.py` 导入路径**

修改 `gimbal/cli/prism.py`:
```python
"""gimbal prism 子命令组注册。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from gimbal.prism.cli import prism_app


@prism_app.command("start")
def start(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
    home: Optional[Path] = typer.Option(None, "--home"),
    workers: int = typer.Option(1, "--workers", "-w", help="uvicorn workers, v0 仅支持 1"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
):
    """启动 prism 配置器 web UI。"""
    from gimbal.prism.cli.start import start_cmd
    start_cmd(host, port, home, workers, reload)
```

注：上面的 `from gimbal.prism.cli.start import start_cmd` 与 `@prism_app.command("start")` 在同一文件, 避免循环 import。**实际 import 改用 `from gimbal.prism.cli import prism_app`**（不是 `from gimbal.prism.cli import start_cmd`）。

- [ ] **Step 4: 删除旧 `gimbal/prism/cli.py`**

Run: `rm gimbal/prism/cli.py`
(Bash: `git rm gimbal/prism/cli.py` if tracked, else just delete.)

- [ ] **Step 5: 跑现有测试确认无回归**

Run: `pytest tests/test_prism_server.py tests/test_cli_integration.py -v`
Expected: PASS (无回归 — web prism 仍工作, start 命令仍可用).

- [ ] **Step 6: 手动 smoke: `gimbal prism --help`**

Run: `gimbal prism --help`
Expected: 列出 `start` 子命令 (其他子命令尚未注册).

- [ ] **Step 7: Commit**

```bash
git add gimbal/prism/cli/__init__.py gimbal/prism/cli/start.py gimbal/cli/prism.py
git rm gimbal/prism/cli.py
git commit -m "refactor(prism-cli): migrate cli.py to cli/ subpackage (start only)"
```

---

## Task 10: cli/_shared.py (shared helpers)

**Files:**
- Create: `gimbal/prism/cli/_shared.py`

**Interfaces:**
- `load_yaml(path) -> dict` — convenience wrapper.
- `save_yaml(data, path) -> None` — convenience wrapper.
- `print_error(msg, exit_code) -> NoReturn` — print to stderr + sys.exit.
- `resolve_home(home: Path | None) -> Path` — resolve `$GIMBAL_HOME` or default.

- [ ] **Step 1: 实现 `_shared.py`**

`gimbal/prism/cli/_shared.py`:
```python
"""gimbal.prism.cli._shared — shared utilities for CLI subcommands."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, NoReturn

import yaml


def resolve_home(home: Path | None = None) -> Path:
    """Resolve $GIMBAL_HOME; default ~/.gimbal. Create if missing."""
    if home is not None:
        h = home.expanduser()
    else:
        h = Path(os.environ.get("GIMBAL_HOME", "~/.gimbal")).expanduser()
    h.mkdir(parents=True, exist_ok=True)
    return h


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        print_error(f"file not found: {path}", 2)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_yaml(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def print_error(msg: str, exit_code: int) -> NoReturn:
    """Print error to stderr and exit."""
    typer = None  # type: ignore[assignment]
    import typer as _typer  # noqa: PLC0415
    _typer.secho(msg, fg=_typer.colors.RED, err=True)
    raise SystemExit(exit_code)
```

- [ ] **Step 2: 手动 smoke (暂未接入)**

(无测试, 留给后续子命令接入.)

- [ ] **Step 3: Commit**

```bash
git add gimbal/prism/cli/_shared.py
git commit -m "feat(prism-cli): add _shared.py with home/yaml/error helpers"
```

---

## Task 11: convert subcommand

**Files:**
- Create: `gimbal/prism/cli/convert.py`
- Create: `tests/test_prism_cli_convert.py`
- Modify: `gimbal/prism/cli/__init__.py` (register command)

**Interfaces:**
- `gimbal prism convert --input <ndjson> [--config <yaml>] [--output <yaml>] [--home] [--quiet]`

- [ ] **Step 1: 实现 `convert_cmd`**

`gimbal/prism/cli/convert.py`:
```python
"""gimbal prism convert — NDJSON (+ config) → Scenario YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error, resolve_home


def convert_cmd(
    input: Path = typer.Option(..., "--input", "-i", help="NDJSON 文件"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="场景配置 YAML"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出 YAML 路径 (缺省 stdout)"),
    home: Optional[Path] = typer.Option(None, "--home"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """NDJSON + 可选 config → Scenario YAML。"""
    resolve_home(home)  # ensure dir exists, even if unused
    try:
        result = core.convert_ndjson_to_scenario(input, config, output)
    except FileNotFoundError as e:
        print_error(f"input not found: {e}", 2)
    except ValueError as e:
        print_error(f"ndjson error: {e}", 3)
    except Exception as e:  # noqa: BLE001
        if not quiet:
            raise
        print_error(f"internal error: {e}", 5)

    if not quiet:
        typer.echo(
            f"[prism convert] events={result.event_count} "
            f"steps={result.step_count} "
            f"output={result.output_path or '<stdout>'}",
            err=True,
        )

    if output is None:
        typer.echo(result.yaml_text)
```

- [ ] **Step 2: 注册到 cli app**

修改 `gimbal/prism/cli/__init__.py`，追加:
```python
from .convert import convert_cmd

prism_app.command("convert")(convert_cmd)
```

- [ ] **Step 3: 写 CLI 测试**

`tests/test_prism_cli_convert.py`:
```python
"""CLI integration tests for `gimbal prism convert`."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner(mix_stderr=False)


def test_convert_basic_to_stdout():
    result = runner.invoke(
        prism_app, ["convert", "-i", str(FIXTURES / "minimal_captures.ndjson")],
    )
    assert result.exit_code == 0
    assert "scenarioId:" in result.stdout


def test_convert_with_config_to_file(tmp_path):
    out = tmp_path / "out.yaml"
    result = runner.invoke(prism_app, [
        "convert",
        "-i", str(FIXTURES / "minimal_captures.ndjson"),
        "-c", str(FIXTURES / "sample_config.yaml"),
        "-o", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    assert "scenarioId: sc_sample" in out.read_text(encoding="utf-8")


def test_convert_exit_code_2_missing_input(tmp_path):
    result = runner.invoke(prism_app, ["convert", "-i", str(tmp_path / "nope.ndjson")])
    assert result.exit_code == 2


def test_convert_exit_code_3_empty_ndjson(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.write_text("")
    result = runner.invoke(prism_app, ["convert", "-i", str(p)])
    assert result.exit_code == 3
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_convert.py -v`
Expected: PASS (4 cases).

- [ ] **Step 5: Commit**

```bash
git add gimbal/prism/cli/convert.py gimbal/prism/cli/__init__.py tests/test_prism_cli_convert.py
git commit -m "feat(prism-cli): add `convert` subcommand (full pipeline)"
```

---

## Task 12: inspect subcommand

**Files:**
- Create: `gimbal/prism/cli/inspect.py`
- Create: `tests/test_prism_cli_inspect.py`
- Modify: `gimbal/prism/cli/__init__.py`

**Interfaces:**
- `gimbal prism inspect --input <ndjson> [--limit N] [--json]`

- [ ] **Step 1: 实现 `inspect_cmd`**

`gimbal/prism/cli/inspect.py`:
```python
"""gimbal prism inspect — NDJSON 统计 + 前 N 条样本。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def inspect_cmd(
    input: Path = typer.Option(..., "--input", "-i", help="NDJSON 文件"),
    limit: int = typer.Option(3, "--limit", help="sample 事件数"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出 (缺省人读友好)"),
) -> None:
    """读取 NDJSON 输出统计 + 前 N 条样本。"""
    try:
        stats = core.inspect_ndjson(input, sample_limit=limit)
    except FileNotFoundError as e:
        print_error(f"input not found: {e}", 2)
    except ValueError as e:
        print_error(f"ndjson error: {e}", 3)

    if as_json:
        typer.echo(json.dumps({
            "event_count": stats.event_count,
            "method_counts": stats.method_counts,
            "host_counts": stats.host_counts,
            "status_counts": stats.status_counts,
            "sample_events": stats.sample_events,
        }, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"events: {stats.event_count}")
        typer.echo(f"methods: {stats.method_counts}")
        typer.echo(f"hosts: {stats.host_counts}")
        typer.echo(f"statuses: {stats.status_counts}")
        typer.echo(f"sample (first {len(stats.sample_events)}):")
        for ev in stats.sample_events:
            typer.echo(f"  {ev.get('method'):6} {ev.get('path'):30} -> {ev.get('response',{}).get('status')}")
```

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .inspect import inspect_cmd
prism_app.command("inspect")(inspect_cmd)
```

`tests/test_prism_cli_inspect.py`:
```python
"""CLI integration tests for `gimbal prism inspect`."""
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_inspect_text_output():
    result = runner.invoke(prism_app, ["inspect", "-i", str(FIXTURES / "sample_captures.ndjson")])
    assert result.exit_code == 0
    assert "events: 3" in result.stdout
    assert "POST" in result.stdout
    assert "GET" in result.stdout


def test_inspect_json_output():
    result = runner.invoke(prism_app, ["inspect", "-i", str(FIXTURES / "sample_captures.ndjson"), "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert data["event_count"] == 3
    assert data["method_counts"]["POST"] == 1


def test_inspect_exit_code_2_missing(tmp_path):
    result = runner.invoke(prism_app, ["inspect", "-i", str(tmp_path / "nope.ndjson")])
    assert result.exit_code == 2
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_inspect.py -v`
Expected: PASS (3 cases).

- [ ] **Step 4: Commit**

```bash
git add gimbal/prism/cli/inspect.py gimbal/prism/cli/__init__.py tests/test_prism_cli_inspect.py
git commit -m "feat(prism-cli): add `inspect` subcommand"
```

---

## Task 13: validate subcommand

**Files:**
- Create: `gimbal/prism/cli/validate.py`
- Create: `tests/test_prism_cli_validate.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 实现 `validate_cmd`**

`gimbal/prism/cli/validate.py`:
```python
"""gimbal prism validate — config YAML 校验。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def validate_cmd(
    config: Path = typer.Option(..., "--config", "-c", help="场景配置 YAML"),
) -> None:
    """校验 config YAML 是否合法 (Pydantic schema)。"""
    if not config.exists():
        print_error(f"config not found: {config}", 2)
    errors = core.validate_config(config)
    if errors:
        for e in errors:
            typer.secho(f"  - {e}", fg=typer.colors.RED, err=True)
        raise SystemExit(4)
    typer.echo(f"[prism validate] OK: {config}", err=True)
```

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .validate import validate_cmd
prism_app.command("validate")(validate_cmd)
```

`tests/test_prism_cli_validate.py`:
```python
"""CLI integration tests for `gimbal prism validate`."""
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner(mix_stderr=False)


def test_validate_ok():
    result = runner.invoke(prism_app, ["validate", "-c", str(FIXTURES / "sample_config.yaml")])
    assert result.exit_code == 0
    assert "OK" in result.stderr


def test_validate_exit_code_4_invalid(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenario_id: x\nname: ''\n")
    result = runner.invoke(prism_app, ["validate", "-c", str(bad)])
    assert result.exit_code == 4


def test_validate_exit_code_2_missing(tmp_path):
    result = runner.invoke(prism_app, ["validate", "-c", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_validate.py -v`
Expected: PASS (3 cases).

- [ ] **Step 4: Commit**

```bash
git add gimbal/prism/cli/validate.py gimbal/prism/cli/__init__.py tests/test_prism_cli_validate.py
git commit -m "feat(prism-cli): add `validate` subcommand"
```

---

## Task 14: to-steps subcommand

**Files:**
- Create: `gimbal/prism/cli/to_steps.py`
- Create: `tests/test_prism_cli_to_steps.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 实现 `to_steps_cmd`**

`gimbal/prism/cli/to_steps.py`:
```python
"""gimbal prism to-steps — NDJSON → step fragment JSON (中间产物)。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import print_error


def to_steps_cmd(
    input: Path = typer.Option(..., "--input", "-i", help="NDJSON 文件"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="场景配置 YAML (用于 services 映射)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出 JSON 路径 (缺省 stdout)"),
) -> None:
    """NDJSON → step 片段 JSON (不组装 scenario)。"""
    try:
        frags = core.ndjson_to_step_fragments(input, config)
    except FileNotFoundError as e:
        print_error(f"input not found: {e}", 2)
    except ValueError as e:
        print_error(f"ndjson error: {e}", 3)

    text = json.dumps(frags, ensure_ascii=False, indent=2)
    if output is None:
        typer.echo(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        typer.echo(f"[prism to-steps] wrote {len(frags)} steps to {output}", err=True)
```

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .to_steps import to_steps_cmd
prism_app.command("to-steps")(to_steps_cmd)
```

`tests/test_prism_cli_to_steps.py`:
```python
"""CLI integration tests for `gimbal prism to-steps`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism.cli import prism_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner(mix_stderr=False)


def test_to_steps_to_stdout():
    result = runner.invoke(prism_app, ["to-steps", "-i", str(FIXTURES / "minimal_captures.ndjson")])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert "api" in data[0]


def test_to_steps_to_file(tmp_path):
    out = tmp_path / "steps.json"
    result = runner.invoke(prism_app, [
        "to-steps", "-i", str(FIXTURES / "minimal_captures.ndjson"), "-o", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 1


def test_to_steps_exit_code_2(tmp_path):
    result = runner.invoke(prism_app, ["to-steps", "-i", str(tmp_path / "nope.ndjson")])
    assert result.exit_code == 2
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_to_steps.py -v`
Expected: PASS (3 cases).

- [ ] **Step 4: Commit**

```bash
git add gimbal/prism/cli/to_steps.py gimbal/prism/cli/__init__.py tests/test_prism_cli_to_steps.py
git commit -m "feat(prism-cli): add `to-steps` subcommand"
```

---

## Task 15: explain subcommand

**Files:**
- Create: `gimbal/prism/cli/explain.py`
- Create: `tests/test_prism_cli_explain.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 实现 `explain_cmd`**

`gimbal/prism/cli/explain.py`:
```python
"""gimbal prism explain — scenario YAML 结构化摘要。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, print_error


def explain_cmd(
    scenario: Path = typer.Argument(..., help="scenario YAML 路径"),
    section: Optional[str] = typer.Option(None, "--section", help="仅输出某个 section (meta/config/steps/...)"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出"),
) -> None:
    """读 scenario YAML 输出结构化摘要。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    summary = core.explain_scenario(sc)
    if section:
        if section not in summary:
            print_error(f"unknown section: {section} (available: {list(summary.keys())})", 1)
        payload = summary[section]
    else:
        payload = summary

    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
```

注: 人读友好输出留给后续 task 调优；本期先统一 JSON 输出（可解析即 OK）。

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .explain import explain_cmd
prism_app.command("explain")(explain_cmd)
```

`tests/test_prism_cli_explain.py`:
```python
"""CLI integration tests for `gimbal prism explain`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner(mix_stderr=False)


def _make_scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    scenario = core.render(draft)
    p = tmp_path / "sc.yaml"
    core.save_scenario(scenario, p)
    return p


def test_explain_full(tmp_path):
    p = _make_scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["explain", str(p)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "meta" in data
    assert "steps_count" in data
    assert data["steps_count"] == 1


def test_explain_section(tmp_path):
    p = _make_scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["explain", str(p), "--section", "meta"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "scenarioId" in data or "name" in data


def test_explain_exit_code_2(tmp_path):
    result = runner.invoke(prism_app, ["explain", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_explain.py -v`
Expected: PASS (3 cases).

- [ ] **Step 4: Commit**

```bash
git add gimbal/prism/cli/explain.py gimbal/prism/cli/__init__.py tests/test_prism_cli_explain.py
git commit -m "feat(prism-cli): add `explain` subcommand"
```

---

## Task 16: edit/__init__.py + edit/meta subcommand

**Files:**
- Create: `gimbal/prism/cli/edit/__init__.py`
- Create: `gimbal/prism/cli/edit/meta.py`
- Create: `tests/test_prism_cli_meta.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 创建 `edit/__init__.py`**

`gimbal/prism/cli/edit/__init__.py`:
```python
"""gimbal.prism.cli.edit — section-grouped edit subcommands."""
```

- [ ] **Step 2: 实现 `meta` get/set**

`gimbal/prism/cli/edit/meta.py`:
```python
"""gimbal prism meta — get/set scenario meta fields."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

meta_app = typer.Typer(help="scenario meta 编辑")


@meta_app.command("get")
def meta_get(
    scenario: Path = typer.Argument(..., help="scenario YAML"),
    field: Optional[str] = typer.Option(None, "--field", "-f", help="仅输出某个字段"),
):
    """读 meta 字段。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    meta = core.get_meta(sc)
    if field:
        if field not in meta:
            print_error(f"field not found: {field}", 6)
        typer.echo(json.dumps({field: meta[field]}, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(json.dumps(meta, ensure_ascii=False, indent=2, default=str))


@meta_app.command("set")
def meta_set(
    scenario: Path = typer.Argument(..., help="scenario YAML"),
    name: Optional[str] = typer.Option(None, "--name"),
    description: Optional[str] = typer.Option(None, "--description"),
    module: Optional[str] = typer.Option(None, "--module"),
    priority: Optional[int] = typer.Option(None, "--priority"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """设 meta 字段 (at least one required)。"""
    fields = {
        k: v for k, v in {
            "name": name, "description": description,
            "module": module, "priority": priority,
        }.items() if v is not None
    }
    if not fields:
        print_error("at least one --field required", 1)
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    sc2 = core.set_meta(sc, **fields)
    if dry_run:
        typer.echo(json.dumps(sc2["meta"], ensure_ascii=False, indent=2, default=str))
    else:
        save_yaml(sc2, scenario)
        typer.echo(f"[prism meta set] updated: {list(fields.keys())}", err=True)
```

- [ ] **Step 3: 注册到 prism_app**

修改 `gimbal/prism/cli/__init__.py`，追加:
```python
from .edit.meta import meta_app

prism_app.add_typer(meta_app, name="meta")
```

- [ ] **Step 4: 写测试**

`tests/test_prism_cli_meta.py`:
```python
"""CLI integration tests for `gimbal prism meta`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner(mix_stderr=False)


def _scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    p = tmp_path / "sc.yaml"
    core.save_scenario(core.render(draft), p)
    return p


def test_meta_get(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["meta", "get", str(p)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "name" in data


def test_meta_get_field(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["meta", "get", str(p), "--field", "name"])
    assert result.exit_code == 0


def test_meta_set(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, [
        "meta", "set", str(p), "--name", "Renamed", "--description", "new desc",
    ])
    assert result.exit_code == 0
    sc = core.load_scenario(p)
    assert sc["meta"]["name"] == "Renamed"
    assert sc["meta"]["description"] == "new desc"


def test_meta_set_dry_run(tmp_path):
    p = _scenario_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    result = runner.invoke(prism_app, [
        "meta", "set", str(p), "--name", "DryRun", "--dry-run",
    ])
    assert result.exit_code == 0
    # 不写文件
    assert p.read_text(encoding="utf-8") == before


def test_meta_set_no_fields(tmp_path):
    p = _scenario_file(tmp_path)
    result = runner.invoke(prism_app, ["meta", "set", str(p)])
    assert result.exit_code == 1
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_meta.py -v`
Expected: PASS (5 cases).

- [ ] **Step 6: Commit**

```bash
git add gimbal/prism/cli/edit/ tests/test_prism_cli_meta.py gimbal/prism/cli/__init__.py
git commit -m "feat(prism-cli): add `meta` get/set subcommands"
```

---

## Task 17: edit/user subcommand

**Files:**
- Create: `gimbal/prism/cli/edit/user.py`
- Create: `tests/test_prism_cli_user.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 实现 `user` list/add/remove**

`gimbal/prism/cli/edit/user.py`:
```python
"""gimbal prism user — list/add/remove scenario users."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

user_app = typer.Typer(help="scenario users 编辑")


@user_app.command("list")
def user_list(scenario: Path = typer.Argument(...)):
    """列出所有 users。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    users = core.list_users(sc)
    typer.echo(json.dumps([{"key": k, **v} for k, v in users],
                          ensure_ascii=False, indent=2, default=str))


@user_app.command("add")
def user_add(
    scenario: Path = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
    url: str = typer.Option("", "--url"),
    username: str = typer.Option("", "--username"),
    password: str = typer.Option("", "--password"),
    expires_in: int = typer.Option(7200, "--expires-in"),
    token_type: str = typer.Option("Authorization", "--token-type"),
):
    """新增 user。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    sc = core.add_user(
        sc, key,
        url=url, username=username, password=password,
        expiresIn=expires_in, tokenType=token_type,
    )
    save_yaml(sc, scenario)
    typer.echo(f"[prism user add] added: {key}", err=True)


@user_app.command("remove")
def user_remove(
    scenario: Path = typer.Argument(...),
    key: str = typer.Option(..., "--key"),
):
    """删除 user。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    try:
        sc = core.remove_user(sc, key)
    except KeyError:
        print_error(f"user not found: {key}", 6)
    save_yaml(sc, scenario)
    typer.echo(f"[prism user remove] removed: {key}", err=True)
```

注：`add_user` 在 `core.py` 写 `config.users[key] = fields`，字段名是 Pydantic Config.users dict 元素所需的子字段 (`url`/`username`/`password`/`expiresIn`/`tokenType`/`token`)。此处传 camelCase。

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .edit.user import user_app
prism_app.add_typer(user_app, name="user")
```

`tests/test_prism_cli_user.py`:
```python
"""CLI integration tests for `gimbal prism user`."""
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner(mix_stderr=False)


def _scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    p = tmp_path / "sc.yaml"
    core.save_scenario(core.render(draft), p)
    return p


def test_user_add_and_list(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "user", "add", str(p), "--key", "admin",
        "--url", "https://x", "--username", "admin", "--password", "secret",
    ])
    assert r.exit_code == 0
    r = runner.invoke(prism_app, ["user", "list", str(p)])
    assert r.exit_code == 0
    assert "admin" in r.stdout


def test_user_remove(tmp_path):
    p = _scenario_file(tmp_path)
    runner.invoke(prism_app, [
        "user", "add", str(p), "--key", "ops", "--username", "ops",
    ])
    r = runner.invoke(prism_app, ["user", "remove", str(p), "--key", "ops"])
    assert r.exit_code == 0
    sc = core.load_scenario(p)
    assert "ops" not in sc["config"]["users"]


def test_user_remove_exit_code_6(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["user", "remove", str(p), "--key", "ghost"])
    assert r.exit_code == 6
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_user.py -v`
Expected: PASS (3 cases).

- [ ] **Step 4: Commit**

```bash
git add gimbal/prism/cli/edit/user.py gimbal/prism/cli/__init__.py tests/test_prism_cli_user.py
git commit -m "feat(prism-cli): add `user` list/add/remove subcommands"
```

---

## Task 18: edit/resource subcommand

**Files:**
- Create: `gimbal/prism/cli/edit/resource.py`
- Create: `tests/test_prism_cli_resource.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 实现 `resource` list/add/remove**

`gimbal/prism/cli/edit/resource.py`:
```python
"""gimbal prism resource — list/add/remove scenario resources."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

resource_app = typer.Typer(help="scenario resources 编辑")


@resource_app.command("list")
def resource_list(scenario: Path = typer.Argument(...)):
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    res = core.list_resources(sc)
    typer.echo(json.dumps([{"name": n, **v} for n, v in res],
                           ensure_ascii=False, indent=2, default=str))


@resource_app.command("add")
def resource_add(
    scenario: Path = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
    kind: str = typer.Option("mock", "--kind"),
    image: str = typer.Option("", "--image"),
    port: Optional[str] = typer.Option(None, "--port", help="host:container 形式"),
):
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    port_mapping: dict[str, int] = {}
    if port:
        h, c = port.split(":")
        port_mapping[h] = int(c)
    sc = load_yaml(scenario)
    fields: dict[str, Any] = {"kind": kind}
    if image:
        fields["image"] = image
    if port_mapping:
        fields["portMapping"] = {int(k): v for k, v in port_mapping.items()}
    sc = core.add_resource(sc, name, **fields)
    save_yaml(sc, scenario)
    typer.echo(f"[prism resource add] added: {name}", err=True)


@resource_app.command("remove")
def resource_remove(
    scenario: Path = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
):
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    try:
        sc = core.remove_resource(sc, name)
    except KeyError:
        print_error(f"resource not found: {name}", 6)
    save_yaml(sc, scenario)
    typer.echo(f"[prism resource remove] removed: {name}", err=True)
```

需在文件顶部加: `from typing import Any`.

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .edit.resource import resource_app
prism_app.add_typer(resource_app, name="resource")
```

`tests/test_prism_cli_resource.py`:
```python
"""CLI integration tests for `gimbal prism resource`."""
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner(mix_stderr=False)


def _scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    p = tmp_path / "sc.yaml"
    core.save_scenario(core.render(draft), p)
    return p


def test_resource_add_and_list(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "resource", "add", str(p),
        "--name", "redis", "--kind", "mock", "--image", "redis:7",
        "--port", "6379:6379",
    ])
    assert r.exit_code == 0
    r = runner.invoke(prism_app, ["resource", "list", str(p)])
    assert r.exit_code == 0
    assert "redis" in r.stdout


def test_resource_remove(tmp_path):
    p = _scenario_file(tmp_path)
    runner.invoke(prism_app, [
        "resource", "add", str(p), "--name", "redis", "--kind", "mock",
    ])
    r = runner.invoke(prism_app, ["resource", "remove", str(p), "--name", "redis"])
    assert r.exit_code == 0
    sc = core.load_scenario(p)
    assert "redis" not in sc.get("resource", {})


def test_resource_remove_exit_code_6(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["resource", "remove", str(p), "--name", "ghost"])
    assert r.exit_code == 6
```

- [ ] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_resource.py -v`
Expected: PASS (3 cases).

- [ ] **Step 4: Commit**

```bash
git add gimbal/prism/cli/edit/resource.py gimbal/prism/cli/__init__.py tests/test_prism_cli_resource.py
git commit -m "feat(prism-cli): add `resource` list/add/remove subcommands"
```

---

## Task 19: edit/config subcommand

**Files:**
- Create: `gimbal/prism/cli/edit/config.py`
- Create: `tests/test_prism_cli_config.py`
- Modify: `gimbal/prism/cli/__init__.py`

- [ ] **Step 1: 实现 `config` get/set**

`gimbal/prism/cli/edit/config.py`:
```python
"""gimbal prism config — get/set scenario config sections (timePolicy/retry/services/...)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from gimbal.prism import core
from gimbal.prism.cli._shared import load_yaml, save_yaml, print_error

config_app = typer.Typer(help="scenario config 编辑")


@config_app.command("get")
def config_get(
    scenario: Path = typer.Argument(...),
    field: str = typer.Option("timePolicy", "--field", "-f"),
):
    """读 config 某个 section。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    sc = load_yaml(scenario)
    val = core.get_config_section(sc, field)
    typer.echo(json.dumps(val, ensure_ascii=False, indent=2, default=str))


@config_app.command("set")
def config_set(
    scenario: Path = typer.Argument(...),
    time_policy_kind: Optional[str] = typer.Option(None, "--time-policy-kind"),
    time_policy_seconds: Optional[int] = typer.Option(None, "--time-policy-seconds"),
    retry_enabled: Optional[bool] = typer.Option(None, "--retry-enabled/--no-retry-enabled"),
    retry_max_attempts: Optional[int] = typer.Option(None, "--retry-max-attempts"),
    retry_backoff_seconds: Optional[float] = typer.Option(None, "--retry-backoff-seconds"),
):
    """设 config section 字段。"""
    if not scenario.exists():
        print_error(f"scenario not found: {scenario}", 2)
    fields: dict[str, Any] = {}
    if time_policy_kind is not None:
        fields["timePolicyKind"] = time_policy_kind
    if time_policy_seconds is not None:
        fields["timePolicySeconds"] = time_policy_seconds
    if retry_enabled is not None:
        fields["retryEnabled"] = retry_enabled
    if retry_max_attempts is not None:
        fields["retryMaxAttempts"] = retry_max_attempts
    if retry_backoff_seconds is not None:
        fields["retryBackoffSeconds"] = retry_backoff_seconds
    if not fields:
        print_error("at least one --field required", 1)
    sc = load_yaml(scenario)
    sc = core.set_config_section(sc, **fields)
    save_yaml(sc, scenario)
    typer.echo(f"[prism config set] updated: {list(fields.keys())}", err=True)
```

需在文件顶部加: `from typing import Any`.

注：`set_config_section` 的字段名以 Pydantic `Config` 字段为准 (camelCase): `timePolicyKind`, `timePolicySeconds`, `retryEnabled`, `retryMaxAttempts`, `retryBackoffSeconds`。当前 `core.set_config_section` 直接 set 字段；后续若 Pydantic Config 的字段是嵌套对象（timePolicy 是 {kind, seconds} dict），需在 `set_config_section` 里做内层嵌套 — 这是当前实现的**已知 gap**，留待 P0 时修。

- [ ] **Step 2: 注册 + 测试**

追加到 `gimbal/prism/cli/__init__.py`:
```python
from .edit.config import config_app
prism_app.add_typer(config_app, name="config")
```

`tests/test_prism_cli_config.py`:
```python
"""CLI integration tests for `gimbal prism config`."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gimbal.prism import core
from gimbal.prism.cli import prism_app

runner = CliRunner(mix_stderr=False)


def _scenario_file(tmp_path):
    events = [{"host": "api.example.com", "method": "GET", "path": "/x",
               "headers": {}, "body": "", "response": {"status": 200}}]
    draft = core.load_config(None, events)
    p = tmp_path / "sc.yaml"
    core.save_scenario(core.render(draft), p)
    return p


def test_config_get(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["config", "get", str(p), "--field", "timePolicy"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data is not None


def test_config_set_time_policy(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, [
        "config", "set", str(p),
        "--time-policy-kind", "timeout", "--time-policy-seconds", "120",
    ])
    assert r.exit_code == 0
    sc = core.load_scenario(p)
    assert sc["config"]["timePolicy"]["kind"] == "timeout"


def test_config_set_no_fields(tmp_path):
    p = _scenario_file(tmp_path)
    r = runner.invoke(prism_app, ["config", "set", str(p)])
    assert r.exit_code == 1
```

注: 上面 `test_config_set_time_policy` 假设 Task 7 后续会修 `set_config_section` 处理嵌套结构 (把 timePolicyKind/timePolicySeconds 合并为 timePolicy: {kind, seconds})。如果在 Task 19 之前 core 已修，测试直接过；否则在 Task 19 之前需要先 patch `core.set_config_section` 让嵌套正确。详见 Task 19 末的"已知 gap 备注"。

- [ ] **Step 3: 若测试失败, 先 patch `core.set_config_section` 处理嵌套**

打开 `gimbal/prism/core.py`, 修改 `set_config_section`:
```python
def set_config_section(scenario: dict[str, Any], **fields: Any) -> dict[str, Any]:
    sc = _deep_copy(scenario)
    cfg = sc.setdefault("config", {})
    # 处理嵌套: timePolicyKind + timePolicySeconds → cfg["timePolicy"] = {kind, seconds}
    if "timePolicyKind" in fields or "timePolicySeconds" in fields:
        tp = cfg.setdefault("timePolicy", {})
        if "timePolicyKind" in fields:
            tp["kind"] = fields.pop("timePolicyKind")
        if "timePolicySeconds" in fields:
            tp["seconds"] = fields.pop("timePolicySeconds")
    # 处理嵌套: retryEnabled/MaxAttempts/BackoffSeconds → cfg["retry"] = {...}
    retry_keys = {"retryEnabled", "retryMaxAttempts", "retryBackoffSeconds", "retryOn"}
    if any(k in fields for k in retry_keys):
        rt = cfg.setdefault("retry", {})
        if "retryEnabled" in fields:
            rt["enabled"] = fields.pop("retryEnabled")
        if "retryMaxAttempts" in fields:
            rt["maxAttempts"] = fields.pop("retryMaxAttempts")
        if "retryBackoffSeconds" in fields:
            rt["backoffSeconds"] = fields.pop("retryBackoffSeconds")
    cfg.update(fields)
    validate_scenario(sc)
    return sc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_prism_cli_config.py -v`
Expected: PASS (3 cases).

- [ ] **Step 5: 跑全部 core 测试确认未回归**

Run: `pytest tests/test_prism_core.py tests/test_prism_core_builder_parity.py -v`
Expected: PASS (无回归)。

- [ ] **Step 6: Commit**

```bash
git add gimbal/prism/cli/edit/config.py gimbal/prism/cli/__init__.py tests/test_prism_cli_config.py gimbal/prism/core.py
git commit -m "feat(prism-cli): add `config` get/set subcommands + nested field handling"
```

---

## Task 20: docs - README / USER_MANUAL / CHANGELOG

**Files:**
- Modify: `README.md` (子命令表)
- Modify: `USER_MANUAL.md` (新增 §X)
- Modify: `CHANGELOG.md` (v0.6.0 条目)

- [ ] **Step 1: 更新 README 子命令表**

打开 `README.md`, 替换"## 子命令"节:
```markdown
## 子命令

| 命令 | 作用 |
|---|---|
| `gimbal capture start` | 启动 mitmproxy 抓包 |
| `gimbal capture list` | 列出 active 下的 session |
| `gimbal capture show <sid>` | 查看某 session 的事件 |
| `gimbal capture archive <sid>` | 手动归档 |
| `gimbal prism start` | 启动 web 配置器 (默认 :8765) |
| `gimbal prism convert` | NDJSON (+ config) → Scenario YAML |
| `gimbal prism inspect` | NDJSON 统计 + 前 N 条样本 |
| `gimbal prism validate` | config YAML 校验 |
| `gimbal prism to-steps` | NDJSON → step 片段 JSON |
| `gimbal prism explain <sc>` | scenario YAML 结构摘要 |
| `gimbal prism meta get/set` | 读 / 改 scenario meta 字段 |
| `gimbal prism user list/add/remove` | 读 / 改 scenario users |
| `gimbal prism resource list/add/remove` | 读 / 改 scenario resources |
| `gimbal prism config get/set` | 读 / 改 scenario config sections |
```

- [ ] **Step 2: USER_MANUAL 新增 §X "Headless CLI"**

打开 `USER_MANUAL.md`, 在文件末尾追加:
```markdown
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
```

- [ ] **Step 3: CHANGELOG 加 v0.6.0 条目**

打开 `CHANGELOG.md`, 在顶部 (最新) 追加:
```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add README.md USER_MANUAL.md CHANGELOG.md
git commit -m "docs: document v0.6 headless CLI (9 subcommands + config schema)"
```

---

## Task 21: final integration + full test run

**Files:** (no file changes; verification only)

- [ ] **Step 1: 跑全部新增 core + CLI 测试**

Run: `pytest tests/test_prism_core.py tests/test_prism_core_builder_parity.py tests/test_prism_cli_*.py -v`
Expected: PASS (~50+ cases).

- [ ] **Step 2: 跑全部现有测试, 确认 237 passed / 4 skipped 仍绿**

Run: `pytest tests/ -v`
Expected: 全部通过 (现有基线 + 50+ 新增)。

- [ ] **Step 3: 手动 smoke: 9 个子命令都能 help**

Run:
```bash
gimbal prism --help
gimbal prism convert --help
gimbal prism inspect --help
gimbal prism validate --help
gimbal prism to-steps --help
gimbal prism explain --help
gimbal prism meta --help
gimbal prism user --help
gimbal prism resource --help
gimbal prism config --help
gimbal prism start --help
```
Expected: 11 个 help 都正常打印。

- [ ] **Step 4: 手动 smoke: end-to-end CLI 工作流**

Run:
```bash
# 1. 准备 fixtures
mkdir -p /tmp/prism-smoke
cp tests/fixtures/sample_captures.ndjson /tmp/prism-smoke/
cp tests/fixtures/sample_config.yaml /tmp/prism-smoke/

# 2. inspect
gimbal prism inspect -i /tmp/prism-smoke/sample_captures.ndjson

# 3. validate
gimbal prism validate -c /tmp/prism-smoke/sample_config.yaml

# 4. convert
gimbal prism convert \
  -i /tmp/prism-smoke/sample_captures.ndjson \
  -c /tmp/prism-smoke/sample_config.yaml \
  -o /tmp/prism-smoke/out.yaml

# 5. explain
gimbal prism explain /tmp/prism-smoke/out.yaml

# 6. edit: 加 user
gimbal prism user add /tmp/prism-smoke/out.yaml \
  --key ops --username ops --password x

# 7. explain again
gimbal prism explain /tmp/prism-smoke/out.yaml --section config

# 8. web prism 仍工作
gimbal prism start --port 18765 &  # background
sleep 2
curl -s http://127.0.0.1:18765/api/health
kill %1
```
Expected: 全部 8 步都成功, 第 8 步的 curl 返回 `{"status":"ok",...}`.

- [ ] **Step 5: ruff 检查**

Run: `ruff check gimbal/`
Expected: 无报错 (已遵守现有代码风格)。

- [ ] **Step 6: 提交最终结果**

```bash
git status
# 应只有上面已经 commit 过的文件, 没有未提交修改
git log --oneline -25
# 应看到 v0.6 一系列 feat/docs/refactor/test commit
```

---

## Self-Review Checklist (run before handoff)

After completing all 21 tasks, verify:

- [ ] **Spec coverage**: spec §1-§8 sections all have a corresponding task. Section 6 (Future Work) is documented but not implemented.
- [ ] **No placeholders**: scan plan for "TBD", "TODO", "implement later", "fill in details" — none should remain.
- [ ] **Type consistency**: `core.py` function signatures match across Tasks 1-7. CLI flags match core parameters across Tasks 11-19.
- [ ] **Test count**: ~14 core unit tests + 2 parity + 9 CLI files × ~3-5 cases = ~50+ new test cases, all passing.
- [ ] **No regression**: existing 237 tests still pass (web prism untouched).
- [ ] **Doc parity**: README / USER_MANUAL / CHANGELOG all updated to reflect 9 new subcommands.
- [ ] **Branch**: all commits on `feature/prism-cli` (not main).

## Execution Handoff

After Task 21 passes, the plan is complete. The user can choose:

1. **Merge to main**: `git checkout main && git merge --no-ff feature/prism-cli`
2. **Open PR**: `gh pr create --base main --head feature/prism-cli --title "feat: v0.6 headless prism-cli (9 subcommands + core)" --body "..."`
3. **Keep working on branch**: defer merge to next session
