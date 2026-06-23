"""Fix #5: builder 必须做 password redaction (docx §7.3 精神)。

原版只 server.py 脱敏;CLI 走的 convert-scenario / build 路径不经 server,
会写明文 password 到导出文件。修复后:``AuthDraft.confirm_password=False``
时,builder 输出的 ``config.users.<k>.password`` 必为 ``<REDACTED>``。
"""
import pytest

from gimbal.prism.builder import (
    AuthDraft,
    ScenarioDraft,
    StepDraft,
    build_scenario,
)


def _empty_draft() -> ScenarioDraft:
    return ScenarioDraft(
        scenario_id="sc_x", name="t", module="default",
        users={
            "alice": AuthDraft(
                url="https://api.example.com/auth",
                username="alice",
                password="super-secret",
                expires_in=7200,
                token_type="Bearer",
            ),
        },
    )


def test_authdraft_has_confirm_password_default_false():
    """``AuthDraft`` 暴露 ``confirm_password`` 字段,默认 False。"""
    a = AuthDraft(username="u", password="p")
    assert a.confirm_password is False


def test_builder_redacts_password_by_default():
    """未确认时, builder 输出的 password 应为 ``<REDACTED>``, 不是明文。"""
    out = build_scenario(_empty_draft())
    pw = out["config"]["users"]["alice"]["password"]
    assert pw == "<REDACTED>"
    assert "super-secret" not in str(out)  # 明文不出现在任何字段


def test_builder_preserves_password_when_confirmed():
    """显式 ``confirm_password=True`` 时, password 应原样落地。"""
    draft = _empty_draft()
    draft.users["alice"].confirm_password = True
    out = build_scenario(draft)
    assert out["config"]["users"]["alice"]["password"] == "super-secret"


def test_builder_keeps_empty_password_as_empty():
    """password 为空时, redaction 也不能把它写成 ``<REDACTED>``。"""
    draft = _empty_draft()
    draft.users["alice"].password = ""
    out = build_scenario(draft)
    assert out["config"]["users"]["alice"]["password"] == ""


def test_builder_idempotent_redaction():
    """已脱敏的 password 再次走 builder, 应保持 ``<REDACTED>`` (不被双层覆盖)。"""
    draft = _empty_draft()
    draft.users["alice"].password = "<REDACTED>"
    out = build_scenario(draft)
    assert out["config"]["users"]["alice"]["password"] == "<REDACTED>"
