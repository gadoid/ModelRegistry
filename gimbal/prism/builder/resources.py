"""gimbal.prism.builder.resources — ResourceDraft → schema.ResourceUnion dispatch.

The 4 resource kinds (mock / mock_ref / file / file_ref) are mapped to
their respective factory functions via a dispatch table (痛点 12).
"""
from __future__ import annotations

from typing import Any

from gimbal.prism.builder.drafts import ResourceDraft
from gimbal.schema import (
    File,
    FileRef,
    Mock,
    MockRef,
    ResourceUnion,
)

# 痛点 12: 资源 kind 派发表(原 if/elif 串行收敛)
_RESOURCE_KIND_DISPATCH: dict[str, Any] = {}


def _make_mock(rd: ResourceDraft, name: str) -> ResourceUnion:
    return Mock(
        kind="mock", name=name, image=rd.image or "nginx:latest",
        config=rd.config or {},
        portMapping={int(k): int(v) for k, v in (rd.port_mapping or {}).items()},
    )


def _make_mock_ref(rd: ResourceDraft, name: str) -> ResourceUnion:
    return MockRef(ref=rd.ref)


def _make_file(rd: ResourceDraft, name: str) -> ResourceUnion:
    return File(kind="file", name=name, path=rd.path or "")


def _make_file_ref(rd: ResourceDraft, name: str) -> ResourceUnion:
    return FileRef(ref=rd.ref)


_RESOURCE_KIND_DISPATCH["mock"] = _make_mock
_RESOURCE_KIND_DISPATCH["mock_ref"] = _make_mock_ref
_RESOURCE_KIND_DISPATCH["file"] = _make_file
_RESOURCE_KIND_DISPATCH["file_ref"] = _make_file_ref


def build_resource(rd: ResourceDraft) -> ResourceUnion:
    """按 rd.kind 派发表构造 schema.ResourceUnion 之一。

    痛点 12 (Phase 1.3): 替代 if/elif 串行, 便于加新 kind 不用改 builder。
    """
    name = rd.name
    if rd.kind not in _RESOURCE_KIND_DISPATCH:
        _RESOURCE_KIND_DISPATCH.setdefault("__kinds__", set()).add(rd.kind)
        raise ValueError(f"未知 resource kind: {rd.kind!r}; 支持: mock/mock_ref/file/file_ref")
    return _RESOURCE_KIND_DISPATCH[rd.kind](rd, name)


__all__ = ["build_resource"]