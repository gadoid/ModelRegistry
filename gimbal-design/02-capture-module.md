# 02 · capture 模块详细设计

> 本文档描述 `gimbal capture` 子命令的实现细节:目录结构、FileBus、文件锁、归档策略、与 mitmproxy 的对接、退出流程。

---

## 1. 模块职责与边界

### 1.1 职责

`gimbal capture` 是 gimbal 平台的**流量录制组件**,只做一件事:

> 把浏览器(或任何 HTTP 客户端)通过本地代理发出的 HTTP 请求/响应,**原样追加**写到 `$GIMBAL_HOME/captures/active/{sid}.ndjson`。

### 1.2 不做(明确排除)

| 不做 | 替代方案 |
|---|---|
| 把 NDJSON 转成 step 片段 | 由 prism 模块的 `gimbal/prism/convert.py` 负责 |
| 实时把事件推送给 prism | 写盘即可,prism 用 watchdog 读 |
| 解析请求/响应体 | 原样存,下游想解析自己解析 |
| 加密字段脱敏 | v0 不做;敏感字段由 prism 端的 `<REDACTED>` 机制处理 |
| 多 session 合并 / 切分 | 每个 session 独立文件 |

### 1.3 代码位置

```
gimbal/
└── capture/
    ├── __init__.py              # 公开 API:FileBus / FileSink / CaptureEvent / archive_session
    ├── proxy.py                 # mitmproxy addon
    ├── recorder.py              # CaptureEvent dataclass + 序列化
    ├── bus.py                   # FileBus 实现(写入 + 文件锁)
    ├── archive.py               # 归档策略(active → archive)
    ├── filter.py                # path 前缀过滤
    └── cli.py                   # 子命令注册(被 gimbal/cli/capture.py 调用)
```

---

## 2. CaptureEvent 数据模型

### 2.1 类定义(`gimbal/capture/recorder.py`)

```python
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class CaptureEvent:
    """单次 HTTP 抓包事件。"""
    ts: float                                    # epoch 秒
    method: str                                  # 大写
    scheme: str                                  # http / https
    host: str
    port: int
    path: str                                    # 已去 query string
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    response_status: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""

    def to_dict(self) -> dict[str, Any]:
        """输出与 NDJSON 写入格式一致的 dict(嵌套 response.*)。

        注意:CaptureEvent 内部把 response 拆成平铺字段(便于 dataclass),
        序列化时合并为 {response: {status, headers, body}} 与 capture.py 历史输出对齐。
        """
        d = asdict(self)
        d["response"] = {
            "status": d.pop("response_status"),
            "headers": d.pop("response_headers"),
            "body": d.pop("response_body"),
        }
        return d
```

### 2.2 与历史 capture.py 输出的兼容

`prism/capture.py:33-48` 当前输出 `response.{status, headers, body}` 嵌套结构。`gimbal/capture/recorder.py:to_dict()` 保持同样的形态,**确保 NDJSON 行字段一致**,旧 reader 不需改动。

---

## 3. FileBus 实现

### 3.1 类骨架(`gimbal/capture/bus.py`)

```python
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import IO

from .recorder import CaptureEvent


class SessionLockedError(RuntimeError):
    """同 session 已有另一个 capture 进程持有锁。"""


class FileBus:
    """capture 进程的唯一写入契约。"""

    def __init__(self, home: Path, session_id: str) -> None:
        self.home = home
        self.session_id = session_id
        self.path = home / "captures" / "active" / f"{session_id}.ndjson"
        self._fp: IO[str] | None = None
        self._lock_backend: LockBackend | None = None

    # ─── 公开方法 ───

    def write(self, event: CaptureEvent) -> None:
        """单次写入。失败抛异常(进程退出)。"""
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
        if self._lock_backend is not None:
            self._lock_backend.release()
            self._lock_backend = None

    # ─── 内部 ───

    def _open_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # append 模式:不破坏已有内容
        fp = self.path.open("a", encoding="utf-8", buffering=1)  # line-buffered
        lock = make_lock_backend()  # 工厂,见 §4
        try:
            lock.acquire(fp.fileno())
        except SessionLockedError:
            fp.close()
            raise
        self._fp = fp
        self._lock_backend = lock


# 模块级工厂
def make_lock_backend() -> "LockBackend":
    if sys.platform == "win32":
        return WindowsLock()
    return PosixLock()
```

