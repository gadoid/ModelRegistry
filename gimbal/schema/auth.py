"""gimbal/schema/auth.py — AuthSession (读写一体, docx §7.3)。

v0.2.4: AuthSession 加 ui 注解, 给 Config.users 渲染用
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pydantic import BaseModel, ConfigDict, Field as _PydField

from . import Field


class AuthSession(BaseModel):
    """认证会话(读写一体)。

    认证前: 填写 url/username/password/expires_in
    认证后: token/expires_at 自动填充
    """
    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        "",
        ui={"widget": "input", "label": "url", "group": "users",
            "placeholder": "https://api.example.com/auth"},
    )
    username: str = Field(
        "",
        ui={"widget": "input", "label": "username", "group": "users"},
    )
    password: str = Field(
        "",
        ui={"widget": "password", "label": "password", "group": "users",
            "hint": "默认写 <REDACTED>; confirm 后才落明文"},
    )

    expires_in: int | None = Field(
        None,
        ui={"widget": "number", "label": "expires_in (s)", "min": 60, "max": 86400 * 30,
            "group": "users"},
    )
    token: str | None = Field(
        None,
        ui={"widget": "input", "label": "token", "group": "users", "readonly": True,
            "hint": "认证后自动填充"},
    )
    token_type: str = Field(
        "Bearer",
        ui={"widget": "input", "label": "token_type", "group": "users"},
    )
    expires_at: datetime | None = Field(
        None,
        ui={"widget": "input", "label": "expires_at", "group": "users", "readonly": True},
    )

    # ── 计算属性 ───────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        if not self.token:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    @property
    def should_refresh(self) -> bool:
        if not self.expires_at:
            return False
        threshold = datetime.utcnow() + timedelta(minutes=5)
        return threshold > self.expires_at

    @property
    def auth_header(self) -> str | None:
        if not self.token:
            return None
        return f"{self.token_type} {self.token}"

    @property
    def remaining_seconds(self) -> int | None:
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    # ── 方法 ───────────────────────────────────────────────

    def apply_token(self, token: str, expires_in: int | None = None) -> "AuthSession":
        self.token = token
        if expires_in is not None:
            self.expires_in = expires_in
        if self.expires_in:
            self.expires_at = datetime.utcnow() + timedelta(seconds=self.expires_in)
        return self

    def clear_token(self) -> "AuthSession":
        self.token = None
        self.expires_at = None
        return self

    def is_same_credential(self, other: "AuthSession") -> bool:
        return (
            self.url == other.url
            and self.username == other.username
            and self.password == other.password
        )

    @classmethod
    def from_dict(cls, data: dict) -> "AuthSession":
        return cls(**data)
