"""gimbal.contracts — ModelRegistry 引入层 (Phase 3)。

加载优先级:
  1. 已装 model-registry-local (通过 `pip install -e ".[model-registry]"`), 直接 `from ModelRegistry import ...`
  2. 环境变量 ``GIMBAL_MODEL_REGISTRY_PATH`` 指向 D:/M/ModelRegistry 根目录, sys.path 注入
  3. 全部失败 → ``is_available() == False``, 其他 gimbal 子模块正常使用, 仅 ModelRegistry 相关功能降级

导出符号 (在 is_available() == True 时):
  - registry: 进程级单例 (从 ModelRegistry.core)
  - EndpointKey: 索引键 dataclass
  - EndpointSpec: endpoint 契约 (frozen, @final)
  - MockHook / ValidateHook / BuildRequestHook: hook Protocols
  - BootstrapError: warm() 聚合错误类
  - is_available: bool 探测函数
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


__all__ = [
    "registry", "BootstrapError", "EndpointSpec", "EndpointKey",
    "MockHook", "ValidateHook", "BuildRequestHook",
    "is_available",
]


# ────────────────────────────────────────────────────────────────────────────
# 内部: 尝试加载
# ────────────────────────────────────────────────────────────────────────────


def _try_load() -> bool:
    """尝试把 ModelRegistry 加进 sys.path 并 import; 成功返回 True。"""
    # 路径 1: 已装 model-registry-local
    try:
        from ModelRegistry import registry as _registry, BootstrapError as _BErr  # type: ignore
        from ModelRegistry.core import EndpointKey as _EKey  # type: ignore
        from ModelRegistry.spec import (  # type: ignore
            EndpointSpec as _ESpec,
            MockHook as _MHook,
            ValidateHook as _VHook,
            BuildRequestHook as _BRHook,
        )
        globals().update({
            "registry": _registry,
            "BootstrapError": _BErr,
            "EndpointSpec": _ESpec,
            "EndpointKey": _EKey,
            "MockHook": _MHook,
            "ValidateHook": _VHook,
            "BuildRequestHook": _BRHook,
        })
        return True
    except ImportError:
        pass

    # 路径 2: 环境变量指定 D:/M/ModelRegistry 根目录
    mr_root = os.environ.get("GIMBAL_MODEL_REGISTRY_PATH")
    if mr_root:
        p = Path(mr_root).expanduser().resolve()
        if (p / "ModelRegistry" / "__init__.py").exists():
            sys.path.insert(0, str(p))
            try:
                from ModelRegistry import registry as _registry, BootstrapError as _BErr  # type: ignore
                from ModelRegistry.core import EndpointKey as _EKey  # type: ignore
                from ModelRegistry.spec import (  # type: ignore
                    EndpointSpec as _ESpec,
                    MockHook as _MHook,
                    ValidateHook as _VHook,
                    BuildRequestHook as _BRHook,
                )
                globals().update({
                    "registry": _registry,
                    "BootstrapError": _BErr,
                    "EndpointSpec": _ESpec,
                    "EndpointKey": _EKey,
                    "MockHook": _MHook,
                    "ValidateHook": _VHook,
                    "BuildRequestHook": _BRHook,
                })
                return True
            except ImportError:
                # 注入失败, 撤回
                try:
                    sys.path.remove(str(p))
                except ValueError:
                    pass

    return False


# 加载 + 标记可用性
_AVAILABLE = _try_load()


def is_available() -> bool:
    """ModelRegistry 是否可用 (已装 或 环境变量路径正确)。"""
    return _AVAILABLE
