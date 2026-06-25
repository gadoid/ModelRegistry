# prism & prism-cli — Headless CLI for NDJSON → Scenario YAML

| Field | Value |
|---|---|
| Date | 2026-06-24 |
| Status | Draft |
| Phase | v0.6 (proposed) |
| Author | brainstorming session |
| Spec owner | TBD |

## 1. Background

The `gimbal prism` module currently has only one entry point: a web configurator
(`gimbal prism start`) that reads NDJSON captures from
`$GIMBAL_HOME/captures/active/{sid}.ndjson`, lets a human edit the scenario
through a 4-tab UI, and exports the result as YAML.

This works well for interactive use but blocks several use cases:

1. **CI / automation**: no headless way to convert an NDJSON capture to a
   complete, runnable Scenario YAML without launching the web server.
2. **Inspection / debugging**: no quick way to peek into an NDJSON file's
   contents without opening a JSON viewer.
3. **Pre-flight validation**: no way to check if a scenario config YAML is
   valid before running a long conversion.
4. **Incremental editing**: web UI is the only way to modify a scenario's
   meta / users / resources / config fields; shell scripting around these
   tasks is impossible.

This spec introduces **7 new CLI subcommands** under `gimbal prism`, all
backed by a new shared `gimbal.prism.core` module that reuses the existing
`gimbal.prism.builder.build_scenario()` logic:

- 5 pipeline subcommands (`convert`, `inspect`, `validate`, `to-steps`,
  `explain`)
- 4 edit subcommand groups (`meta`, `user`, `resource`, `config`)

The web configurator is **not changed** in this PR. A future migration is
documented in §6.

## 2. Goals & Non-goals

### Goals

1. **G1 — Headless conversion**: `gimbal prism convert` takes an NDJSON file and
   optional config YAML, produces a complete Scenario YAML that the future
   `gimbal run` executor can consume.
2. **G2 — Granular pipeline**: each stage of the conversion (parse / validate
   / render / write) is exposed as its own subcommand for debugging and
   scripted workflows.
3. **G3 — Incremental editing**: meta / user / resource / config sections
   of an existing scenario YAML can be read and modified via CLI
   subcommands, supporting shell-scripted scenario composition.
4. **G4 — Full parity with web output**: given the same NDJSON + same scenario
   config, web and CLI produce byte-identical YAML.
5. **G5 — Pipe-friendly**: output goes to stdout by default; can be redirected
   to a file. Logs and errors go to stderr.
6. **G6 — Predictable exit codes**: 0 success, 1-6 distinct error classes
   (see §5.3).
7. **G7 — Parity canary test**: any drift between `core.py` and `builder.py`
   fails CI immediately.

### Non-goals (this PR)

- N1 — Migrating the web configurator to use `core.py` (deferred, see §6.1).
- N2 — Step-level edit subcommands (steps come from NDJSON; see §6.2).
- N3 — Parameterized template × data-row expansion (the "data-driven" feature
  in `gimbal-step-import-future-scope.md`). This PR is **capture-driven**, not
  parameterized. See §6.3.
- N4 — Round-tripping CLI edits back into web sessions.
- N3 — Round-tripping back into web sessions (CLI is one-shot).
- N4 — Replacing `gimbal/prism/convert.py` (the existing pure-function
  `convert_record()` / `convert_file()` stay; `core.py` calls them).

## 3. Vocabulary

- **Capture event**: one line of NDJSON, JSON object with keys
  `host`, `method`, `path`, `headers`, `query`, `body`, `response.status`.
- **NDJSON file**: N capture events = one business scenario.
- **Step**: one capture event after prism processing (status assertion,
  auth header substitution, etc.).
- **Scenario config**: YAML file with `meta`, `services`, `users`,
  `time_policy`, `retry`, `setup_refs`, `teardown_refs`, `resources` — the
  same fields the web UI edits.
- **Scenario YAML**: the final output — `gimbal.schema.Scenario`-validated
  YAML, ready for execution.

## 4. Module Layout

