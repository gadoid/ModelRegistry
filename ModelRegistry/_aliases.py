"""service 名 → 合法 Python 目录名 的反向映射。

本表是 service 命名不一致时的唯一兜底。任何 service 名变更,
先改这里(而不是改目录名 + 所有 scenario)。

约定(主路径):service 名本身就是合法 Python 标识符(字母数字下划线、
不以数字开头、不是关键字)→ 直接用作目录名。

兜底(辅路径):service 名含连字符、点、数字开头等 Python 标识符不
允许的字符 → 在 SERVICE_ALIASES 中显式声明映射。

维护规则:
  1. 仅在 service 名不符合 Python 包名规范时,才在 SERVICE_ALIASES 加一行
  2. value 必须是合法 Python 包名(以供 importlib.import_module 使用)
  3. 修改本表前请确认:scenario 侧 service 字段未改、目录名未改 —— 本表
     是连接"真实 service 标识"与"Python 包名"的唯一桥梁
"""
from __future__ import annotations

import keyword

# 集中维护的 alias 表(按 service 名字母序)
# 键:真实 service 标识(可能含连字符等)
# 值:合法 Python 包名(目录名 = import 路径的最后一段)
SERVICE_ALIASES: dict[str, str] = {
    # "tidb-test-service": "tidb_test_service",  # 示例:连字符 → 下划线
    # "3pl-service": "three_pl_service",        # 示例:数字开头走 alias
}


def resolve_dir_name(service: str) -> str:
    """解析 service 名 → 目录名(可作 import 路径最后一段)。

    解析规则(按优先级):
      1. 是合法 Python 标识符(且不是关键字)→ 直接返回
      2. 在 SERVICE_ALIASES 中 → 返回 alias
      3. 都不行 → fail-fast 抛 ValueError

    Args:
        service: scenario 中引用的 service 标识

    Returns:
        合法 Python 包名,可拼到 ``ModelRegistry.`` 之后作 import 路径

    Raises:
        ValueError: service 名不符合 Python 包名规范,且不在 alias 表中
    """
    if not isinstance(service, str) or not service:
        raise ValueError(
            f"[ModelRegistry] service 名必须是非空字符串,实际 {type(service).__name__}: {service!r}"
        )
    if service.isidentifier() and not keyword.iskeyword(service):
        return service
    if service in SERVICE_ALIASES:
        alias = SERVICE_ALIASES[service]
        if not alias.isidentifier() or keyword.iskeyword(alias):
            raise ValueError(
                f"[ModelRegistry] SERVICE_ALIASES[{service!r}] = {alias!r} 不是合法 Python 包名。"
                f"alias 值必须满足 isidentifier() 且不是 Python 关键字。"
            )
        return alias
    raise ValueError(
        f"[ModelRegistry] service 名 {service!r} 不符合 Python 包名规范,"
        f"也不在 SERVICE_ALIASES 中。请在 ModelRegistry/_aliases.py 添加映射后重试。\n"
        f"  提示:连字符用下划线替代(如 'tidb-test-service' → 'tidb_test_service'),"
        f"数字开头用英文单词替代(如 '3pl-service' → 'three_pl_service')。"
    )
