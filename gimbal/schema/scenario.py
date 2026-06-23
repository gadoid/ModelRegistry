"""gimbal/schema/scenario.py — Scenario / Meta / Config (顶层 model)。

v0.1 已合 (M2.5): Meta.name min_length=1 + _name_not_blank validator
v0.1 加 UI 注解 (Phase 2): Meta 字段用 `Field(..., ui={...})` 标记
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Literal, Annotated, Union

from pydantic import BaseModel, ConfigDict, field_validator

# 用包级 Field(支持 ui=) 替换 pydantic 原生
from . import Field
from .resource import ResourceUnion
from .ref import RefBase
from .step import StepUnion
from .timepolicy import TimePolicyUnion, RecordPolicy
from .retrypolicy import RetryPolicy
from .setup import SetupUnion
from .teardown import TeardownUnion
from .auth import AuthSession


class Meta(BaseModel):
    """用例元信息。

    所有字段带 ``ui=`` 注解, 供 /api/schema/ui-spec 反射生成前端表单。
    """
    model_config = ConfigDict(extra="forbid")

    scenarioId: str = Field(
        "sc_new",
        ui={"widget": "input", "label": "scenarioId", "readonly": True, "group": "meta"},
    )
    name: str = Field(
        "",
        min_length=1,
        ui={
            "widget": "input", "label": "用例名", "required": True,
            "placeholder": "请输入用例名", "group": "meta",
            "help": "必填, 空字符串/纯空白字符串会被 schema 拒绝",
        },
    )
    description: str = Field(
        "",
        ui={"widget": "textarea", "label": "用例描述", "rows": 2, "group": "meta"},
    )
    module: str = Field(
        "default",
        ui={"widget": "input", "label": "module", "group": "meta"},
    )
    priority: int = Field(
        1,
        ui={
            "widget": "select", "label": "优先级", "group": "meta",
            "options": [
                {"value": 1, "label": "1 (最高)"},
                {"value": 2, "label": "2"},
                {"value": 3, "label": "3"},
            ],
        },
    )
    author: str = Field(
        "prism", ui={"widget": "input", "label": "author", "group": "meta"},
    )
    owner: str = Field(
        "prism", ui={"widget": "input", "label": "owner", "group": "meta"},
    )
    tags: list[str] = Field(
        default_factory=lambda: ["smoke"],
        ui={
            "widget": "tags", "label": "tags", "group": "meta",
            "hint": "回车/逗号添加 · 拖动重排",
        },
    )
    version: str = Field(
        "1.0.0", ui={"widget": "input", "label": "version", "group": "meta"},
    )
    createTime: datetime = Field(
        default_factory=datetime.now,
        ui={"widget": "input", "label": "createTime", "readonly": True, "group": "meta"},
    )
    expire: bool = Field(
        False, ui={"widget": "toggle", "label": "expire", "group": "meta"},
    )
    requirementRef: list[RefBase] = Field(
        default_factory=list,
        ui={
            "widget": "tags", "label": "requirementRef", "group": "meta",
            "hint": "需求 ID, 如 REQ-123",
        },
    )

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        """docx §7.3: strip 后必须非空 (拒绝 ``"   "`` 这类纯空白输入)。"""
        if not v or not v.strip():
            raise ValueError("meta.name must not be blank")
        return v


class Config(BaseModel):
    """用例执行配置。

    含 services / users / timePolicy / retry 4 个子结构。
    """
    model_config = ConfigDict(extra="forbid")

    setup: list[SetupUnion] = Field(
        default_factory=list,
        ui={"widget": "step-list", "label": "setup", "group": "config"},
    )
    teardown: list[TeardownUnion] = Field(
        default_factory=list,
        ui={"widget": "step-list", "label": "teardown", "group": "config"},
    )
    services: dict[str, str] = Field(
        default_factory=dict,
        ui={
            "widget": "kv-list", "label": "services", "group": "config",
            "key_label": "service", "value_label": "URL",
            "hint": "service 名 -> URL, 如 tidb-test-service=https://fin-tidb.21eflag.com/",
        },
    )
    users: dict[str, AuthSession] = Field(
        default_factory=dict,
        ui={"widget": "user-list", "label": "users", "group": "config"},
    )
    timePolicy: TimePolicyUnion = Field(
        default_factory=RecordPolicy,
        ui={"widget": "time-policy", "label": "timePolicy", "group": "config"},
    )
    retry: Optional[RetryPolicy] = Field(
        None,
        ui={"widget": "retry-policy", "label": "retry", "group": "config"},
    )


class Scenario(BaseModel):
    """用例数据模型。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["scenario"] = "scenario"
    scenarioId: str = Field(..., description="场景/用例 ID, 前缀为 sc")
    meta: Meta = Field(..., description="用例元信息")
    config: Config = Field(..., description="用例执行配置")
    resource: dict[str, ResourceUnion] = Field(
        default_factory=dict, description="用例需要的资源",
    )
    steps: list[StepUnion] = Field(
        default_factory=list, description="具体执行步骤",
    )


class ScenarioRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["scenario_ref"] = "scenario_ref"


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["suite"] = "suite"
    suite: list[Scenario] = Field(..., description="scenario 集合 (暂时用列表)")


class SuiteRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["suite_ref"] = "suite_ref"


RunUnion = Annotated[
    Union[Scenario, ScenarioRef, Suite, SuiteRef],
    Field(discriminator="kind"),
]