### 3.2 错误处理

| 场景 | 行为 |
|---|---|
| 文件锁被占(`SessionLockedError`) | 直接抛,不重试;CLI 退出码 4 |
| 磁盘满(`OSError: No space left`) | close() + 抛;CLI 退出码 1 |
| 文件被外部删除 | 下次 write 时 reopen,继续写;但归档时检测不到该文件 |
| 父目录被删除 | 下次 mkdir -p,继续写 |

### 3.3 并发模型

- **进程级单例**:每个 capture 进程只开一个 session,只持一个 FileBus 实例
- **跨进程**:用文件锁保证同 session 只能一个 capture 进程写入
- **跨线程**:mitmproxy addon 默认单线程,无需线程安全;若改 mitmdump -T worker 模式需加 `threading.Lock`

---

## 4. 文件锁实现

### 4.1 后端抽象(`gimbal/capture/bus.py`)

```python
from abc import ABC, abstractmethod


class LockBackend(ABC):
    @abstractmethod
    def acquire(self, fd: int) -> None:
        """非阻塞获取锁。失败抛 SessionLockedError。"""

    @abstractmethod
    def release(self) -> None:
        ...


class PosixLock(LockBackend):
    def acquire(self, fd: int) -> None:
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SessionLockedError(f"session 已被另一个进程占用")

    def release(self) -> None:
        # 进程退出 / close() 时自动释放,无需显式 unlock
        pass


class WindowsLock(LockBackend):
    """Windows 使用 msvcrt.locking。

    注意:msvcrt.locking 锁的是"文件区域",不是整个文件描述符。
    我们锁定第 1 个字节(0..1 区域),锁文件 fd 0..1MB 范围。
    """
    def acquire(self, fd: int) -> None:
        import msvcrt
        try:
            # 锁定第 0 个字节(MS 风格:start, length)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SessionLockedError(f"session 已被另一个进程占用")

    def release(self) -> None:
        import msvcrt
        # 文件 close 时 Windows 自动释放;此处只尝试 unlock
        try:
            msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        except (OSError, AttributeError):
            pass
        self._fd = None

    def __init__(self) -> None:
        self._fd: int | None = None

    def acquire(self, fd: int) -> None:  # type: ignore[override]
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            self._fd = fd
        except OSError:
            raise SessionLockedError(f"session 已被另一个进程占用")
```

### 4.2 锁粒度选择

| 选项 | 选择 | 理由 |
|---|---|---|
| 整文件锁(`LOCK_EX`) | ✅ | 简单;写频率低(~10/s);无读阻塞问题 |
| 区域锁(每行一段) | ❌ | 复杂度高,无实际收益 |
| advisory lock(`flock`) | ✅ | POSIX 标准;进程退出自动释放 |
| mandatory lock | ❌ | 平台差异大;Windows 不支持 |

---

## 5. 归档策略

### 5.1 触发时机

| 触发点 | 行为 |
|---|---|
| capture Ctrl+C / SIGTERM | 主动归档 |
| `gimbal capture archive <sid>` | 手动归档 |
| capture 进程崩溃(SIGKILL/异常退出) | **不归档**(下次 start 时检测残留,提示用户) |

### 5.2 归档路径

```
active/{sid}.ndjson  →  archive/{YYYY-MM-DD}/{sid}-{epoch_seconds}.ndjson
```

**示例**:
```
captures/active/dev-1.ndjson
→ captures/archive/2026-06-17/dev-1-1718611200.ndjson
```

### 5.3 实现(`gimbal/capture/archive.py`)

```python
from datetime import datetime
from pathlib import Path
import shutil
import time


def archive_session(home: Path, session_id: str) -> Path | None:
    """把 active/{sid}.ndjson 移到 archive/{date}/{sid}-{ts}.ndjson。

    :returns: 归档后的新路径;若源文件不存在则返回 None。
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
```

### 5.4 残留检测

capture start 时若发现 `active/{sid}.ndjson` 已存在(可能是上次崩溃),处理策略:

```python
# gimbal/capture/cli.py(start 命令)
active_path = home / "captures" / "active" / f"{session_id}.ndjson"
if active_path.exists():
    # 检查文件锁是否被持有(可能有别的进程在写)
    if is_lock_held(active_path):
        raise SessionLockedError(...)
    # 无锁持有 → 提示用户
    if not typer.confirm(
        f"session '{session_id}' 已有残留数据 {active_path.stat().st_size} bytes,如何处理?",
        default=False,
    ):
        raise typer.Exit(1)
    # 用户选覆盖 → truncate 后继续
    active_path.write_text("", encoding="utf-8")
```

