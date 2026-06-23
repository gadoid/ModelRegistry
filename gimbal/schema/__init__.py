"""gimbal.schema — Pydantic 静态描述层(SSOT)。

导出:
  - 从 .scenario / .step / .resource / .api / .request / .strategy / .timepolicy /
    .retrypolicy / .setup / .teardown / .auth / .ref / .states 公开所有类
  - 包装版 ``Field(..., ui=...)``,UI 元数据走 ``json_schema_extra["ui"]``,
    不进入 ``model_dump``

用法::

    from gimbal.schema import Scenario, Meta, Field

    class Meta(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field("", min_length=1, ui={"widget": "input", "label": "用例名", "required": True})
"""
from __future__ import annotations

from typing import Any

from pydantic import Field as _PydanticField

# ────────────────────────────────────────────────────────────────────────────
# 包装版 Field(支持 ui 元数据)
# ────────────────────────────────────────────────────────────────────────────


def Field(  # type: ignore[no-redef]
    default: Any = ...,
    *,
    ui: dict[str, Any] | None = None,
    **kwargs: Any,
):
    """在 pydantic.Field 基础上增加 ``ui`` 参数。

    ui 字典不进入 ``model_dump``,只经 ``json_schema_extra`` 传递,
    给 ``/api/schema/ui-spec`` 端点反射使用。
    """
    if ui is not None:
        existing = kwargs.get("json_schema_extra")
        merged: dict[str, Any] = {**(existing or {}), "ui": ui}
        kwargs["json_schema_extra"] = merged
    return _PydanticField(default, **kwargs)


# ────────────────────────────────────────────────────────────────────────────
# 重导出子模块
# ────────────────────────────────────────────────────────────────────────────


from .states import StepState
from .ref import RefBase, Ref
from .resource import (
    Resource, Mock, File, MockRef, FileRef, ResourceUnion,
)
from .api import Api, ApiRef, ApiUnion
from .request import Request, RequestRef, RequestUnion
from .step import Step, StepRef, StepUnion
from .strategy import (
    StrategyBase, Extract, Assign, Assertion, StrategyRef, StrategyUnion,
    Scope, AssertOperator, StrategyPhase, FailurePolicy,
)
from .timepolicy import TimePolicy, TimeoutPolicy, RecordPolicy, TimePolicyUnion
from .retrypolicy import RetryPolicy
from .scenario import Scenario, Meta, Config, ScenarioRef, Suite, SuiteRef, RunUnion
from .setup import Setup, SetupRef, SetupUnion
from .teardown import Teardown, TeardownRef, TeardownUnion
from .auth import AuthSession


__all__ = [
    # Field
    "Field",
    # states
    "StepState",
    # ref
    "RefBase", "Ref",
    # resource
    "Resource", "Mock", "File", "MockRef", "FileRef", "ResourceUnion",
    # api
    "Api", "ApiRef", "ApiUnion",
    # request
    "Request", "RequestRef", "RequestUnion",
    # step
    "Step", "StepRef", "StepUnion",
    # strategy
    "StrategyBase", "Extract", "Assign", "Assertion",
    "StrategyRef", "StrategyUnion",
    "Scope", "AssertOperator", "StrategyPhase", "FailurePolicy",
    # timepolicy
    "TimePolicy", "TimeoutPolicy", "RecordPolicy", "TimePolicyUnion",
    # retrypolicy
    "RetryPolicy",
    # scenario
    "Scenario", "Meta", "Config",
    "ScenarioRef", "Suite", "SuiteRef", "RunUnion",
    # setup / teardown
    "Setup", "SetupRef", "SetupUnion",
    "Teardown", "TeardownRef", "TeardownUnion",
    # auth
    "AuthSession",
]
