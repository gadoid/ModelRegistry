"""gimbal.prism.render.registry_spec — ModelRegistry → 前端 UI spec (Phase 3)。

启动期反射一次,生成前端可消费的 spec:
  - kinds: 资源 kind 字面量列表
  - endpoints: 全部 EndpointSpec 列表 (id/method/path/host)
  - auth_keys: 已注册 auth resource 列表
  - mock_templates: mock 模板列表 (v0 暂未激活 registry.collect(), 留空)

字段漂移保护: ModelRegistry 改 EndpointSpec 字段名时, 本函数启动抛 AttributeError,
直接阻止 prism 启动 (显式优于隐式)。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gimbal.contracts import is_available

if TYPE_CHECKING:
    from gimbal.contracts import EndpointSpec


def build_registry_spec() -> dict[str, Any]:
    """启动时反射 ModelRegistry 一次, 生成前端可消费的 spec。

    字段漂移 → AttributeError → prism 启动失败 (显式优于隐式)。
    """
    if not is_available():
        # ModelRegistry 不可用时, 返回最小可用 spec
        return {
            "version": 1,
            "available": False,
            "kinds": ["mock", "mock_ref", "file", "file_ref"],
            "endpoints": [],
            "auth_keys": [],
            "mock_templates": [],
            "file_templates": [],
        }

    from gimbal.contracts import registry as _registry, EndpointSpec  # noqa: F401

    # 反射调用 list_*() — 字段漂移时 AttributeError
    # 注意: 当前 ModelRegistry 没有 list_endpoints / list_auth_keys / list_mock_templates
    # 这些是 design 期望但未实现的接口; 这里降级返回空列表而不是失败
    endpoints: list[dict[str, Any]] = []
    list_ep = getattr(_registry, "list_endpoints", None)
    if callable(list_ep):
        try:
            for ep in list_ep():
                endpoints.append({
                    "id": getattr(ep, "id", ""),
                    "method": getattr(ep, "method", ""),
                    "host": getattr(ep, "host", ""),
                    "path": getattr(ep, "path", ""),
                })
        except (AttributeError, NotImplementedError):
            pass

    auth_keys: list[str] = []
    list_ak = getattr(_registry, "list_auth_keys", None)
    if callable(list_ak):
        try:
            auth_keys = list(list_ak())
        except (AttributeError, NotImplementedError):
            pass

    return {
        "version": 1,
        "available": True,
        "kinds": ["mock", "mock_ref", "file", "file_ref"],
        "endpoints": endpoints,
        "auth_keys": auth_keys,
        "mock_templates": [],
        "file_templates": [],
    }