---

## 6. mitmproxy addon

### 6.1 类实现(`gimbal/capture/proxy.py`)

```python
from __future__ import annotations
import sys
import time
from mitmproxy import ctx, http

from .bus import FileBus
from .recorder import CaptureEvent
from .filter import PathFilter


class CaptureAddon:
    """mitmproxy addon:按 path 前缀过滤,落 FileBus。"""

    def __init__(self, bus: FileBus, path_filter: PathFilter) -> None:
        self.bus = bus
        self.filter = path_filter
        self.count = 0

    def load(self, loader) -> None:
        loader.add_option(
            "capture_filter", str, "/api/",
            "path 前缀过滤,逗号分隔,如 /api/order,/api/user",
        )
        loader.add_option(
            "capture_out", str, "captures.ndjson", "NDJSON 输出文件(兼容旧 CLI)",
        )
        # 注意:本次改造不直接使用 capture_filter / capture_out,真正参数走 CLI

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.response is None:
            return  # 失败请求不录

        path = flow.request.path.split("?")[0]
        if not self.filter.match(path):
            return

        event = CaptureEvent(
            ts=time.time(),
            method=flow.request.method,
            scheme=flow.request.scheme,
            host=flow.request.host,
            port=flow.request.port,
            path=path,
            query=dict(flow.request.query),
            headers=dict(flow.request.headers),
            body=flow.request.get_text(),
            response_status=flow.response.status_code,
            response_headers=dict(flow.response.headers),
            response_body=flow.response.get_text(),
        )
        self.bus.write(event)
        self.count += 1
        print(
            f"[capture] #{self.count} {event.method} {event.path}",
            file=sys.stderr,
            flush=True,
        )

    def done(self) -> None:
        """mitmproxy 关闭时调用。"""
        self.bus.close()


addons = []  # 注意:不直接注册 addon,见 §6.2
```

### 6.2 addon 注册(避免 mitmproxy 默认行为)

mitmproxy 通过 `addons = [MyAddon()]` 全局变量自动注册。**但这导致 addon 在 import 时就实例化**,无法传参。我们改用 `mitmdump -s` 方式加载脚本:

```python
# gimbal/capture/cli.py
def start_cmd(
    session: str = typer.Option(..., "--session", "-s"),
    port: int = typer.Option(8080, "--port", "-p"),
    filter: str = typer.Option("/api/", "--filter", "-f"),
    home: Path = typer.Option(Path("~/.gimbal").expanduser(), "--home"),
    mitmdump: str = typer.Option("mitmdump", help="mitmdump 可执行文件"),
):
    """启动捕获代理。"""
    home.mkdir(parents=True, exist_ok=True)
    bus = FileBus(home, session)
    path_filter = PathFilter.from_csv(filter)

    # 把 addon 实例化 + 注册写到临时脚本,通过 mitmdump -s 加载
    addon_script = _render_addon_script(bus.path, filter)
    tmp_script = home / ".tmp_capture_addon.py"
    tmp_script.write_text(addon_script, encoding="utf-8")

    cmd = [
        mitmdump,
        "-s", str(tmp_script),
        "-p", str(port),
        "-q",
        "--set", f"capture_home={home}",
        "--set", f"capture_session={session}",
    ]
    typer.echo(f"[capture] session={session}  port={port}  filter={filter}")
    typer.echo(f"[capture] out={bus.path}")
    typer.echo("[capture] 浏览器代理指向 127.0.0.1:8080,信任 mitmproxy CA(http://mitm.it)")

    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
    except KeyboardInterrupt:
        typer.echo("\n[capture] stopping...")
    finally:
        archive_session(home, session)
        tmp_script.unlink(missing_ok=True)
        typer.echo(f"[capture] archived → {home}/captures/archive/")
```

**关键点**:
- addon 通过 `-s` 加载,**而不是** 在 Python 模块顶层 `addons = [...]`,因为我们要在 `__main__` 上下文里实例化 FileBus
- `--set capture_home` / `--set capture_session` 把参数传进 addon,addon 通过 `ctx.options` 读取

