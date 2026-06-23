"""gimbal.capture.loader — 筛选策略文件的加载与编译。

负责把 CLI 参数 (--filter-file / --filter-profile / --filter / --filter-mode / --strict-files-only)
解析成 mitmdump 子进程可用的 `CompiledMatcher`。

四步流水线:
  1. 文件发现 (--filter-file 优先 / 自动 search_paths)
  2. YAML 解析 + Pydantic 校验
  3. include 递归解析 (以主文件目录为基准, 环检测)
  4. profile 选择 + CLI CSV 追加 + 正则预编译

不依赖 `gimbal.prism.*`, 可独立测试。
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Optional

import typer
import yaml

from .strategy import (
    CompiledMatcher,
    CompiledRule,
    FilterMode,
    Profile,
    Rule,
    StrategyFile,
)


# ─── 异常体系 ──────────────────────────────────────────────────────────────


class FilterConfigError(Exception):
    """筛选配置错误, 父进程捕到 → 退出码 5 + 红字。"""


class FilterFileNotFound(FilterConfigError):
    """找不到 filter 文件 (--filter-file 不存在 / --strict-files-only)。"""


class IncludeCycleError(FilterConfigError):
    """include 自环或互环。"""


class ProfileNotFound(FilterConfigError):
    """profile 名不在文件 profiles 中。"""


class RuleCompileError(FilterConfigError):
    """rule 正则编译失败。"""


class EmptyRulesError(FilterConfigError):
    """profile 没有任何规则, 也没传 --filter 兜底。"""


# ─── 文件发现 ──────────────────────────────────────────────────────────────


def _default_search_paths() -> tuple[Optional[Path], ...]:
    """默认搜索路径顺序 (先 CWD, 后用户家目录)。"""
    env = os.environ.get("GIMBAL_FILTERS")
    return (
        Path.cwd() / ".gimbal" / "filters.yaml",
        Path.cwd() / "filters.yaml",
        Path.home() / ".gimbal" / "filters.yaml",
        Path(env).expanduser() if env else None,
    )


def discover_filter_file(
    explicit: Optional[Path | str],
    search_paths: tuple[Optional[Path], ...],
    strict: bool,
) -> Optional[Path]:
    """--filter-file 优先; 否则按 search_paths 找第一个存在的文件。

    strict=True 且未找到 → FilterFileNotFound。

    explicit 接受 str 或 Path: 父进程走 CliRunner 校验时是 Path,
    mitmdump 子进程 exec addon 脚本时是 str(经 f-string 序列化) —
    统一在边界 coerce,避免上下游各自防御。
    """
    if explicit is not None and explicit != "":
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise FilterFileNotFound(f"--filter-file 指定的文件不存在: {p}")
        return p

    for p in search_paths:
        if p and p.exists():
            return p.resolve()

    if strict:
        raise FilterFileNotFound("未找到 filter 文件 (--strict-files-only 已启用)")
    return None


# ─── YAML 解析 ─────────────────────────────────────────────────────────────


def _load_one_yaml(path: Path) -> StrategyFile:
    """加载单个 YAML 文件, 解析为 StrategyFile。"""
    if not path.exists():
        raise FilterFileNotFound(f"filter 文件不存在: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise FilterConfigError(f"{path}: YAML 解析失败: {e}") from e
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise FilterConfigError(
            f"{path}: 根节点必须是 mapping, 得到 {type(raw).__name__}"
        )
    try:
        return StrategyFile.model_validate(raw)
    except Exception as e:
        raise FilterConfigError(f"{path}: 策略文件校验失败: {e}") from e


# ─── include 解析 ──────────────────────────────────────────────────────────


def resolve_includes(
    main_path: Path,
    visited: Optional[frozenset[Path]] = None,
) -> StrategyFile:
    """递归加载 main_path + 它的 includes。

    - 跨文件 profile 合并: 后者覆盖前者 + 警告
    - 顶层 mode / default_profile / includes 只用主文件的
    - include 路径以主文件所在目录为基准 (不是 CWD)
    - visited 在函数边界检测, 发现环 → IncludeCycleError
    """
    abs_main = main_path.resolve()
    visited = visited or frozenset()
    if abs_main in visited:
        raise IncludeCycleError(f"include 循环: {abs_main}")

    sf = _load_one_yaml(abs_main)

    for inc in sf.includes:
        inc_abs = (abs_main.parent / inc).resolve()
        inc_sf = resolve_includes(inc_abs, visited | {abs_main})
        for name, prof in inc_sf.profiles.items():
            if name in sf.profiles:
                typer.secho(
                    f"[filter] 警告: profile {name!r} 被覆盖 "
                    f"(来源: {inc_abs.name})",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            sf.profiles[name] = prof
    return sf


# ─── profile 选择 ──────────────────────────────────────────────────────────


def select_profile(sf: StrategyFile, name: Optional[str]) -> Profile:
    """选 profile: 显式 > default_profile > 单 profile 自动。"""
    chosen = name or sf.default_profile
    if chosen is None:
        if len(sf.profiles) == 1:
            return next(iter(sf.profiles.values()))
        raise ProfileNotFound(
            f"文件含 {len(sf.profiles)} 个 profile, 必须 --filter-profile 指定, "
            f"或文件内设置 default_profile"
        )
    if chosen not in sf.profiles:
        raise ProfileNotFound(
            f"profile {chosen!r} 不存在, 文件中只有: {sorted(sf.profiles)}"
        )
    return sf.profiles[chosen]


# ─── CLI 追加规则 ──────────────────────────────────────────────────────────


def append_cli_rules(
    profile: Profile,
    csv: Optional[str],
    cli_mode: FilterMode,
) -> None:
    """把 --filter '/a,/b' 转成 Rule 列表, 追加到 profile.rules 末尾。

    每条 CSV 元素 → Rule(path=p, mode=cli_mode)。
    空 csv → 不追加 (保留纯文件行为)。
    """
    if not csv:
        return
    for p in csv.split(","):
        p = p.strip()
        if not p:
            continue
        profile.rules.append(Rule(path=p, mode=cli_mode))


# ─── 编译 ──────────────────────────────────────────────────────────────────


def _compile_host(rule: Rule) -> Optional[re.Pattern[str]]:
    """host 字段编译为 re.Pattern。"""
    if rule.host:
        return re.compile(re.escape(rule.host))
    if rule.host_glob:
        return re.compile(fnmatch.translate(rule.host_glob))
    if rule.host_regex:
        return re.compile(rule.host_regex)
    return None


def _compile_path(rule: Rule) -> tuple[Optional[str], Optional[re.Pattern[str]]]:
    """path 字段编译: prefix 直接返回, glob/regex 走 re.compile。"""
    if rule.path:
        return rule.path, None
    if rule.path_glob:
        return None, re.compile(fnmatch.translate(rule.path_glob))
    if rule.path_regex:
        return None, re.compile(rule.path_regex)
    return None, None


def _compile_one(
    idx: int, rule: Rule, default_mode: FilterMode
) -> CompiledRule:
    """单条 Rule → CompiledRule。"""
    mode = rule.mode or default_mode
    host_re = _compile_host(rule)
    path_prefix, path_re = _compile_path(rule)
    methods = frozenset(rule.methods) if rule.methods else None
    return CompiledRule(
        mode=mode,
        host=host_re,
        path_prefix=path_prefix,
        path_re=path_re,
        methods=methods,
    )


def compile_matcher(sf: StrategyFile, profile: Profile) -> CompiledMatcher:
    """把 Profile.rules 编译成 CompiledMatcher。

    default_mode = sf.mode 的反向:
      - sf.mode = INCLUDE → default = EXCLUDE (白名单, 无 rule 命中时不录)
      - sf.mode = EXCLUDE → default = INCLUDE (黑名单, 无 rule 命中时录)

    编译失败 → RuleCompileError, 提示 rule 索引和原因。
    """
    compiled: list[CompiledRule] = []
    for idx, rule in enumerate(profile.rules):
        try:
            compiled.append(_compile_one(idx, rule, sf.mode))
        except re.error as e:
            raise RuleCompileError(
                f"profile rule #{idx + 1} 正则编译失败: {e}\n"
                f"  rule: {rule.model_dump_json(indent=2)}"
            ) from e
    default_mode = (
        FilterMode.EXCLUDE if sf.mode == FilterMode.INCLUDE else FilterMode.INCLUDE
    )
    return CompiledMatcher(compiled, default_mode=default_mode)


# ─── 旧行为兜底 ────────────────────────────────────────────────────────────


def _sentinel_match_all() -> CompiledMatcher:
    """全匹配 sentinel rule: 等价于 v0 PathFilter([]).match() == True。"""
    return CompiledMatcher(
        [
            CompiledRule(
                mode=FilterMode.INCLUDE,
                host=None,
                path_prefix=None,
                path_re=None,
                methods=None,
            )
        ],
        default_mode=FilterMode.INCLUDE,
    )


def _matcher_from_csv(csv: str, cli_mode: FilterMode) -> CompiledMatcher:
    """纯 CSV 路径: 每条 → path 前缀 Rule, default_mode 与 cli_mode 相反。"""
    csv_rules = [p.strip() for p in csv.split(",") if p.strip()]
    if not csv_rules:
        return _sentinel_match_all()
    default_mode = (
        FilterMode.EXCLUDE if cli_mode == FilterMode.INCLUDE else FilterMode.INCLUDE
    )
    compiled = [
        CompiledRule(
            mode=cli_mode,
            host=None,
            path_prefix=p.rstrip("/"),
            path_re=None,
            methods=None,
        )
        for p in csv_rules
    ]
    return CompiledMatcher(compiled, default_mode=default_mode)


# ─── 端到端入口 ────────────────────────────────────────────────────────────


def build_matcher(
    *,
    filter_file: Optional[Path],
    profile: Optional[str],
    cli_csv: Optional[str],
    cli_mode: FilterMode,
    strict_files_only: bool = False,
    _strategy_file: Optional[StrategyFile] = None,
) -> CompiledMatcher:
    """端到端: CLI 参数 → CompiledMatcher。

    分支:
      A. 找到文件 + profile.rules 非空 → 编译文件规则
      B. 找到文件 + profile.rules 为空 且 无 CSV → EmptyRulesError
      C. 找不到文件 + 无 CSV → 旧行为兜底 (sentinel 全匹配)
      D. 找不到文件 + 有 CSV → 纯 CSV 路径
    """
    if _strategy_file is not None:
        # 测试旁路: 直接用已加载的 StrategyFile
        sf = _strategy_file
    else:
        file_path = discover_filter_file(
            filter_file, _default_search_paths(), strict_files_only
        )
        if file_path is None:
            # 分支 C / D
            if not cli_csv:
                return _sentinel_match_all()
            return _matcher_from_csv(cli_csv, cli_mode)
        sf = resolve_includes(file_path)

    prof = select_profile(sf, profile)
    append_cli_rules(prof, cli_csv, cli_mode)
    if not prof.rules:
        raise EmptyRulesError("选中的 profile 无任何规则, 请至少 1 条或加 --filter")
    return compile_matcher(sf, prof)
