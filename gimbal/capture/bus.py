"""gimbal.capture.bus — NDJSON 文件总线 + 跨进程文件锁。

FileBus 是 capture 进程对外的**唯一写入契约**:
  - 创建哨兵文件 {sid}.lock (O_CREAT|O_EXCL) → write (append + flush) → close + 删除哨兵

v0.5.2 改造: 原来用 fcntl.flock(POSIX) / msvcrt.locking(Windows) 锁 NDJSON 文件本身。
Windows 的 msvcrt.locking 是 **mandatory lock**, 锁住后其他进程**任何**读都会失败,
导致 prism 端 CaptureReader.read() 报 PermissionError。

修复: 不再锁 NDJSON 文件。改用独立的哨兵文件 {sid}.lock (O_CREAT|O_EXCL):
  - capture 启动时创建哨兵 → 失败抛 SessionLockedError (另一 capture 在跑)
  - capture 关闭时删除哨兵
  - prism 端: NDJSON 文件**完全无锁**, 可自由读 (CaptureReader / Watcher / WS)

跨平台一致: POSIX 的 fcntl.flock 是 advisory, 允许多读, 旧版在 Unix 上原本能工作;
Windows 的 msvcrt.locking 是 mandatory, 必须改。新方案两端行为统一。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import IO

from .recorder import CaptureEvent


class SessionLockedError(RuntimeError):
    """同 session 已有另一个 capture 进程持有哨兵。"""


class FileBus:
    """capture 进程对外契约: 把 CaptureEvent 追加写入 NDJSON。

    并发模型:
      - 哨兵文件 `{sid}.lock` 由 O_CREAT|O_EXCL 创建, 失败 → SessionLockedError
      - NDJSON 文件本身**不被锁**, 允许多读 (prism 端 CaptureReader/Watcher/WS)
    """

    def __init__(self, home: Path, session_id: str) -> None:
        self.home = home
        self.session_id = session_id
        self.path = home / "captures" / "active" / f"{session_id}.ndjson"
        self.lock_path = home / "captures" / "active" / f"{session_id}.lock"
        self._fp: IO[str] | None = None
        self._lock_fd: int | None = None
        # v0.5.2: 立即抢哨兵, 失败抛 SessionLockedError (早失败, 避免 race)
        self._open_locked()

    @property
    def is_open(self) -> bool:
        return self._fp is not None

    def write(self, event: CaptureEvent) -> None:
        """单次写入。失败抛异常(进程退出)。"""
        # v0.5.2: __init__ 已 _open_locked, 此处仅兜底
        if self._fp is None:
            self._open_locked()
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        try:
            self._fp.write(line)
            self._fp.flush()  # 行缓冲足够,但调用方期望即时可见
        except OSError:
            self.close()
            raise

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.flush()
            finally:
                self._fp.close()
                self._fp = None
        # 释放哨兵 (POSIX 显式 close, Windows 显式 close + unlink)
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        # 删哨兵文件 (POSIX 也需要, 不然下次 O_EXCL 永远失败)
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _open_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 1) 抢占哨兵 (原子): O_CREAT|O_EXCL, 失败 → 已有 capture
        try:
            self._lock_fd = os.open(
                str(self.lock_path),
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o644,
            )
        except FileExistsError as e:
            raise SessionLockedError(
                f"session '{self.session_id}' 已有另一个 capture 在跑 (哨兵 {self.lock_path})"
            ) from e
        # 写 pid 到哨兵 (调试用)
        try:
            os.write(self._lock_fd, str(os.getpid()).encode())
        except OSError:
            pass
        # 2) 打开 NDJSON append 模式 (无锁, 多读安全)
        self._fp = self.path.open("a", encoding="utf-8", buffering=1)  # line-buffered

    def __enter__(self) -> "FileBus":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
