"""Registry 核心:collect / resolve / warm,线程安全。

设计要点(对应 v3 文档 §3.3 / §10.2):
  - 拉式收集:遍历 service 子包模块命名空间,用 ``type(attr) is EndpointSpec``
    严格匹配(排除继承,配合 ``@final``)
  - 线程安全:``threading.Lock`` 保护 ``_index`` / ``_loaded`` 的修改;
    "collect + dict 读取/迭代"必须在同一把锁内,避免锁外迭代被并发的
    collect 触发 ``RuntimeError: dictionary changed size during iteration``
  - 共用 ``warm()``:`contract check` 与 mock server 启动都走这一入口
  - 按需加载:scenario 加载器和 mock 启动都"按需",未引用的 service
    一个字节都不 import

⚠ 易错点(已修,v3 §10.2):``resolve`` / ``warm`` 必须把 "collect + 读"
包进同一个 ``with self._lock:``。``_collect_locked`` 是内部锁内版本,
``collect`` 是公开自带取锁版本,``resolve`` / ``warm`` 用 ``_collect_locked``。
"""
from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass

from ._aliases import resolve_dir_name
from .spec import EndpointSpec


# ════════════════════════════════════════════════════════════════════════════
# 公开类型
# ════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EndpointKey:
    """Registry 索引键。frozen=True 保证可作 dict key / set element。"""
    service: str
    method: str
    path: str


class BootstrapError(RuntimeError):
    """``warm()`` 失败时的聚合错误——多 service 异常合并抛出,便于一次性 fail-fast。"""


# ════════════════════════════════════════════════════════════════════════════
# Registry 主体
# ════════════════════════════════════════════════════════════════════════════

class _Registry:
    """进程级单例。线程安全、按需加载、拉式收集。"""

    def __init__(self) -> None:
        self._index: dict[EndpointKey, EndpointSpec] = {}
        self._loaded: set[str] = set()
        self._lock = threading.Lock()

    # ── 锁内操作(假设调用方已持锁)──

    def _collect_locked(self, service: str) -> None:
        """import service 包,遍历模块命名空间,拉式收集所有 ``EndpointSpec`` 实例。

        严格 ``type(attr) is EndpointSpec`` 匹配,排除任何继承(``@final`` 配合)。
        """
        if service in self._loaded:
            return
        dir_name = resolve_dir_name(service)
        try:
            module = importlib.import_module(f"ModelRegistry.{dir_name}")
        except ImportError as e:
            raise LookupError(
                f"[ModelRegistry] service '{service}' 对应的目录 "
                f"'ModelRegistry/{dir_name}/' 不存在或导入失败: {e}"
            ) from e
        for attr in vars(module).values():
            if type(attr) is EndpointSpec:
                key = EndpointKey(service, attr.method, attr.path)
                self._index[key] = attr
        self._loaded.add(service)

    def _check_no_duplicate_paths_locked(self, service: str) -> None:
        """同 service 内 (method, path) 唯一性检查(内部一致性)。

        实际去重由 ``_index`` 的 dict 语义保证:同 key 会被后者覆盖。
        此方法作为契约:在 service collect 完后跑一次,发现"被覆盖"则报错。
        留给 ``warm()`` 在断言模式下调用;单 ``collect`` 不强制(允许同 path
        在不同 service 下出现)。
        """
        seen: dict[tuple[str, str], str] = {}  # (method, path) -> 第一次出现的 service
        for key, spec in self._index.items():
            sub_key = (key.method, key.path)
            if sub_key in seen:
                # 仅在两个 service 名都不同时报错(同 service 同 (method, path)
                # 是真正的"撞 path";不同 service 算作跨 service,不算重复)
                # 实际上 _index 不会跨 service 撞(method, path),因为 key 包含 service。
                # 此检查只用作"作者可能把同名 spec 误写到多个 service"的弱提示。
                if seen[sub_key] == key.service:
                    raise ValueError(
                        f"[ModelRegistry] 内部一致性违反:service '{key.service}' 内 "
                        f"({key.method} {key.path}) 出现多次。"
                    )
            else:
                seen[sub_key] = key.service

    # ── 公开 API(总是先取锁)──

    def collect(self, service: str) -> None:
        """import 该 service 包,拉式收集所有 ``EndpointSpec`` 实例。幂等。"""
        with self._lock:
            self._collect_locked(service)

    def resolve(self, service: str, method: str, path: str) -> EndpointSpec:
        """按 ``(service, method, path)`` 拿 ``EndpointSpec``。首次访问触发 collect。

        整个 collect + dict 读取都在同一把锁内:避免并发的 collect 修改
        ``_index`` 时,本线程在锁外迭代 ``_index`` 触发
        ``RuntimeError("dictionary changed size during iteration")``。
        ``EndpointSpec`` 是 ``frozen=True`` 的 dataclass,锁内取出后到锁外用
        是安全的(实例不可变,无 TOCTOU 风险)。
        """
        key = EndpointKey(service, method, path)
        with self._lock:
            self._collect_locked(service)
            if key not in self._index:
                registered = sorted(
                    f"  {k.method} {k.path}" for k in self._index if k.service == service
                )
                hint = (
                    f"\n请在 ModelRegistry/{resolve_dir_name(service)}/ 下建对应 endpoint 文件,"
                    f"或修正 scenario 中 path 的拼写。"
                )
                raise LookupError(
                    f"[ModelRegistry] 未找到 {service} {method} {path}。\n"
                    f"该 service 已注册端点:\n" + "\n".join(registered) + hint
                )
            return self._index[key]

    def warm(self, services: list[str]) -> list[EndpointSpec]:
        """共用的预热逻辑。``contract check`` 与 mock server 启动都走这里。

        返回该批 service 收集到的全部 ``EndpointSpec`` 实例(顺序按
        ``_index`` 插入序);收集过程中任一 service 失败,抛 ``BootstrapError``
        并附所有错误(便于作者一次性看到全部问题)。

        整个 collect + 列表构造都在锁内,避免锁外迭代 ``_index`` 时被
        并发的 collect 触发 ``"dictionary changed size"``。
        """
        issues: list[str] = []
        collected_specs: list[EndpointSpec] = []
        with self._lock:
            for s in services:
                try:
                    self._collect_locked(s)
                except Exception as e:
                    issues.append(f"  - {s}: {e}")
            if issues:
                raise BootstrapError(
                    f"[ModelRegistry] 预热失败,以下 service 异常:\n" + "\n".join(issues)
                )
            for k, spec in self._index.items():
                if k.service in services:
                    collected_specs.append(spec)
        return collected_specs

    def loaded_services(self) -> list[str]:
        """返回已 collect 的 service 列表(快照,用于 introspection / 报告)。"""
        with self._lock:
            return sorted(self._loaded)

    def is_loaded(self, service: str) -> bool:
        with self._lock:
            return service in self._loaded

    def reset(self) -> None:
        """清空 index 与 loaded 集合。**仅供测试使用** —— 生产代码不应调。"""
        with self._lock:
            self._index.clear()
            self._loaded.clear()


# ════════════════════════════════════════════════════════════════════════════
# 全局单例
# ════════════════════════════════════════════════════════════════════════════

registry = _Registry()


__all__ = [
    "EndpointKey",
    "BootstrapError",
    "registry",
]
