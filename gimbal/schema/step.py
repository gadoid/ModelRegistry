"""gimbal/schema/step.py — Step / StepRef。

v0.1.1: Step 加 ui 注解
"""
from __future__ import annotations

from typing import Optional, Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from . import Field
from .strategy import StrategyUnion
from .ref import RefBase
from .api import ApiUnion
from .request import RequestUnion


class Step(BaseModel):
    """单步骤数据模型。

    v0.1 已合 (M2.5): ``key: Optional[str]`` 字段
    """
    model_config = ConfigDict(extra="forbid")

    kind: Literal["step"] = "step"
    name: Optional[str] = Field(
        None,
        ui={"widget": "input", "label": "step name", "group": "steps"},
    )
    api: ApiUnion = Field(
        ...,
        ui={"widget": "api-block", "label": "api", "group": "steps"},
    )
    request: RequestUnion = Field(
        ...,
        ui={"widget": "request-block", "label": "request", "group": "steps"},
    )
    strategy: list[StrategyUnion] = Field(
        default_factory=list,
        ui={"widget": "strategy-list", "label": "strategy", "group": "steps"},
    )
    key: Optional[str] = Field(
        default=None,
        ui={"widget": "input", "label": "step key", "readonly": True, "group": "steps"},
    )


class StepRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["step_ref"] = "step_ref"


StepUnion = Annotated[
    Union[Step, StepRef],
    Field(discriminator="kind"),
]
