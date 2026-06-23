"""gimbal/schema/timepolicy.py — TimePolicy 派发 (v0.2.4 加 UI 注解)。"""
from __future__ import annotations

from typing import Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from . import Field


class TimePolicy(BaseModel):
    """时间策略基类。"""
    model_config = ConfigDict(extra="forbid")
    pass


class TimeoutPolicy(TimePolicy):
    """超时模式: 执行器检查每一步是否超时, 超时抛异常。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["timeout"] = Field(
        "timeout",
        ui={"widget": "select", "label": "kind", "group": "timePolicy",
            "options": [
                {"value": "record", "label": "record (记录耗时)"},
                {"value": "timeout", "label": "timeout (超时检查)"},
            ]},
    )
    seconds: int = Field(
        60,
        ui={"widget": "number", "label": "seconds", "min": 1, "max": 3600,
            "unit": "秒", "group": "timePolicy",
            "show_if": {"path": "config.timePolicy.kind", "equals": "timeout"}},
    )


class RecordPolicy(TimePolicy):
    """记录模式: 不检查超时, 但记录实际耗时到运行结果。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["record"] = Field(
        "record",
        ui={"widget": "select", "label": "kind", "group": "timePolicy"},
    )


TimePolicyUnion = Annotated[
    Union[TimeoutPolicy, RecordPolicy],
    _PydField(discriminator="kind"),
]


if __name__ == "__main__":
    t = TimeoutPolicy(seconds=60)
    print(f"TimeoutPolicy: kind={t.kind}, seconds={t.seconds}")
