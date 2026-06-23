"""空状态文件选择器 / 拖拽导入 / 空文件早返静态测试。"""
from __future__ import annotations

from pathlib import Path

APP_JS = Path("D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_old_import_btn_handler_removed():
    text = _read()
    assert "$('import-btn').addEventListener" not in text, \
        "应已删除旧 #import-btn click handler"


def test_old_import_path_drop_removed():
    text = _read()
    assert "import-path" not in text, "应已删除 import-path 引用"
    assert ".import-row" not in text, "应已删除 .import-row 引用"


def test_new_empty_state_triggers_file_picker():
    text = _read()
    assert "$('ndjson-file-input').click()" in text, \
        "空状态 click 应触发 $('ndjson-file-input').click()"
    assert "triggerFilePicker" in text, "应抽 triggerFilePicker 函数"
    # 键盘: Enter / Space
    assert "e.key === 'Enter' || e.key === ' '" in text, \
        "空状态应支持 Enter/Space 触发"


def test_file_input_change_validates_extension():
    text = _read()
    assert "_ndjsonInput.addEventListener('change'" in text, \
        "ndjson-file-input 应有 change 监听"
    assert "请选择 .ndjson 文件" in text, "非 .ndjson 应 toast 拒绝"
    assert "/\\.ndjson$/i.test(file.name)" in text, "应做后缀校验"


def test_drop_on_empty_state_and_step_main():
    text = _read()
    assert "_handleNdjsonDrop" in text, "应抽 drop handler"
    assert ".step-main" in text, "应绑定 .step-main 为 drop target"
    assert "prism-drop-target" in text, "应使用 prism-drop-target 视觉类"
    assert "请拖入 .ndjson 文件" in text, "拖入非 .ndjson 应 toast"


def test_empty_file_early_return():
    text = _read()
    assert "文件为空, 无可导入" in text, "空文件应早返并 toast"
    # _importNdjsonFile 内部 text trim 后判空
    assert "if (!text || !text.trim())" in text or "if (!text.trim())" in text, \
        "应检查 text.trim() 为空"


def test_import_from_file_alias_kept():
    """向后兼容: importFromFile 别名保留。"""
    text = _read()
    assert "const importFromFile = _importNdjsonFile" in text, \
        "应保留 importFromFile 别名以防外部调用"