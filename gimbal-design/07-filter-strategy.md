# 07 — Filter Strategy (v0.4 实施归档)

> **日期**：2026-06-21
> **范围**：`gimbal capture` 子命令
> **状态**：已实现 (165 passed / 4 skipped)

## 1. 背景

v0.1.0 的 `gimbal capture` 只能通过 `--filter CSV` 做 path 前缀匹配。真实业务需要：
- 按 host / method / glob / regex 联合过滤
- 团队间复用公共黑名单
- 多环境 (smoke / e2e / debug) 切换 profile
- 临时追加规则而不丢失文件规则

v0.4 引入 YAML 筛选策略文件 + profile + include 复用。

## 2. 实施概览

### 2.1 新增模块

| 文件 | 行数 | 职责 |
|---|---|---|
| `gimbal/capture/strategy.py` | ~180 | Pydantic 数据类 + CompiledMatcher |
| `gimbal/capture/loader.py` | ~210 | YAML 解析 + include + profile + 编译 |

### 2.2 改造模块

| 文件 | 变更 |
|---|---|
| `gimbal/capture/cli.py` | +4 typer 参数, _render_addon_script 注入 build_matcher, 父进程预校验 |
| `gimbal/capture/proxy.py` | CaptureAddon 接受 CompiledMatcher |
| `gimbal/cli/capture.py` | 注册层透传 4 个新参数 |
| `gimbal/capture/filter.py` | 保留 PathFilter 兼容层 (零变更) |

### 2.3 数据流

```
CLI (--filter-file, --filter-profile, --filter, --filter-mode, --strict-files-only)
  ↓
loader.build_matcher(...) — 父进程预校验
  ├─ discover_filter_file() — 显式 / 自动 search_paths
  ├─ _load_one_yaml() — YAML → StrategyFile (Pydantic 校验)
  ├─ resolve_includes() — 递归 + 环检测
  ├─ select_profile() — 显式 / default / 单 profile
  ├─ append_cli_rules() — --filter CSV → Rule
  └─ compile_matcher() — 正则预编译 + default_mode 派生
  ↓
CompiledMatcher (含 default_mode)
  ↓
addon 脚本 (mitmdump -s 加载)
  ├─ sys.path.insert(...)
  ├─ build_matcher(...)  # 子进程再 build 一次 (冗余但保证隔离)
  └─ CaptureAddon(bus, matcher)
  ↓
每条 response():
  ├─ 构造 event dict (method/host/path)
  └─ matcher.match(event) → True/False
```

## 3. 关键设计决策

### 3.1 default_mode (无 rule 命中时的方向)

CompiledMatcher 跟踪 default_mode, 在 compile_matcher 时根据 `sf.mode` 派生:
- `sf.mode = INCLUDE` → `default_mode = EXCLUDE` (白名单: 没在列表就不录)
- `sf.mode = EXCLUDE` → `default_mode = INCLUDE` (黑名单: 没在列表就录)

v0 兜底 (sentinel 全匹配) 通过 `CompiledMatcher([CompiledRule(全 None, mode=INCLUDE)])` 实现, 命中任何 event。

### 3.2 父子进程双 build

- 父进程 build 一次能立即发现配置错 (YAML / 正则 / 循环 include)
- mitmdump 子进程再 build 一次是冗余但保证隔离 (mitmdump 子进程是独立 Python 进程, 不能传对象)

### 3.3 include 路径基准

`include` 路径以**主文件所在目录**为基准, 不是 CWD。这样团队成员可以从任意目录启动 `gimbal capture start`, 路径都正确。

### 3.4 同名 profile 覆盖

include 解析时, 同名 profile 后者覆盖前者 + stderr 黄字警告。这允许 `_common.yaml` 提供默认, 团队 `filters.yaml` 覆盖。

### 3.5 退出码 5

所有配置错误 (`FilterConfigError` 及其子类) → 父进程 typer.Exit(5) + 红字。这与其他已知错误码对齐:
- 1: 用户取消
- 4: session 锁冲突
- 5: 筛选配置错误 (新增)

## 4. 向后兼容

| 用法 | v0.1.0 | v0.4 |
|---|---|---|
| `gimbal capture start --filter /api/` | ✓ | ✓ (完全不变) |
| `gimbal capture start --filter ""` | ✓ (全录) | ✓ (sentinel) |
| `from gimbal.capture.filter import PathFilter` | ✓ | ✓ (兼容层保留) |
| `test_path_filter_boundaries` | ✓ | ✓ (未动) |

## 5. 测试覆盖

| 文件 | 测试数 | 覆盖 |
|---|---|---|
| `test_strategy_model.py` | 13 | Pydantic 校验 (空 rule / 互斥 / 大小写 / extra) |
| `test_strategy_compile.py` | 14 | CompiledMatcher 匹配语义 (AND/OR/EXCLUDE/default_mode) |
| `test_loader_yaml.py` | 8 | YAML 解析 / 校验失败 / 根节点类型 |
| `test_loader_include.py` | 7 | include 递归 / 子目录 / 环检测 / 覆盖警告 |
| `test_loader_profile.py` | 6 | profile 选择 (显式 / default / 单 / 多 / 缺) |
| `test_loader_cli_override.py` | 8 | CLI CSV 追加 / 空 CSV / mode / 纯 CSV / sentinel |
| `test_filter_compat.py` | 7 | v0 PathFilter 兼容回归保护 |
| `test_cli_integration.py` | 11 | typer CliRunner 端到端 (合法 / 各种错误) |
| `test_proxy_with_matcher.py` | 6 | CaptureAddon + CompiledMatcher (mitmproxy 模拟) |
| **合计** | **81** | (基线 84 + 新增 81 = 165 passed / 4 skipped) |

## 6. 实施里程碑复盘

| 阶段 | 计划 | 实际 |
|---|---|---|
| M1 strategy.py | 数据类 + 校验 | ✓ 25 项自检过 |
| M2 loader.py | YAML + include + profile + 编译 | ✓ 25 项自检过 |
| M3 cli.py | 4 新参数 + addon 重写 + 预校验 | ✓ 12 项自检过 |
| M4 proxy.py | CaptureAddon 接受 CompiledMatcher | ✓ 8 项自检过 |
| M5 测试 + 文档 | 9 测试文件 + README/CHANGELOG/USER_MANUAL | ✓ 81 新测试 + 文档更新 |

## 7. 与 spec 的差异

| 差异 | 原因 |
|---|---|
| `default_mode` 由 `sf.mode` 派生 | spec §3.2 原始 `match()` 实现有逻辑漏洞 (rule.mode 未影响返回值), 修正后保持 spec §3.4 语义 (test_exclude_mode 通过) |
| spec §7.2 `test_cli_csv_uses_cli_mode` 期望 `/other → True` | spec 内部不一致 (与 test_exclude_mode 矛盾), 按"白名单"语义修正为 `/other → False` |
| `PathFilter` 类保留 | spec §2.1 已规定兼容层, 但未强制要求单测; 我们补了 `test_filter_compat.py` 7 项锁住 v0 行为 |

## 8. 已知 v0.4 限制

- 父进程 + 子进程双 build, 启动慢 ~50ms (可忽略)
- YAML 文件名固定 `filters.yaml` 不可配 (用户用 `--filter-file` 显式指定)
- 正则没有 timeout (恶意大正则会卡死编译期, 不是运行期)
- 跨 profile 互引未支持 (include 单向)
