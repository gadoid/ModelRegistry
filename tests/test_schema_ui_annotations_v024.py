"""v0.2.4 测试: Config 子结构 + AuthSession UI 注解。"""
from gimbal.schema import (
    Scenario, Meta, Config, AuthSession,
    TimeoutPolicy, RecordPolicy, RetryPolicy,
)
from gimbal.prism.render import build_ui_spec


def test_time_policy_kind_select_with_options():
    """TimePolicy.kind 是 select, 选项含 record / timeout。"""
    f = TimeoutPolicy.model_fields["kind"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "select"
    values = {o["value"] for o in ui["options"]}
    assert values == {"record", "timeout"}


def test_time_policy_seconds_conditional():
    """TimePolicy.seconds 用 show_if 仅在 kind=timeout 时显示。"""
    f = TimeoutPolicy.model_fields["seconds"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "number"
    assert ui["show_if"] == {"path": "config.timePolicy.kind", "equals": "timeout"}


def test_retry_policy_annotations():
    """RetryPolicy 3 字段带 ui 注解 + show_if 联动。"""
    for fname in ("maxAttempts", "backoffSeconds", "retryOn"):
        f = RetryPolicy.model_fields[fname]
        ui = (f.json_schema_extra or {}).get("ui")
        assert ui is not None
        assert ui["show_if"]["path"] == "config.retry.kind"


def test_auth_session_all_fields_annotated():
    """AuthSession 7 字段带 ui 注解。"""
    spec = build_ui_spec(Scenario)
    users_group = next(g for g in spec["groups"] if g["id"] == "users")
    paths = {f["path"] for f in users_group["fields"]}
    expected = {
        "config.users.url", "config.users.username", "config.users.password",
        "config.users.expires_in", "config.users.token",
        "config.users.token_type", "config.users.expires_at",
    }
    assert expected <= paths, f"缺少字段: {expected - paths}"


def test_password_widget_is_password_type():
    """AuthSession.password 用 password widget (前端应遮罩)。"""
    f = AuthSession.model_fields["password"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["widget"] == "password"


def test_token_is_readonly():
    """AuthSession.token 是 readonly (UI 不能改, 认证后自动填充)。"""
    f = AuthSession.model_fields["token"]
    ui = (f.json_schema_extra or {}).get("ui")
    assert ui["readonly"] is True


def test_groups_in_ui_spec():
    """ui_spec 输出应至少含 5 个 group: meta / config / timePolicy / retry / users。"""
    spec = build_ui_spec(Scenario)
    group_ids = {g["id"] for g in spec["groups"]}
    assert "meta" in group_ids
    assert "config" in group_ids
    assert "timePolicy" in group_ids
    assert "retry" in group_ids
    assert "users" in group_ids


def test_dot_paths_include_config_subfields():
    """/api/schema/dot-paths 应包含嵌套字段路径。"""
    from gimbal.prism.render import walk_fields
    paths = [p for p, _fi, _m in walk_fields(Scenario)]
    assert "config.timePolicy.kind" in paths
    assert "config.timePolicy.seconds" in paths
    assert "config.retry.maxAttempts" in paths
    # 嵌套 BaseModel 应被 walk 进 (Config.users -> AuthSession)
    assert "config.users.url" in paths
    assert "config.users.password" in paths
