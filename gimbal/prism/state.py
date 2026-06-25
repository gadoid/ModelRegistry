"""gimbal.prism.state — Session / SessionStore / CaptureReader / CaptureWatcher。

v0 用法: 走 FastAPI `lifespan` + `app.state` 集中管理,**禁止**模块级 mutable 单例。
"""
from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

# watchdog 是可选依赖 (lifespan 内 lazy 探测,失败则降级为无监听)
# v0.5.2 试过 watchdog.observers.polling.PollingObserver, 但 Windows 上
# on_modified 触发的是**目录**而非具体文件, 我们的过滤逻辑失效.
# v0.5.4: 不再依赖 watchdog, 改用自实现后台轮询线程.
try:
    import threading  # noqa: F401  (用于 CaptureWatcher)
    _HAS_WATCHDOG = True
except ImportError:  # pragma: no cover
    _HAS_WATCHDOG = False
    Observer = None  # type: ignore[assignment]
    FileSystemEventHandler = object  # type: ignore[assignment, misc]


# ────────────────────────────────────────────────────────────────────────────
# Session
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Session:
    """单个 draft 会话状态。"""
    # v0.5.8: draft 默认填 DraftIn 默认值 (含 name="template"), 不再空 dict
    draft: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        """编辑前快照(深拷贝,用于 undo)。"""
        return copy.deepcopy(self.draft)

    def push_history(self, snapshot: dict[str, Any]) -> None:
        self.history.append(snapshot)
        self.redo_stack.clear()  # 任何新编辑清空 redo

    def undo(self) -> dict[str, Any] | None:
        if not self.history:
            return None
        self.redo_stack.append(copy.deepcopy(self.draft))
        self.draft = self.history.pop()
        return self.draft

    def redo(self) -> dict[str, Any] | None:
        if not self.redo_stack:
            return None
        self.history.append(copy.deepcopy(self.draft))
        self.draft = self.redo_stack.pop()
        return self.draft


class SessionStore:
    """session_id → Session 索引。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            sess = Session()
            # v0.5.8: 填充 DraftIn 默认值 (含 name="template"),
            # 避免新 session 草稿是空 dict 导致前端 fields 为空
            try:
                from gimbal.prism.server import DraftIn  # 避免循环 import
                sess.draft = DraftIn().model_dump()
            except ImportError:
                pass
            self._sessions[session_id] = sess
        return self._sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._sessions)


# ────────────────────────────────────────────────────────────────────────────
# CaptureReader (文件只读视图)
# ────────────────────────────────────────────────────────────────────────────


class CaptureReader:
    """对 capture/active/*.ndjson 的只读视图。"""

    def __init__(self, home: Path) -> None:
        self.home = home

    def list_active(self) -> list[dict[str, Any]]:
        active = self.home / "captures" / "active"
        if not active.exists():
            return []
        return [
            {
                "session_id": p.stem,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            }
            for p in sorted(active.glob("*.ndjson"))
        ]

    def read(self, session_id: str, limit: int | None = 500) -> list[dict[str, Any]]:
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        if limit is not None and len(events) > limit:
            events = events[-limit:]
        return events

    def truncate(self, session_id: str) -> bool:
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        if not path.exists():
            return False
        path.write_text("", encoding="utf-8")
        return True

    def append(self, session_id: str, event: dict[str, Any]) -> None:
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


# ────────────────────────────────────────────────────────────────────────────
# CaptureWatcher (v0.5.4: 自实现轮询线程, 替代 watchdog PollingObserver)
#
# v0.5.2 试过 watchdog.observers.polling.PollingObserver, 但在 Windows 上:
#   - on_modified 触发的是**目录**, 不是具体文件
#   - 我们的过滤逻辑 P(event.src_path) == self.path 失败, 事件被跳过
#   - 结果: 实时推送在 Windows 上完全失效
#
# 修复: 不依赖 watchdog, 直接用后台线程 + os.stat 轮询文件大小.
# 100 sessions × 5/s = 500 stat/s, 开销可忽略.
# ────────────────────────────────────────────────────────────────────────────


class WatchHandle:
    def __init__(self, watcher: "CaptureWatcher", session_id: str) -> None:
        self._watcher = watcher
        self._session_id = session_id
        self._active = True

    def stop(self) -> None:
        if self._active:
            self._watcher._unschedule(self._session_id)
            self._active = False


class _FileWatch:
    """单个 NDJSON 文件的轮询状态。"""

    def __init__(self, path: Path, on_event: Callable[[dict], None]) -> None:
        self.path = path
        self.on_event = on_event
        self._last_pos = 0
        self._last_mtime = 0.0
        self._last_size = 0

    def poll(self) -> None:
        """检查文件是否被修改, 是则读新增内容."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return
        # 用 (mtime, size) 联合检测 (size 变化最可靠)
        if stat.st_size == self._last_size and stat.st_mtime == self._last_mtime:
            return
        self._last_size = stat.st_size
        self._last_mtime = stat.st_mtime
        # 文件被截断 (e.g. 用户点"清空"): 重置 _last_pos
        if stat.st_size < self._last_pos:
            self._last_pos = 0
        try:
            with self.path.open("r", encoding="utf-8") as f:
                f.seek(self._last_pos)
                for line in f:
                    if line.strip():
                        self.on_event(json.loads(line))
                self._last_pos = f.tell()
        except FileNotFoundError:
            pass  # 文件被归档后删除, 忽略


class CaptureWatcher:
    """自实现轮询线程: 每 0.2s 检查所有 watched 文件的 mtime/size."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self._watches: dict[str, _FileWatch] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        self._started = False

    def _ensure_thread(self) -> None:
        """懒启动轮询线程 (第一次 watch() 时启动)."""
        with self._start_lock:
            if self._started:
                return
            self._thread = threading.Thread(
                target=self._poll_loop, name="capture-watcher", daemon=True,
            )
            self._thread.start()
            self._started = True

    def _poll_loop(self) -> None:
        while not self._stop.wait(0.2):
            with self._lock:
                watches = list(self._watches.values())
            for w in watches:
                try:
                    w.poll()
                except Exception:  # noqa: BLE001
                    pass  # 单文件出错不影响其他

    def watch(self, session_id: str, on_event: Callable[[dict], None]) -> WatchHandle:
        """注册回调, 接收该 session 的新增事件."""
        path = self.home / "captures" / "active" / f"{session_id}.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = WatchHandle(self, session_id)
        with self._lock:
            self._watches[session_id] = _FileWatch(path, on_event)
        self._ensure_thread()
        return handle

    def _unschedule(self, session_id: str) -> None:
        with self._lock:
            self._watches.pop(session_id, None)

    def stop_all(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # 注: v0.5.4 之前用 watchdog PollingObserver (赋给 self._observer),
        # 后来改自实现轮询线程 (self._thread),_observer 字段已不存在,
        # 不再 join 它以避免 AttributeError
