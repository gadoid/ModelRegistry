"""gimbal.capture.archive — active → archive 归档策略。

归档路径: active/{sid}.ndjson → archive/{YYYY-MM-DD}/{sid}-{epoch_seconds}.ndjson

触发时机:
  - capture Ctrl+C / SIGTERM (start_cmd finally 块)
  - `gimbal capture archive <sid>` 手动归档
  - 崩溃 (SIGKILL / 异常退出) **不归档**,下次 start 时检测残留
"""
from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path


def archive_session(home: Path, session_id: str) -> Path | None:
    """把 active/{sid}.ndjson 移到 archive/{date}/{sid}-{ts}.ndjson。

    :returns: 归档后的新路径; 若源文件不存在则返回 None。
    """
    src = home / "captures" / "active" / f"{session_id}.ndjson"
    if not src.exists():
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    dst_dir = home / "captures" / "archive" / today
    dst_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    dst = dst_dir / f"{session_id}-{ts}.ndjson"
    shutil.move(str(src), str(dst))
    return dst


def list_archived(home: Path, session_id: str | None = None) -> list[Path]:
    """列出 archive 下所有 ndjson(可按 session 过滤)。"""
    archive = home / "captures" / "archive"
    if not archive.exists():
        return []
    if session_id:
        return sorted(archive.rglob(f"{session_id}-*.ndjson"))
    return sorted(archive.rglob("*.ndjson"))


def list_active(home: Path) -> list[Path]:
    """列出 active 下所有 ndjson。"""
    active = home / "captures" / "active"
    if not active.exists():
        return []
    return sorted(active.glob("*.ndjson"))
