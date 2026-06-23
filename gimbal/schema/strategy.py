"""gimbal/schema/strategy.py — Strategy / Extract / Assign / Assertion + 枚举。"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Literal, Union, Annotated, List
from pydantic import BaseModel, ConfigDict, Field as _PydField

from .ref import RefBase


class Scope(str, Enum):
    FRAMEWORK = "framework"
    SESSION = "session"
    SCENARIO = "scenario"
    STEP = "step"
    REQUEST = "request"


class AssertOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EXISTS = "exists"
    EMPTY = "empty"
    LENGTH_EQ = "length_eq"
    SCHEMA = "schema"


class StrategyPhase(str, Enum):
    BEFORE_REQUEST = "before_request"
    AFTER_REQUEST = "after_request"
    VERIFYING = "verifying"
    TEARDOWN = "teardown"


class FailurePolicy(str, Enum):
    ABORT = "abort"
    CONTINUE = "continue"
    WARN = "warn"
    RETRY = "retry"


class StrategyBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = _PydField(None, description="策略名 (builder 自动生成, UI 可改)")
    phase: Optional[StrategyPhase] = _PydField(None, description="处理的阶段")
    order: int = _PydField(0, description="执行顺序")
    enabled: bool = _PydField(True, description="是否启用")
    onFailure: FailurePolicy = _PydField(FailurePolicy.ABORT, description="失败处理策略")
    timeout: Optional[float] = _PydField(None, description="策略执行超时 (秒)")
    tags: List[str] = _PydField(default_factory=list, description="标签")


class Extract(StrategyBase):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["extract"] = "extract"
    expression: str = _PydField(..., description="JSONPath, 在 scratch 上导航")
    target: str = _PydField(..., description="写入目标的 key")
    scope: Scope = _PydField(Scope.STEP, description="变量作用域")
    default: Optional[Any] = _PydField(None, description="提取失败时的默认值")
    required: bool = _PydField(True, description="提取失败是否抛异常")


class Assign(StrategyBase):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["assign"] = "assign"
    source: Any = _PydField(..., description="路径或值")
    target: str = _PydField(..., description="模板路径")
    scope: Scope = _PydField(Scope.SCENARIO, description="作用域")
    default: Optional[Any] = _PydField(None, description="提取失败时的默认值")
    required: bool = _PydField(True, description="注入失败是否抛异常")


class Assertion(StrategyBase):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["assertion"] = "assertion"
    target: str = _PydField(..., description="断言的目标字段")
    operator: AssertOperator = _PydField(..., description="断言的比较符")
    expected: Any = _PydField(None, description="断言的比较值")
    message: Optional[str] = _PydField(None, description="断言失败信息")
    soft: bool = _PydField(False, description="软断言 (失败不中断)")


class StrategyRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["strategy_ref"] = "strategy_ref"


StrategyUnion = Annotated[
    Union[Extract, Assign, Assertion, StrategyRef],
    _PydField(discriminator="kind"),
]


if __name__ == "__main__":
    e = Extract(expression="$.x", target="v")
    print(f"Extract: {e.expression} -> {e.target}")
