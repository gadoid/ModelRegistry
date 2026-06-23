"""gimbal/schema/api.py — Api / ApiRef。"""
from __future__ import annotations

from typing import Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from .ref import RefBase


class Api(BaseModel):
    """单步骤 API 描述。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["api"] = "api"
    service: str = _PydField(..., description="service 名 (从 capture host 推断或 services 表映射)")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = _PydField(
        ..., description="HTTP method",
    )
    path: str = _PydField(..., description="URL 路径")
    headers: dict[str, str] = _PydField(
        default_factory=dict, description="请求头 (含 Authorization 占位)",
    )
    timeout: float = _PydField(30, description="超时秒数")


class ApiRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["api_ref"] = "api_ref"


ApiUnion = Annotated[
    Union[Api, ApiRef],
    _PydField(discriminator="kind"),
]


if __name__ == "__main__":
    api = Api(service="user-service", method="GET", path="/api/users/{id}")
    print(f"Api 测试: service={api.service}, method={api.method}, path={api.path}")
    api_ref = ApiRef(ref="api_ref_1")
    print(f"ApiRef 测试: ref={api_ref.ref}")
