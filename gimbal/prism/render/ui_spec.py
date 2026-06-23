"""gimbal.prism.render.ui_spec — 把 schema + ui 注解 反射为前端 JSON。

输出 ``/api/schema/ui-spec`` 的结构::

    {
      "version": 1,
      "groups": [
        {"id": "meta", "label": "用例元信息", "icon": "info-circle", "fields": [...]},
        ...
      ]
    }
"""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from .walk_model import walk_fields


GROUP_DEFS: dict[str, tuple[str, str]] = {
    # group id -> (label, icon)
    "meta": ("用例元信息", "info-circle"),
    "config": ("用例配置", "settings-2"),
    "timePolicy": ("Time Policy", "clock"),
    "retry": ("Retry", "refresh"),
    "services": ("Services", "server"),
    "users": ("Users", "users"),
    "resource": ("资源", "box"),
    "steps": ("Steps", "list-check"),
    "default": ("其他", "settings"),
}


def build_ui_spec(root_model: Type[BaseModel]) -> dict[str, Any]:
    """遍历 root_model 的所有字段, 按 group 聚合输出。"""
    groups: dict[str, dict[str, Any]] = {}

    for path, field_info, _parent in walk_fields(root_model):
        # 提取 ui 注解
        extra = field_info.json_schema_extra
        if not extra or not isinstance(extra, dict):
            continue
        ui = extra.get("ui")
        if not ui:
            continue

        group_id = ui.get("group", "default")
        if group_id not in groups:
            label, icon = GROUP_DEFS.get(group_id, (group_id.title(), "settings"))
            groups[group_id] = {
                "id": group_id,
                "label": label,
                "icon": icon,
                "fields": [],
            }

        groups[group_id]["fields"].append({
            "path": path,
            "widget": ui.get("widget", "input"),
            "label": ui.get("label", _camel_to_label(path.split(".")[-1])),
            "required": ui.get("required", False),
            "placeholder": ui.get("placeholder"),
            "help": ui.get("help"),
            "options": ui.get("options"),
            "options_from": ui.get("options_from"),
            "min": ui.get("min"),
            "max": ui.get("max"),
            "unit": ui.get("unit"),
            "show_if": ui.get("show_if"),
            "rows": ui.get("rows"),
            "hint": ui.get("hint"),
            "readonly": ui.get("readonly", False),
            "key_label": ui.get("key_label"),
            "value_label": ui.get("value_label"),
            "default": _extract_default(field_info),
        })

    # 按 GROUP_DEFS 顺序排
    ordered: list[dict[str, Any]] = []
    for gid in GROUP_DEFS:
        if gid in groups:
            ordered.append(groups[gid])
    for gid, g in groups.items():
        if gid not in GROUP_DEFS:
            ordered.append(g)

    return {"version": 1, "groups": ordered}


def _camel_to_label(name: str) -> str:
    """camelCase / snake_case → Title Case。"""
    s = name.replace("_", " ")
    out: list[str] = []
    for i, ch in enumerate(s):
        if i > 0 and ch.isupper() and s[i - 1].islower():
            out.append(" ")
        out.append(ch)
    return "".join(out).title()


def _extract_default(field_info: FieldInfo) -> Any:
    if field_info.default is not PydanticUndefined:
        return field_info.default
    if field_info.default_factory is not None:
        try:
            return field_info.default_factory()
        except Exception:  # noqa: BLE001
            return None
    return None