```
gimbal/prism/
├── __init__.py
├── convert.py          # 现有: NDJSON record → step fragment (纯函数, IO-free)
├── builder.py          # 现有: ScenarioDraft → Scenario (pydantic 校验)
├── server.py           # 现有: web (FastAPI) — 不动
├── state.py            # 现有: Session/CaptureReader/Watcher — 不动
├── render/             # 现有: schema → UI spec — 不动
├── static/             # 现有: web 前端 — 不动
│
├── core.py             # ← NEW: shared functions used by CLI
│                        #   - parse_ndjson / load_config / render / write
│                        #   - load_scenario / save_scenario / apply_edit
│                        #     (for incremental edit subcommands)
│
└── cli/                # ← NEW: CLI subpackage, replaces gimbal/prism/cli.py
    ├── __init__.py     #   - 注册所有子命令到 prism_app
    ├── _shared.py      #   - 共享工具 (load_yaml / save_yaml / exit codes)
    ├── convert.py      #   - convert_cmd (full pipeline)
    ├── inspect.py      #   - inspect_cmd (NDJSON 统计)
    ├── validate.py     #   - validate_cmd (config 校验)
    ├── to_steps.py     #   - to_steps_cmd (NDJSON → step fragments)
    ├── explain.py      #   - explain_cmd (scenario 结构摘要)
    └── edit/           #   - 增量修改子命令 (按 section 分组)
        ├── __init__.py
        ├── meta.py     #   - meta get/set
        ├── user.py     #   - user add/list/remove
        ├── resource.py #   - resource add/list/remove
        └── config.py   #   - config get/set (time_policy / retry / services)

gimbal/cli/prism.py     # 现有: prism subcommand group
                         # ← ADD `convert` + 其他子命令
```

**Why a `cli/` subpackage, not one big file:**

7+ subcommands with different arg signatures, organized by section for the
edit commands. A single file would grow to 1000+ LOC. The subpackage mirrors
the section structure and makes adding future commands (e.g., `step edit`)
mechanical.

**Touched files:**

| File | Change |
|---|---|
| `gimbal/prism/core.py` | NEW — pipeline + edit primitives |
| `gimbal/prism/cli/` | NEW subpackage (replaces old `gimbal/prism/cli.py`) |
| `gimbal/cli/prism.py` | Register all subcommands on prism_app |
| `tests/test_prism_core.py` | NEW — unit tests for core |
| `tests/test_prism_core_builder_parity.py` | NEW — parity canary |
| `tests/test_prism_cli_*.py` | NEW — one test file per subcommand |
| `tests/fixtures/sample_*.yaml/.ndjson` | NEW — sample inputs |

**Untouched:**

- `gimbal/prism/server.py` (web API surface unchanged)
- `gimbal/prism/builder.py` (`core.py` calls it)
- `gimbal/prism/convert.py` (`core.py` calls it)
- `gimbal/prism/state.py`, `render/`, `static/`
- Existing 237 tests must remain green.

**Backward compatibility note:** `gimbal/prism/cli.py` (the old single
file containing `start_cmd`) is **moved** into `gimbal/prism/cli/start.py`
inside the new subpackage, or kept as a re-export shim. `gimbal.cli.prism`
imports the `prism_app` symbol — that symbol's location changes from
`gimbal.prism.cli` to `gimbal.prism.cli` (now a package). External imports
like `from gimbal.prism.cli import start_cmd` keep working via re-export
in `gimbal/prism/cli/__init__.py`.

## 5. Detailed Design

### 5.1 `gimbal/prism/core.py`

**Public API** — two groups of functions:

#### Group A: Pipeline functions (NDJSON → Scenario)

```python
@dataclass
class ConvertResult:
    scenario: dict[str, Any]            # 渲染后的 scenario (Pydantic-validated)
    output_path: Path | None            # 写到了哪里; None = 没写文件, 走 stdout
    yaml_text: str                      # 序列化好的 YAML (for stdout)
    warnings: list[str]                 # e.g. "step 3 has no response status"
    event_count: int
    step_count: int


def convert_ndjson_to_scenario(
    ndjson_path: Path,
    config_path: Path | None,
    output_path: Path | None = None,
) -> ConvertResult:
    """NDJSON + optional config YAML → Scenario YAML.

    Pure-ish: reads files, writes 0 or 1 file. No web/CLI dependencies.
    Validates final output against gimbal.schema.Scenario.
    """


def parse_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read NDJSON file. Raises FileNotFoundError if path missing,
    ValueError if file is empty, json.JSONDecodeError on bad lines."""


def load_config(path: Path | None, events: list[dict]) -> ScenarioDraft:
    """Load scenario config YAML, or return default draft with steps filled."""


def render(draft: ScenarioDraft) -> dict[str, Any]:
    """Call builder.build_scenario(draft), validate against Schema."""


def write(result: ConvertResult, output_path: Path | None) -> None:
    """Write YAML to output_path (mutates result.output_path / warnings)."""


def validate_config(path: Path) -> list[str]:
    """Validate a config YAML file. Returns list of error strings
    (empty if valid). Used by `gimbal prism validate`."""


@dataclass
class NdjsonStats:
    event_count: int
    method_counts: dict[str, int]
    host_counts: dict[str, int]
    status_counts: dict[int, int]
    sample_events: list[dict[str, Any]]   # 前 N 条


def inspect_ndjson(path: Path, sample_limit: int = 3) -> NdjsonStats:
    """Compute stats over NDJSON. Used by `gimbal prism inspect`."""


def ndjson_to_step_fragments(
    ndjson_path: Path,
    config_path: Path | None,
) -> list[dict[str, Any]]:
    """NDJSON → list of step fragment dicts (no scenario assembly).
    Used by `gimbal prism to-steps` and as input to other tools."""
```

