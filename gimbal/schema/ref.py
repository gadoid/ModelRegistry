"""gimbal/schema/ref.py — 所有引用模型的基类 + 通用内联引用。"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field as _PydField, ConfigDict


class RefBase(BaseModel):
    """所有引用模型的基类。

    子类必须:
      1. 用 ``kind`` 字段声明自己的 discriminator(便于 Pydantic 多态反序列化)
      2. 通过 ``ref`` 字段(继承自本类)声明要拉取的 asset ref 字符串
    """
    model_config = ConfigDict(extra="forbid")

    ref: str = _PydField(..., description="asset ref 字符串, 格式 namespace/name:tag 或 namespace/name@digest")


class Ref(RefBase):
    """通用内联引用: 可出现在 dict / list 任意位置的待实例化占位符。"""
    kind: Literal["ref"] = "ref"


if __name__ == "__main__":
    ref = RefBase(ref="test_ref")
    print(f"RefBase 测试: ref={ref.ref}")
    inline = Ref(ref="smoke/order-id-pool:latest")
    print(f"Ref 测试: kind={inline.kind} ref={inline.ref}")
