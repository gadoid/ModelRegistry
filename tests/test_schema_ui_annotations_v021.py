"""v0.2.3 测试: Resource / Step 字段的 UI 注解 + meta 字段完整覆盖。"""
import pytest
from pydantic_core import PydanticUndefined

from gimbal.schema import Mock, File, Step, Api, Request
from gimbal.prism.render import build_ui_spec
from gimbal.schema import Scenario


def test_meta_field_annotations_complete():
    """Meta 11+ 字段全部带 ui 注解。"""
    spec = build_ui_spec(Scenario)
    meta = next(g for g in spec["groups"] if g["id"] == "meta")
    paths = {f["path"] for f in meta["fields"]}
    # 必须覆盖的 11 个 Meta 字段
    expected = {
        "meta.scenarioId", "meta.name", "meta.description", "meta.module",
        "meta.priority", "meta.author", "meta.owner", "meta.tags",
        "meta.version", "meta.expire", "meta.requirementRef",
    }
    assert expected <= paths, f"缺少字段: {expected - paths}"


def test_priority_field_is_select():
    from gimbal.schema import Meta
    f = Meta.model_fields["priority"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "select"
    assert {o["value"] for o in ui["options"]} == {1, 2, 3}


def test_name_field_is_required():
    from gimbal.schema import Meta
    f = Meta.model_fields["name"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["required"] is True
    assert ui["widget"] == "input"


def test_resource_mock_ui_annotations():
    """Mock 字段带 ui 注解 (kind select + image input + portMapping kv-list)。"""
    from gimbal.schema import Mock
    # kind
    k = Mock.model_fields["kind"]
    ui = (k.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "select"
    assert "mock" in [o["value"] for o in ui["options"]]
    # image
    img = Mock.model_fields["image"]
    ui = (img.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "input"
    # portMapping
    pm = Mock.model_fields["portMapping"]
    ui = (pm.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "kv-list"
    assert ui["key_label"] == "host_port"
    assert ui["value_label"] == "container_port"


def test_step_ui_annotations():
    """Step.api / .request / .strategy / .key 带 ui 注解。"""
    from gimbal.schema import Step
    for fname in ("api", "request", "strategy", "key"):
        f = Step.model_fields[fname]
        ui = (f.json_schema_extra or {}).get("ui")
        assert ui is not None, f"Step.{fname} 缺 ui 注解"
        assert "widget" in ui


def test_step_key_is_readonly():
    """Step.key 是 readonly (UI 不能改, builder 注入)。"""
    from gimbal.schema import Step
    f = Step.model_fields["key"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["readonly"] is True


def test_scenario_id_is_readonly():
    """Meta.scenarioId 是 readonly (UI 不能改)。"""
    from gimbal.schema import Meta
    f = Meta.model_fields["scenarioId"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["readonly"] is True


def test_no_ui_metadata_in_model_dump():
    """ui 字典不进 model_dump (只经 json_schema_extra)。"""
    from gimbal.schema import Meta
    m = Meta(name="t")
    d = m.model_dump()
    # 没有任何 ui_* 字段
    assert all(not k.startswith("ui_") for k in d.keys())
    # 也无 ui 字段
    assert "ui" not in d
