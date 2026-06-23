"""gimbal 顶层 typer app。

console_scripts 入口点: `gimbal = gimbal.cli.app:main`

v0 子命令:
  - capture (start / list / show / archive)
  - prism   (start)

不注册 `gimbal run`(执行器未实现)。
"""
from __future__ import annotations

import typer

app = typer.Typer(
    name="gimbal",
    help="gimbal 测试用例配置平台(capture + prism)",
    no_args_is_help=True,
)


def main() -> None:
    app()


# 子命令组挂载 (Phase 1.2 / 1.3 后实装)
# 故意留空:避免循环 import 启动失败
try:
    from gimbal.cli.capture import capture_app

    app.add_typer(capture_app, name="capture")
except ImportError:
    pass

try:
    from gimbal.cli.prism import prism_app

    app.add_typer(prism_app, name="prism")
except ImportError:
    pass
