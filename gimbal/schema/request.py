"""gimbal/schema/request.py — Request / RequestRef。

v0.1 新增 ``params`` 字段(原 design 期望 ``query → params``)。
"""
from __future__ import annotations

from typing import Any, Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from .ref import RefBase


class Request(BaseModel):
    """单步骤请求体 (含 query params 与 body)。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["request"] = "request"
    body: dict[str, Any] = _PydField(default_factory=dict, description="请求体 dict")
    params: dict[str, str] = _PydField(
        default_factory=dict, description="query string 参数 (v0.1 补)",
    )


class RequestRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["request_ref"] = "request_ref"


RequestUnion = Annotated[
    Union[Request, RequestRef],
    _PydField(discriminator="kind"),
]


if __name__ == "__main__":
    r = Request(body={"userId": 123}, params={"q": "abc"})
    print(f"Request 测试: body={r.body}, params={r.params}")