#### Group B: Edit primitives (existing scenario YAML ↔ dict)

```python
def load_scenario(path: Path) -> dict[str, Any]:
    """Load scenario YAML into a plain dict. Does NOT validate.
    Used by edit subcommands."""


def save_scenario(scenario: dict[str, Any], path: Path) -> None:
    """Write scenario dict back to YAML (preserves key order)."""


def validate_scenario(scenario: dict[str, Any]) -> None:
    """Validate scenario dict against gimbal.schema.Scenario.
    Raises ValidationError on failure."""


def explain_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Produce structured summary of a scenario.
    Used by `gimbal prism explain`."""


# Section-level edit operations (atomic, return new dict, no I/O)
def get_meta(scenario: dict) -> dict[str, Any]: ...
def set_meta(scenario: dict, **fields) -> dict[str, Any]: ...

def list_users(scenario: dict) -> list[tuple[str, dict]]: ...
def add_user(scenario: dict, key: str, **fields) -> dict[str, Any]: ...
def remove_user(scenario: dict, key: str) -> dict[str, Any]: ...

def list_resources(scenario: dict) -> list[tuple[str, dict]]: ...
def add_resource(scenario: dict, name: str, **fields) -> dict[str, Any]: ...
def remove_resource(scenario: dict, name: str) -> dict[str, Any]: ...

def get_config_section(scenario: dict, field: str) -> Any: ...
def set_config_section(scenario: dict, **fields) -> dict[str, Any]: ...
```

**Design note:** all edit primitives are **pure functions** — they take a
scenario dict, return a new (or modified) dict, perform no I/O. The CLI
subcommand layer is responsible for: load → apply → validate → save.

**No step-level edit operations in this PR.** Steps come from NDJSON; CLI edit
subcommands operate on meta / users / resources / config only. Step edit is
documented as future work in §6.

### 5.2 Config YAML schema (new, but field-compatible with web `DraftIn`)

```yaml
# Required for execute-ready output; otherwise defaults applied.
scenario_id: sc_login_flow          # 缺省: derive from filename stem
name: "User login flow"             # 缺省: "Untitled scenario"
description: "data-driven smoke"    # 缺省: ""
module: auth                        # 缺省: "default"
priority: 1                         # 缺省: 1
author: alice                       # 缺省: "prism"
owner: team-a                       # 缺省: "prism"
tags: [smoke, login]                # 缺省: ["smoke"]
version: "1.0.0"                    # 缺省: "1.0.0"
expire: false                       # 缺省: false
requirement_ref: []                 # 缺省: []

# services: host → service 名映射 (used by StepDraft.api.service)
services:
  api.example.com: auth-api

# users: auth 配置
users:
  admin:
    url: https://api.example.com/auth/login
    username: admin
    password: ${env:ADMIN_PWD}      # 仅支持 ${env:VAR} 一种占位符 (v1)
    expires_in: 7200
    token_type: Authorization       # 缺省
    token: null                     # 如已拿到的 token, 直接填这里

# time_policy
time_policy:
  kind: record                      # record | timeout
  seconds: 60                       # 仅 timeout 时用

# retry
retry:
  enabled: true
  max_attempts: 3
  backoff_seconds: 20
  retry_on: [500, 502, 503]

# setup/teardown references
setup_refs: []
teardown_refs: []

# resources
resources:
  - name: redis
    kind: mock                      # mock | mock_ref | file | file_ref
    image: redis:7                  # mock
    port_mapping: {"6379": 6379}    # mock
    config: {}                      # mock
    path: ""                        # file
    ref: ""                         # mock_ref / file_ref
    value: null                     # (reserved)
```

