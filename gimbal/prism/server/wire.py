"""gimbal.prism.server.wire — Pydantic wire forms for HTTP API.

DraftIn and UserIn live in gimbal.prism.state (architectural: they are
draft state shapes, not HTTP payload shapes). This module re-exports
them for HTTP-layer convenience plus the server-specific ExportIn.
"""
from __future__ import annotations

from typing import Optional

from gimbal.prism.state import DraftIn, UserIn


class ExportIn(DraftIn):
    fmt: str = "yaml"
    output_path: Optional[str] = None


__all__ = ["DraftIn", "UserIn", "ExportIn"]