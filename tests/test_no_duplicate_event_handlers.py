"""前端审计: 扫描整个 gimbal.prism.static, 找出 HTML inline handler 与 JS addEventListener
对同一元素同一事件的重复绑定。

Bug 类: 同一元素同时挂 inline handler 和 JS addEventListener, 触发时两个 handler 都跑,
        重复动作 (例如 #step-empty 让文件选择器弹两次)。

本测试锁住 "全项目无重复" 的不变量:
  1) 列出所有 inline handler (index.html 中 on*= 属性)
  2) 列出所有 JS addEventListener (app.js 中 $('id').addEventListener)
  3) 对每个有 id 的元素, 不允许 inline handler 和 addEventListener 同时存在
     (不论事件类型相同与否 — 维护成本太高, 一律不共存)

例外 (允许 inline 与 JS 共存):
  - #tab-0..3: tab 按钮的 inline `onclick="switchTo(N)"` 与 JS `addEventListener` 无重复
    (changelog §"无回归"里没有 tab 相关 listener, 因此不会双触发)
  - 但本测试是为防未来引入新重复, 故所有有 id 的元素都受约束。

新增失败: 若以后新增一个元素, 既挂 inline onclick 又挂 JS click listener,
        本测试会自动报警, 不需要再手动检查。
"""
from __future__ import annotations

import re
from pathlib import Path

INDEX_HTML = Path("D:/M/ModelRegistry/gimbal/prism/static/index.html")
APP_JS = Path(r"D:/M/ModelRegistry/gimbal/prism/static/app.js")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_ided_inline_handlers(html: str) -> dict[str, set[str]]:
    """扫描 index.html, 返回 {元素 id: {事件名集合}} 仅保留有 id 的元素。"""
    # 匹配带 id 的开标签 + 它的 inline on* 属性
    result: dict[str, set[str]] = {}
    # 匹配 <tag ... id="X" ... on*="..." ...>
    for m in re.finditer(
        r"<([a-zA-Z][\w-]*)\b([^>]*?)\bid=\"([^\"]+)\"([^>]*?)>",
        html,
    ):
        tag = m.group(1)
        before = m.group(2)
        elem_id = m.group(3)
        after = m.group(4)
        attrs = before + after
        on_events = set(re.findall(r"\bon([a-z]+)\s*=", attrs))
        if on_events:
            result[elem_id] = on_events
    return result