### 6.3 临时 addon 脚本渲染

```python
def _render_addon_script(home: Path, filter: str) -> str:
    return f'''
# Auto-generated by gimbal capture;do not edit.
import sys
from pathlib import Path

# 把 gimbal 包加进 sys.path
sys.path.insert(0, r"{Path(__file__).parent.parent.parent.resolve()}")

from gimbal.capture.bus import FileBus
from gimbal.capture.recorder import CaptureEvent
from gimbal.capture.filter import PathFilter
from gimbal.capture.proxy import CaptureAddon

home = Path(r"{home}")
session = {session!r}
bus = FileBus(home, session)
path_filter = PathFilter.from_csv({filter!r})

addons = [CaptureAddon(bus, path_filter)]
'''
```

**注意**:`sys.path` 注入只用于子进程启动,主进程(CLI)直接 `import gimbal.capture`。

---

## 7. Path 过滤

### 7.1 实现(`gimbal/capture/filter.py`)

```python
from __future__ import annotations


class PathFilter:
    """path 前缀匹配。空列表 = 不过滤(全部记录)。"""

    def __init__(self, prefixes: list[str]) -> None:
        # 去重 + 去尾 /
        self.prefixes = list({p.rstrip("/") for p in prefixes if p})

    @classmethod
    def from_csv(cls, csv: str) -> "PathFilter":
        return cls([p.strip() for p in csv.split(",") if p.strip()])

    def match(self, path: str) -> bool:
        if not self.prefixes:
            return True  # 无过滤
        return any(path == p or path.startswith(p + "/") for p in self.prefixes)

    def __bool__(self) -> bool:
        return bool(self.prefixes)
```

### 7.2 匹配规则

- `/api/order` 匹配 `/api/order`、`/api/order/123`,**不匹配** `/api/orderlist`(避免前缀误伤)
- 多个前缀任一匹配即通过(OR 语义)
- 空 filter 字符串 → 不过滤

---

## 8. CLI 子命令

### 8.1 `gimbal capture` 命令组(`gimbal/cli/capture.py`)

```python
import typer
from pathlib import Path
from typing import Optional

from gimbal.capture.cli import start_cmd, list_sessions, show_session, archive_cmd

capture_app = typer.Typer(help="gimbal 流量捕获模块", no_args_is_help=True)


@capture_app.command("start")
def start(
    session: str = typer.Option(..., "--session", "-s", help="会话 ID"),
    port: int = typer.Option(8080, "--port", "-p"),
    filter: str = typer.Option("/api/", "--filter", "-f"),
    home: Path = typer.Option(Path("~/.gimbal").expanduser(), "--home"),
    mitmdump: str = typer.Option("mitmdump", help="mitmdump 可执行文件"),
):
    """启动 mitmproxy 抓包,Ctrl+C 停止并自动归档。"""
    start_cmd(session, port, filter, home, mitmdump)


@capture_app.command("list")
def list_cmd(
    home: Path = typer.Option(Path("~/.gimbal").expanduser(), "--home"),
):
    """列出 active 下所有 session。"""
    list_sessions(home)


@capture_app.command("show")
def show_cmd(
    session: str = typer.Argument(..., help="会话 ID"),
    home: Path = typer.Option(Path("~/.gimbal").expanduser(), "--home"),
    limit: int = typer.Option(50, "--limit", "-n"),
):
    """查看某 session 的事件(默认最近 50 条)。"""
    show_session(home, session, limit)


@capture_app.command("archive")
def archive_cmd(
    session: str = typer.Argument(..., help="会话 ID"),
    home: Path = typer.Option(Path("~/.gimbal").expanduser(), "--home"),
):
    """手动归档一个 session(从 active 移到 archive)。"""
    archive_cmd(home, session)
```

### 8.2 `list` / `show` 实现(用 prism 不依赖 prism)

