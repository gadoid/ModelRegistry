"""v0.2 留位: 痛点 #6 的旧测试已不再适用 (lifespan 替代 _loop)。

痛点 #6 描述: ``_broadcast`` 在 ``_loop is None`` 时必须发出 warning。
v0 改造后, 整个 ``_loop`` / ``_broadcast`` 机制被 lifespan + SSE 替代,
``gimbal.prism.server`` 没有这些全局单例。

本测试仅留作历史归档 (标记 v0.2 deprecated), 跑时会 skip。
"""
import pytest


@pytest.mark.skip(reason="v0 痛点 #11: lifespan 替代 _loop 单例, 旧测试不再适用")
def test_broadcast_logs_warning_when_loop_not_ready():
    """痛点 #6 旧逻辑: _loop is None 时 _broadcast 发 WARNING。"""
    pass


@pytest.mark.skip(reason="v0 痛点 #11: lifespan 替代 _loop 单例, 旧测试不再适用")
def test_broadcast_silent_when_loop_ready():
    """痛点 #6 旧逻辑: _loop 就绪时不产生 warning。"""
    pass
