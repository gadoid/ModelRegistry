"""gimbal/schema/request.py — Request / RequestRef。

v0.1 新增 ``params`` 字段(原 design 期望 ``query → params``)。
"""
from __future__ import annotations

from typing import Any, Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from .ref import RefBase


class Request(BaseModel):
    """单步骤请求体 (含 query params 与 body)。

    v0.5.9 修复: ``body`` 由 ``dict[str, Any]`` 放宽为 ``Any``。
    现实 API (如批量发票提交) 的请求体常为 JSON 数组, 而非对象。
    schema 强制 dict 会让 ``POST /api/draft/{sid}/yaml`` 在
    ``req_override.body`` 为数组时抛 422 ``Input should be a valid dictionary``,
    与 ``本地 JSON 视图``(纯客户端)行为不一致 — 用户体验割裂。
    放宽后 ``Scenario.model_validate`` 不再误伤, 真实执行期按 HTTP body 透传。
    """
    model_config = ConfigDict(extra="forbid")

    kind: Literal["request"] = "request"
    body: Any = _PydField(
        default_factory=dict,
        description="请求体 (任意 JSON: dict / list / str / number / null)",
    )
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
