"""gimbal/schema/setup.py — Setup / SetupRef。"""
from __future__ import annotations

from typing import Literal, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field as _PydField

from .ref import RefBase


class Setup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["setup"] = "setup"


class SetupRef(RefBase):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["setup_ref"] = "setup_ref"


SetupUnion = Annotated[
    Union[Setup, SetupRef],
    _PydField(discriminator="kind"),
]
