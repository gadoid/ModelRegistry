"""gimbal/schema/teardown.py — Teardown / TeardownRef。"""
from __future__ import annotations

from typing import Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from .ref import RefBase


class Teardown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["teardown"] = "teardown"


class TeardownRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["teardown_ref"] = "teardown_ref"


TeardownUnion = Annotated[
    Union[Teardown, TeardownRef],
    _PydField(discriminator="kind"),
]
