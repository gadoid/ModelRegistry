"""gimbal.capture.strategy — 筛选策略的数据模型与编译产物。

v0.4 引入: 把 gimbal capture 的筛选从"CSV 前缀"升级为"YAML 策略文件 + profile + include 复用"。
本模块只定义数据类 (Pydantic) + 编译后产物 (CompiledRule / CompiledMatcher)。
实际加载 (YAML 解析、include 递归、profile 选择) 在 `gimbal.capture.loader` 模块。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─── 枚举 ──────────────────────────────────────────────────────────────────


class FilterMode(str, Enum):
    """规则模式: include (白名单) / exclude (黑名单)。"""

    INCLUDE = "include"
    EXCLUDE = "exclude"


# ─── Pydantic 数据模型 ─────────────────────────────────────────────────────


class Rule(BaseModel):
    """单条匹配规则。

    同一 rule 内: 所有填写的字段都必须满足 (AND 语义)。
    多条 rule 之间: 任一命中即通过 (OR 语义)。
    所有字段可选, 但空 rule 被拒绝。
    """

    model_config = ConfigDict(extra="forbid")

    mode: Optional[FilterMode] = None  # None = 继承顶层 mode
    host: Optional[str] = None  # 精确匹配
    host_glob: Optional[str] = None  # fnmatch, 与 host 互斥
    host_regex: Optional[str] = None  # 正则, 与 host/host_glob 互斥
    path: Optional[str] = None  # 前缀匹配 (与现有 PathFilter 一致)
    path_glob: Optional[str] = None
    path_regex: Optional[str] = None
    methods: Optional[list[str]] = None

    @field_validator("methods")
    @classmethod
    def _upper_methods(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """methods 统一大写。"""
        return [m.upper() for m in v] if v else v

    @model_validator(mode="after")
    def _no_empty_rule(self) -> "Rule":
        """rule 至少需要 1 个匹配字段。"""
        if not any(
            [
                self.host,
                self.host_glob,
                self.host_regex,
                self.path,
                self.path_glob,
                self.path_regex,
                self.methods,
            ]
        ):
            raise ValueError("rule 至少需要 1 个匹配字段")
        return self

    @model_validator(mode="after")
    def _mutually_exclusive(self) -> "Rule":
        """host / path 的三选一互斥。"""
        host_fields = [self.host, self.host_glob, self.host_regex]
        if sum(f is not None for f in host_fields) > 1:
            raise ValueError("host / host_glob / host_regex 只能选一个")

        path_fields = [self.path, self.path_glob, self.path_regex]
        if sum(f is not None for f in path_fields) > 1:
            raise ValueError("path / path_glob / path_regex 只能选一个")

        return self


class Profile(BaseModel):
    """一组命名规则。"""

    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = None
    rules: list[Rule] = Field(default_factory=list)


class StrategyFile(BaseModel):
    """一份 YAML 筛选策略文件的根结构。

    `mode` 决定无 rule 命中时的默认语义 (include / exclude)。
    `default_profile` 在不指定 --filter-profile 时使用。
    `includes` 是相对路径列表, 跨文件组合 profiles (include 解析在 loader 里做)。
    """

    model_config = ConfigDict(extra="forbid")

    mode: FilterMode = FilterMode.INCLUDE
    default_profile: Optional[str] = None
    includes: list[Path] = Field(default_factory=list)
    profiles: dict[str, Profile]


# ─── 编译产物 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompiledRule:
    """编译后单条规则: 正则预编译, mode 在编译时已解析为具体值。"""

    mode: FilterMode
    host: Optional[re.Pattern[str]]
    path_prefix: Optional[str]
    path_re: Optional[re.Pattern[str]]
    methods: Optional[frozenset[str]]


class CompiledMatcher:
    """mitmdump 子进程内使用的匹配器。

    匹配语义 (spec §3.4):
      - rule 命中 (同一 rule 内 host + path + method 都满足) →
        mode=INCLUDE → 记录, mode=EXCLUDE → 不记录
      - 无 rule 命中 → 由 default_mode 决定 (INCLUDE 文件 → False / EXCLUDE 文件 → True)

    顶层 mode (StrategyFile.mode) 决定两个东西:
      1. Rule.mode=None 的继承方向
      2. 无 rule 命中时的 default_mode (与顶层 mode 相反)
    """

    def __init__(
        self,
        rules: list[CompiledRule],
        default_mode: FilterMode = FilterMode.INCLUDE,
    ) -> None:
        """default_mode: 无 rule 命中时的"通过方向"。

        loader 在编译时传入, 通常为:
          - sf.mode = INCLUDE → default_mode = EXCLUDE (白名单: 没在列表就不录)
          - sf.mode = EXCLUDE → default_mode = INCLUDE (黑名单: 没在列表就录)
        """
        self.rules = list(rules)
        self.default_mode = default_mode

    def match(self, event: dict) -> bool:
        """事件是否应被记录。

        任一 rule 命中 → 由该 rule 的 mode 决定 (include=True / exclude=False)。
        无 rule 命中 → default_mode == INCLUDE。
        """
        for rule in self.rules:
            if self._match_one(rule, event):
                return rule.mode == FilterMode.INCLUDE
        return self.default_mode == FilterMode.INCLUDE

    def match_with_reason(
        self, event: dict
    ) -> tuple[bool, Optional[str]]:
        """调试用: 返回 (是否记录, 命中的 rule 描述或 None)。"""
        for idx, rule in enumerate(self.rules, 1):
            if self._match_one(rule, event):
                desc = self._describe_rule(idx, rule)
                return rule.mode == FilterMode.INCLUDE, desc
        return self.default_mode == FilterMode.INCLUDE, None

    @staticmethod
    def _match_one(rule: CompiledRule, event: dict) -> bool:
        """单条 rule 的 AND 匹配。"""
        method = (event.get("method") or "").upper()
        host = event.get("host") or ""
        path = event.get("path") or ""

        if rule.methods and method not in rule.methods:
            return False
        if rule.host and not rule.host.search(host):
            return False
        if rule.path_prefix and not (
            path == rule.path_prefix
            or path.startswith(rule.path_prefix + "/")
        ):
            return False
        if rule.path_re and not rule.path_re.search(path):
            return False
        return True

    @staticmethod
    def _describe_rule(idx: int, rule: CompiledRule) -> str:
        """生成 rule 的人类可读描述 (供调试 / 日志)。"""
        parts = [f"rule #{idx}", f"mode={rule.mode.value}"]
        if rule.host:
            parts.append(f"host={rule.host.pattern!r}")
        if rule.path_prefix:
            parts.append(f"path_prefix={rule.path_prefix!r}")
        if rule.path_re:
            parts.append(f"path_re={rule.path_re.pattern!r}")
        if rule.methods:
            parts.append(f"methods={sorted(rule.methods)}")
        return " ".join(parts)
