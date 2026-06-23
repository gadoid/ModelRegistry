"""gimbal/schema/retrypolicy.py — RetryPolicy (v0.2.4 加 UI 注解)。"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field as _PydField

from . import Field


class RetryPolicy(BaseModel):
    """重试策略配置。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["retry_policy"] = "retry_policy"
    maxAttempts: int = Field(
        3,
        ui={"widget": "number", "label": "maxAttempts", "min": 1, "max": 10,
            "group": "retry",
            "show_if": {"path": "config.retry.kind", "equals": "retry_policy"}},
    )
    backoffSeconds: float = Field(
        20.0,
        ui={"widget": "number", "label": "backoffSeconds", "min": 0, "max": 600,
            "unit": "秒", "group": "retry",
            "show_if": {"path": "config.retry.kind", "equals": "retry_policy"}},
    )
    retryOn: list[str] = Field(
        default_factory=lambda: ["500", "502", "503", "504"],
        ui={"widget": "tags", "label": "retryOn", "group": "retry",
            "show_if": {"path": "config.retry.kind", "equals": "retry_policy"}},
    )


if __name__ == "__main__":
    r = RetryPolicy(maxAttempts=3, backoffSeconds=30, retryOn=["500", "502"])
    print(f"RetryPolicy: max={r.maxAttempts}, retryOn={r.retryOn}")