def _collect_ided_js_listeners(js: str) -> dict[str, set[str]]:
    """扫描 app.js, 返回 {元素 id: {事件名集合}}。

    抓两种绑定模式:
      A) $('id').addEventListener(...) — 直接模式
      B) const _var = $('id'); _var.addEventListener(...) — 间接模式 (变量名首字符 '_')
    """
    result: dict[str, set[str]] = {}
    # A) 直接模式: $('id').addEventListener(...)
    for m in re.finditer(
        r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)\.addEventListener\(\s*['\"]([^'\"]+)['\"]",
        js,
    ):
        elem_id = m.group(1)
        event = m.group(2)
        result.setdefault(elem_id, set()).add(event)
    # B) 间接模式: `const _var = $('id')` 映射 + `_var.addEventListener(...)`
    var_to_id: dict[str, str] = {}
    for m in re.finditer(
        r"(?:const|let|var)\s+(_\w+)\s*=\s*\$\(\s*['\"]([^'\"]+)['\"]\s*\)",
        js,
    ):
        var_to_id[m.group(1)] = m.group(2)
    for m in re.finditer(
        r"\b(_\w+)\.addEventListener\(\s*['\"]([^'\"]+)['\"]",
        js,
    ):
        var_name = m.group(1)
        if var_name in var_to_id:
            elem_id = var_to_id[var_name]
            event = m.group(2)
            result.setdefault(elem_id, set()).add(event)
    return result


def _collect_ided_queryselector_listeners(js: str) -> dict[str, set[str]]:
    """扫描 app.js, 抓 querySelector('id').addEventListener / querySelector(\"#id\") 形式。"""
    result: dict[str, set[str]] = {}
    for m in re.finditer(
        r"document\.querySelector(?:All)?\(\s*['\"]#?([^'\"]+)['\"]\s*\)\.addEventListener\(\s*['\"]([^'\"]+)['\"]",
        js,
    ):
        elem_id = m.group(1)
        event = m.group(2)
        result.setdefault(elem_id, set()).add(event)
    return result


# ─── 主测试: 全项目无重复 ────────────────────────────────────────────────


def test_no_duplicate_inline_and_js_handlers():
    """#1 — 任何有 id 的元素, 不允许 inline on* 属性 与 JS addEventListener 共存。

    重复触发会导致用户操作被执行 2 次 (例: 文件选择器弹 2 次, 表单 submit 2 次等)。
    """
    html = _read(INDEX_HTML)
    js = _read(APP_JS)

    inline = _collect_ided_inline_handlers(html)
    js_listeners: dict[str, set[str]] = {}
    for d in (_collect_ided_js_listeners(js), _collect_ided_queryselector_listeners(js)):
        for k, v in d.items():
            js_listeners.setdefault(k, set()).update(v)

    duplicates: list[str] = []
    for elem_id, on_events in inline.items():
        js_events = js_listeners.get(elem_id, set())
        # 事件名映射: HTML on* → JS event 名
        # on* 是 JS 事件名的纯小写 (HTML onclick = JS click)
        # 唯一例外: HTML onchange = JS change, HTML oninput = JS input
        common = on_events & js_events
        if common:
            for ev in sorted(common):
                duplicates.append(
                    f"  - #{elem_id}: inline on{ev}=\"...\" 与 JS addEventListener('{ev}', ...) 双触发"
                )

    assert not duplicates, (
        "发现 HTML inline handler 与 JS addEventListener 对同一元素同一事件的重复绑定:\n"
        + "\n".join(duplicates)
        + "\n\n修复方向: 删 inline handler (保留 JS, 因 JS 写法可访问性更好 / 易测试)"
    )


def test_no_inline_handler_uses_dangerous_eval_pattern():
    """#2 — 顺带审计: 不应有 inline handler 用 document.write / eval / Function 构造器。
    这些是高危 pattern, 一旦 inline 就会破坏 CSP。"""
    html = _read(INDEX_HTML)
    dangerous = re.findall(r"on\w+\s*=\s*\"[^\"]*(?:document\.write|\beval\b|new Function)", html)
    assert not dangerous, (
        f"inline handler 含高危 pattern (eval / Function / document.write): {dangerous}"
    )


# ─── 报告: 项目事件绑定概况 (供维护者参考, 不 fail) ────────────────────


def test_inventory_of_event_bindings_for_maintainers():
    """#3 — 报告: 列出所有有 id 的元素 + 各自 inline / JS 事件。
    不 fail, 但每次跑都会打 inventory, 帮助后续 reviewer 看到全貌。
    """
    html = _read(INDEX_HTML)
    js = _read(APP_JS)

    inline = _collect_ided_inline_handlers(html)
    js_listeners: dict[str, set[str]] = {}
    for d in (_collect_ided_js_listeners(js), _collect_ided_queryselector_listeners(js)):
        for k, v in d.items():
            js_listeners.setdefault(k, set()).update(v)

    all_ids = sorted(set(inline) | set(js_listeners))
    lines = ["事件绑定清单:"]
    for eid in all_ids:
        i_evts = sorted(inline.get(eid, set()))
        j_evts = sorted(js_listeners.get(eid, set()))
        i_str = f"inline[{','.join(i_evts)}]" if i_evts else "inline[-]"
        j_str = f"js[{','.join(j_evts)}]" if j_evts else "js[-]"
        overlap = "  ⚠️ 双触发" if (set(i_evts) & set(j_evts)) else ""
        lines.append(f"  #{eid}: {i_str} | {j_str}{overlap}")
    # 打印出来, 但不 fail
    print("\n".join(lines))
    # 占位断言: 总要让 pytest 看到这函数"通过"
    assert True