```python
# gimbal/capture/cli.py(辅助函数)
def list_sessions(home: Path) -> None:
    active = home / "captures" / "active"
    if not active.exists():
        typer.echo("(无 active session)")
        return
    for p in sorted(active.glob("*.ndjson")):
        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        typer.echo(f"{p.stem:<30} {size:>10} bytes  {mtime:%Y-%m-%d %H:%M:%S}")


def show_session(home: Path, session_id: str, limit: int) -> None:
    path = home / "captures" / "active" / f"{session_id}.ndjson"
    if not path.exists():
        typer.secho(f"session 不存在: {session_id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    # 倒序读最近 N 条
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[-limit:]:
        ev = json.loads(line)
        typer.echo(f"{ev['method']:<6} {ev['host']}{ev['path']:<40} {ev['response']['status']}")


def archive_cmd(home: Path, session_id: str) -> None:
    from .archive import archive_session
    dst = archive_session(home, session_id)
    if dst:
        typer.echo(f"已归档 → {dst}")
    else:
        typer.secho(f"session 不存在: {session_id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
```

---

## 9. 测试策略

### 9.1 单元测试(`tests/test_capture_*.py`)

| 测试文件 | 覆盖 |
|---|---|
| `test_capture_recorder.py` | `CaptureEvent.to_dict()` 嵌套 response 字段 |
| `test_capture_bus.py` | FileBus 写入 + 文件锁 + 异常路径 |
| `test_capture_archive.py` | 归档函数路径 + 残留检测 |
| `test_capture_filter.py` | PathFilter 边界(`/api/order` vs `/api/orderlist`) |

### 9.2 集成测试(`tests/integration/test_capture_e2e.py`)

```python
def test_capture_start_stop(tmp_path):
    """启动 capture 子进程,模拟请求,验证 NDJSON 落盘。"""
    home = tmp_path / "gimbal"
    home.mkdir()
    proc = subprocess.Popen([
        "gimbal", "capture", "start",
        "--session", "e2e-test",
        "--home", str(home),
        "--port", "18080",
    ])
    time.sleep(2)  # 等 mitmdump 启动
    # 触发一次请求
    httpx.get("http://127.0.0.1:18080/api/test")
    time.sleep(1)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)

    # 验证 NDJSON 已落盘 + 已归档
    archive = home / "captures" / "archive"
    assert any(archive.rglob("e2e-test-*.ndjson")), "归档文件未生成"
```

### 9.3 mitmproxy mock 测试

不启动真实 mitmdump,用 `CaptureAddon.response(flow)` 直接注入 `mitmproxy.http.HTTPFlow` mock,验证写入逻辑:

```python
def test_capture_addon_writes_event(tmp_path):
    bus = FileBus(tmp_path, "test")
    addon = CaptureAddon(bus, PathFilter.from_csv("/api/"))

    flow = MagicMock(spec=http.HTTPFlow)
    flow.request.method = "GET"
    flow.request.scheme = "http"
    flow.request.host = "api.example.com"
    flow.request.port = 80
    flow.request.path = "/api/users"
    flow.request.query = {}
    flow.request.headers = {"X-Foo": "bar"}
    flow.request.get_text.return_value = ""
    flow.response.status_code = 200
    flow.response.headers = {"Content-Type": "application/json"}
    flow.response.get_text.return_value = '{"users": []}'

    addon.response(flow)
    bus.close()

    lines = (tmp_path / "captures" / "active" / "test.ndjson").read_text().strip().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["method"] == "GET"
    assert ev["path"] == "/api/users"
    assert ev["response"]["status"] == 200
```

---

## 10. 风险与已知限制

| 风险 | 影响 | 缓解 |
|---|---|---|
| mitmproxy CA 证书未安装 | 浏览器 HTTPS 抓包失败 | 启动时检测 + 提示 `mitm.it` |
| 临时 addon 脚本被 AV 拦截 | Windows Defender 误报 | 加入白名单 / 改用预编译 |
| 同 session 启动时残留文件 | 旧数据混入 | 启动时检测 + 用户确认(v0)或自动归档(v0.1) |
| 大体积响应体(>10MB) | 单行 NDJSON 巨大 | 加响应体大小阈值,超过则截断 + warning |
| mitmproxy 版本升级 API 变化 | addon 失效 | `requirements.txt` 锁定 `mitmproxy>=12.0,<13` |
| Windows 上 msvcrt.locking 不支持网络文件系统 | NFS 文件锁失败 | 检测路径类型 + 拒绝网络盘归档 |

---

## 11. 下游文档引用

- 总体架构(两个模块位置) → [01-architecture.md](01-architecture.md) §1
- prism 读取 capture 数据的方式 → [03-prism-module.md](03-prism-module.md) §3
- 迁移执行步骤 → [06-migration-plan.md](06-migration-plan.md) M1