**Field naming note:** `time_policy` and `retry` use snake_case in YAML (CLI
ergonomics) and are mapped to `timePolicy` / `retry` Pydantic fields by
`core.py`. `users` is a dict in CLI YAML (ergonomic) but maps to
`DraftIn.users: list[UserIn]` in the web wire form — `core.py` translates the
dict's keys into `UserIn.key` fields.

**Default values when config is omitted:**
- `scenario_id`: derived from NDJSON file stem (`foo.ndjson` → `sc_foo`,
  non-alphanumeric chars replaced with `_`).
- `name`: same as `scenario_id`.
- All other fields: same defaults as `DraftIn` in `gimbal/prism/server.py`.

### 5.3 CLI Surface

The `gimbal prism` group exposes **7 subcommands** in this PR, organized into
two categories:

- **A. Pipeline subcommands** (operate on NDJSON → scenario transformation)
- **B. Edit subcommands** (operate on existing scenario YAML, incremental)

#### A. Pipeline subcommands

```bash
# A1. inspect — 读 NDJSON, 输出统计 + 前 N 条样本
gimbal prism inspect -i captures/dev-1.ndjson [--limit 5]

# A2. validate — 校验 config YAML 是否合法 (Pydantic schema)
gimbal prism validate -c scenario.yaml

# A3. to-steps — NDJSON → step fragments JSON (中间产物, 调试用)
gimbal prism to-steps -i captures/dev-1.ndjson -c scenario.yaml -o steps.json

# A4. convert — 完整 pipeline (快路径, 覆盖 A1+A2+A3)
gimbal prism convert -i captures/dev-1.ndjson -c scenario.yaml -o scenarios/sc_login.yaml

# A5. explain — 读 scenario YAML 输出结构化摘要
gimbal prism explain scenarios/sc_login.yaml [--section meta|config|steps|...]
```

#### B. Edit subcommands (按 section 分组)

```bash
# B1. meta get / set
gimbal prism meta get scenarios/sc.yaml --field name
gimbal prism meta set scenarios/sc.yaml --name 'User login flow' \
  --description 'smoke' --module auth --priority 2

# B2. user list / add / remove
gimbal prism user list scenarios/sc.yaml
gimbal prism user add scenarios/sc.yaml --key admin \
  --url https://api.example.com/auth/login \
  --username admin --password-env ADMIN_PWD \
  --expires-in 7200
gimbal prism user remove scenarios/sc.yaml --key admin

# B3. resource list / add / remove
gimbal prism resource list scenarios/sc.yaml
gimbal prism resource add scenarios/sc.yaml --name redis \
  --kind mock --image redis:7 --port 6379:6379
gimbal prism resource remove scenarios/sc.yaml --name redis

# B4. config get / set (time_policy / retry / services / setup_refs / teardown_refs)
gimbal prism config get scenarios/sc.yaml --field time_policy
gimbal prism config set scenarios/sc.yaml --time-policy-kind timeout --time-policy-seconds 90
gimbal prism config set scenarios/sc.yaml --retry-enabled --retry-max-attempts 5
```

#### Flag conventions

