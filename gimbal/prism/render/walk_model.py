"""gimbal.prism.render.walk_model — 递归遍历 Pydantic model。

产出 ``(dot_path, FieldInfo, parent_model)`` 三元组, 给 ui_spec 用。
"""
from __future__ import annotations

import typing
from typing import Any, Iterator, Type

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _is_base_model(annotation: Any) -> bool:
    """判断 annotation 是否是 BaseModel 子类(处理 Optional / Union 包装)。"""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    origin = typing.get_origin(annotation)
    if origin is None:
        return False
    for arg in typing.get_args(annotation):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return True
    return False


def walk_fields(
    root_model: Type[BaseModel],
    prefix: str = "",
    parent_model: Type[BaseModel] | None = None,
) -> Iterator[tuple[str, FieldInfo, Type[BaseModel]]]:
    """递归遍历 root_model 的所有字段, 产出 (dot-path, field_info, parent_model)。

    - 嵌套 model: 进入嵌套, prefix 加 "."
    - list[X] / dict[str, X] / Union: 不递归(留给前端单独处理)
    - 字段本身永远 yield 一次, 再决定是否深入
    """
    if parent_model is None:
        parent_model = root_model

    for name, field_info in parent_model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        yield path, field_info, parent_model

        annotation = field_info.annotation
        if _is_base_model(annotation):
            # 找到最具体的 BaseModel 子类去递归
            for arg in typing.get_args(annotation) or [annotation]:
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    yield from walk_fields(arg, prefix=path, parent_model=arg)
                    break
            else:
                # 裸 BaseModel
                yield from walk_fields(annotation, prefix=path, parent_model=annotation)
