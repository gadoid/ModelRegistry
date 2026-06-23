"""gimbal.prism.render — 把 Pydantic schema / ModelRegistry 反射成前端可消费的 spec。

公开:
  - walk_fields: 递归遍历 model 字段, 产出 (path, FieldInfo, parent_model)
  - build_ui_spec: 按 group 聚合, 产出 /api/schema/ui-spec JSON
  - build_registry_spec: ModelRegistry → /api/registry/ui-spec JSON
"""
from .walk_model import walk_fields
from .ui_spec import build_ui_spec, GROUP_DEFS
from .registry_spec import build_registry_spec

__all__ = ["walk_fields", "build_ui_spec", "GROUP_DEFS", "build_registry_spec"]