- All subcommands accept `--home` (override `$GIMBAL_HOME`).
- Pipeline subcommands (`convert`, `to-steps`, `inspect`) accept `--quiet`.
- Edit subcommands mutate the scenario YAML in-place (read → apply → write),
  unless `--dry-run` is set (print diff to stdout, don't write).
- All subcommands write logs/errors to stderr; data to stdout.

#### Common flag matrix

| Flag | Applies to | Description |
|---|---|---|
| `--home` | all | Override `$GIMBAL_HOME` |
| `--quiet`, `-q` | pipeline only | Suppress info logs |
| `--dry-run` | edit only | Print diff, don't write |
| `--json` | inspect, explain | Output as JSON instead of human-readable text |

#### Exit codes (uniform across all subcommands)

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Usage error (Typer-level bad args) |
| 2 | Input file not found / unreadable |
| 3 | NDJSON / YAML empty or malformed |
| 4 | Scenario / config validation failed |
| 5 | Unexpected internal error |
| 6 | Edit conflict (e.g., `--remove` on non-existent user) |

**Streams (uniform):**
- Data output (YAML / JSON / text) → stdout
- Info / progress logs → stderr
- Errors → stderr

### 5.4 Error handling matrix

| Condition | Detection | Behavior |
|---|---|---|
| `--input` not found | `parse_ndjson` raises `FileNotFoundError` | exit 2, stderr: `input not found: <path>` |
| NDJSON file empty | `parse_ndjson` raises `ValueError("no events")` | exit 3 |
| NDJSON malformed line | `json.JSONDecodeError` | exit 3, stderr: `line N: invalid JSON` |
| `--config` not found | `load_config` raises `FileNotFoundError` | exit 2, stderr: `config not found: <path>` |
| Config validation fail | `pydantic.ValidationError` | exit 4, stderr: field-level errors |
| Scenario validation fail | `Scenario.model_validate` raises | exit 4, stderr: field-level errors |
| `--output` parent dir missing | `write` creates parents | exit 0 |
| Any other exception | catch-all | exit 5, stderr: traceback (unless `--quiet`) |

### 5.5 Sync obligation with `builder.py`

The user explicitly requested: "core 与 build_scenario 同步更新". Enforcement:

1. **Parity canary test** (see §5.6) — runs on every CI, fails on byte-level
   drift between web and CLI output. **Detects** drift; does not **prevent**
   it. Maintainer must fix `core.py` to match `builder.py` whenever the
   canary fails.
2. **One source of truth** — `core.convert_ndjson_to_scenario` calls
   `builder.build_scenario` under the hood. New fields in `ScenarioDraft`
   must be mirrored in `core.py`'s `load_config` YAML schema.
3. **Doc comment** — `core.py` module docstring explicitly states the
   obligation and points to the canary test path.

### 5.6 Test plan

**`tests/test_prism_core.py`** (~14 unit cases):

Group A — pipeline:
- `test_parse_ndjson_minimal`
- `test_parse_ndjson_empty_raises`
- `test_parse_ndjson_missing_raises`
- `test_parse_ndjson_bad_line_raises`
- `test_load_config_none_returns_default_draft`
- `test_load_config_full_yaml`
- `test_render_validates_against_schema`
- `test_render_minimal_produces_scenario`
- `test_write_returns_yaml_when_no_output`
- `test_write_writes_file_when_output_given`
- `test_inspect_ndjson_stats`
- `test_validate_config_returns_errors`
- `test_ndjson_to_step_fragments`

Group B — edit primitives:
- `test_get_set_meta_roundtrip`
- `test_user_add_remove_roundtrip`
- `test_resource_add_remove_roundtrip`
- `test_config_set_section_validates`
- `test_load_save_scenario_preserves_keys`

**`tests/test_prism_core_builder_parity.py`** (parity canary, 2 cases):

- `test_parity_default_scenario`
- `test_parity_with_config`

**`tests/test_prism_cli_*.py`** (one test file per subcommand, ~5 cases each):

- `test_prism_cli_convert.py` — convert subcommand (existing tests, expanded)
- `test_prism_cli_inspect.py` — inspect subcommand
- `test_prism_cli_validate.py` — validate subcommand
- `test_prism_cli_to_steps.py` — to-steps subcommand
- `test_prism_cli_explain.py` — explain subcommand
- `test_prism_cli_meta.py` — meta get / set
- `test_prism_cli_user.py` — user list / add / remove
- `test_prism_cli_resource.py` — resource list / add / remove
- `test_prism_cli_config.py` — config get / set

Total CLI tests: ~45 cases.

**Uniform CLI test pattern** (each file follows it):

- `test_<sub>_basic_invocation` — happy path
- `test_<sub>_to_stdout` — output goes to stdout
- `test_<sub>_to_file` — `--output` writes file
- `test_<sub>_exit_code_2_missing_input` — input not found
- `test_<sub>_exit_code_4_validation` — invalid input

**Regression safety net:** existing 237 tests in `tests/test_prism_*` and
`tests/test_captures_*` must remain green. Web prism is untouched.

### 5.7 Documentation updates

- `README.md` — replace the single-row subcommand table with a full table
  covering all 7 subcommands (convert / inspect / validate / to-steps /
  explain / meta / user / resource / config).
- `USER_MANUAL.md` — add §X "Headless CLI" with sections:
  - X.1 Pipeline subcommands (convert / inspect / validate / to-steps / explain)
  - X.2 Edit subcommands (meta / user / resource / config)
  - X.3 Config YAML reference (full schema)
  - X.4 Exit code reference
  - X.5 Common workflows (CI integration, batch processing)
- `CHANGELOG.md` — add `v0.6.0` entry under "Added" with the full subcommand
  list and the new `core.py` module.

## 6. Future Work (NOT in this PR)

### 6.1 Web prism migration to `core.py`

When (if) we choose to migrate web to core:

- Replace `_draft_from_in()` calls in `gimbal/prism/server.py` with calls to
  `core.convert_ndjson_to_scenario()`.
- Keep the `DraftIn` wire form unchanged so the UI doesn't break.
- Update server endpoints (`/api/draft/{sid}/export`, `/yaml`) to call core.
- The edit primitives (`get_meta`, `set_user`, etc.) become useful to the web
  UI as well: when a user edits a field in the UI, it could route through
  `core.set_X(scenario, ...)` for consistency.
- Reuse the parity canary as a regression test.

Triggering conditions:
- `builder.py` complexity grows (e.g., new step-level overrides)
- Web session state becomes hard to maintain
- A bug fix in core is hard to verify in web
- Web UI wants to expose "edit individual field" buttons (matches CLI
  edit subcommands 1:1)

### 6.2 Step-level edit subcommands

This PR's edit subcommands cover meta / user / resource / config but **not**
steps (steps come from NDJSON). A future PR could add:

- `gimbal prism step list <scenario.yaml>`
- `gimbal prism step enable/disable <scenario.yaml> --index N`
- `gimbal prism step set-assertion <scenario.yaml> --index N --expected 200`
- `gimbal prism step reorder <scenario.yaml> --from N --to M`

These would mirror the web UI's per-step editing. The `core.py` primitives
for these (`get_step`, `set_step`, `reorder_steps`) are deferred.

### 6.3 Parameterized "data-driven" feature

The `gimbal-step-import-future-scope.md` memory describes a future feature
where JSON/YAML test-case files (parameterized templates × data rows) generate
multiple concrete scenarios.

This PR **does not** implement that. The spec keeps the boundary clean:
- "数据驱动" in this PR = capture-driven (NDJSON = sequential events).
- The parameterized feature is a separate, future PR with its own spec.

The cleanest insertion point for parameterized expansion is between
`parse_ndjson` and `load_config` in `core.py` (a future
`expand_template(draft, data_rows)` stage).

## 7. Open Questions

None at draft time. Awaiting user review.

(Resolved during self-review:
1. `scenario_id` default behaviour when config is omitted → derived from
   NDJSON file stem.
2. Parity canary **detects** rather than **prevents** drift.
3. Multi-subcommand scope expanded mid-iteration per user feedback — now
   includes pipeline subcommands (inspect / validate / to-steps / explain)
   and section-grouped edit subcommands (meta / user / resource / config).
   Step-level edit deferred to §6.2.)

## 8. Acceptance Criteria

**Pipeline subcommands (5):**
- [ ] `gimbal prism inspect -i foo.ndjson` outputs stats + sample events
- [ ] `gimbal prism validate -c cfg.yaml` outputs validation errors (or success)
- [ ] `gimbal prism to-steps -i foo.ndjson` outputs step fragment JSON
- [ ] `gimbal prism convert -i foo.ndjson -c cfg.yaml` prints valid Scenario
      YAML to stdout
- [ ] `gimbal prism convert ... -o out.yaml` writes a Scenario YAML that
      `Scenario.model_validate` accepts
- [ ] `gimbal prism explain scenarios/foo.yaml` outputs structured summary

**Edit subcommands (4 sections):**
- [ ] `gimbal prism meta get/set` round-trips meta fields
- [ ] `gimbal prism user add/list/remove` round-trips user entries
- [ ] `gimbal prism resource add/list/remove` round-trips resource entries
- [ ] `gimbal prism config get/set` round-trips time_policy / retry / services
- [ ] All edit subcommands support `--dry-run`
- [ ] All edit subcommands validate after edit (`Scenario.model_validate`)

**Quality gates:**
- [ ] CLI output is byte-identical to what the web UI would produce given the
      same NDJSON + same config (parity canary)
- [ ] All 7 exit codes (0, 1, 2, 3, 4, 5, 6) reachable and tested
- [ ] All existing 237 tests still pass (web prism untouched)
- [ ] All new core functions have unit tests (~14 cases)
- [ ] All new CLI subcommands have integration tests (~5 cases × 9 files)
- [ ] `README.md`, `USER_MANUAL.md`, `CHANGELOG.md` updated with full
      subcommand reference
- [ ] No new dependencies added to `requirements.txt`
- [ ] `gimbal/prism/cli.py` (old single file) migrated to `gimbal/prism/cli/`
      subpackage without breaking external imports