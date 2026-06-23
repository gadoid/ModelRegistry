"""gimbal/schema/resource.py — Resource / Mock / File / Refs。

v0.1.1 (Phase 2 续): Resource / Mock / File 加 ui 注解
"""
from __future__ import annotations

from typing import Any, Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from . import Field
from .ref import RefBase


class Resource(BaseModel):
    """资源基类(只 name 一字段)。"""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., ui={"widget": "input", "label": "name", "group": "resource"},
    )


class Mock(Resource):
    """容器镜像 mock。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["mock"] = Field(
        "mock",
        ui={
            "widget": "select", "label": "kind", "group": "resource",
            "options": [
                {"value": "mock", "label": "Mock (容器)"},
                {"value": "mock_ref", "label": "Mock Ref"},
                {"value": "file", "label": "File"},
                {"value": "file_ref", "label": "File Ref"},
            ],
        },
    )
    image: str = Field(
        "nginx:latest",
        ui={"widget": "input", "label": "image", "group": "resource"},
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        ui={"widget": "kv-list", "label": "config", "group": "resource"},
    )
    portMapping: dict[int, int] = Field(
        default_factory=dict,
        ui={"widget": "kv-list", "label": "portMapping", "group": "resource",
            "key_label": "host_port", "value_label": "container_port"},
    )


class File(Resource):
    """文件资源。"""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["file"] = Field(
        "file",
        ui={"widget": "select", "label": "kind", "group": "resource"},
    )
    path: str = Field(
        "", ui={"widget": "input", "label": "path", "group": "resource"},
    )


class MockRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mock_ref"] = "mock_ref"


class FileRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["file_ref"] = "file_ref"


ResourceUnion = Annotated[
    Union[Mock, MockRef, File, FileRef],
    Field(discriminator="kind"),
]


if __name__ == "__main__":
    m = Mock(name="m1", image="nginx:1", config={"x": 1}, portMapping={80: 8080})
    print(f"Mock: {m.name} {m.image} {m.portMapping}")
