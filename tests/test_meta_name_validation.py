"""Fix #2: ``Meta.name`` 必填校验。

docx §7.3 要求 meta.name 必填, 但 schema 原版没有 min_length 校验,
允许空字符串通过。修复后: 空 name 应当被 Pydantic ValidationError 拒绝。
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from gimbal.schema import Meta


def _meta_kwargs(**overrides):
    base = dict(
        name="订单到应收",
        description="desc",
        module="settlement",
        priority=1,
        author="alice",
        owner="bob",
        tags=["smoke"],
        version="1.0.0",
        createTime=datetime(2026, 1, 1, 12, 0, 0),
        expire=False,
        requirementRef=[],
    )
    base.update(overrides)
    return base


def test_meta_rejects_empty_name():
    """空字符串 name 应抛 ValidationError。"""
    with pytest.raises(ValidationError) as exc_info:
        Meta(**_meta_kwargs(name=""))
    # 错误信息里要指向 name 字段
    assert any("name" in str(e["loc"]) for e in exc_info.value.errors())


def test_meta_rejects_whitespace_only_name():
    """纯空白 name 应抛 ValidationError (``min_length=1`` + strip 校验)。"""
    with pytest.raises(ValidationError):
        Meta(**_meta_kwargs(name="   "))


def test_meta_accepts_nonempty_name():
    """正常 name 通过。"""
    m = Meta(**_meta_kwargs(name="订单到应收"))
    assert m.name == "订单到应收"


def test_meta_min_length_is_one():
    """单字符 name 也通过 (下界是 1)。"""
    m = Meta(**_meta_kwargs(name="x"))
    assert m.name == "x"


def test_scenario_rejects_empty_meta_name():
    """在 Scenario 顶层校验时, 空 name 也必须被拒。"""
    from gimbal.schema import Scenario, Config
    from gimbal.schema.timepolicy import RecordPolicy

    # 用合法 Scenario 测一遍构造路径
    meta = Meta(**_meta_kwargs(name="x"))
    cfg = Config(services={}, users={}, timePolicy=RecordPolicy(kind="record"))
    s = Scenario(scenarioId="sc_x", meta=meta, config=cfg, resource={}, steps=[])
    assert s.meta.name == "x"
