"""GIMBAL ModelRegistry — 契约模型仓库(子系统)。

本包独立于 ``gimbal`` 主包,被 scenario 加载器与 mock server **按需消费**。
顶层只 re-export 单例 ``registry``,**不 import 任何子包**——保证"导入
ModelRegistry 不会破坏任何东西"的零侵入承诺(A.5 验证阶段的可观察事实)。
"""
from .core import BootstrapError, registry

__all__ = ["registry", "BootstrapError"]
