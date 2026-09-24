"""待答卡（`js/agent-question.js`）的契约钉子。

卡片 = 模型中途 `ask_user_question` 时**人作答的那一块**。本文件钉八件事：

1. **模块形状**：`window.MemoriaAgentQuestion` 暴露 `applyPendingQuestions` / `cardEl` / `collect` /
   `summary`；依赖只有应用门面 `window.MemoriaApp`（缺桥就降级，不抛）。
2. **只走两个面**：轮询载荷 `pending_questions`（钩在 `agent_ask_poll` 上）与回填 RPC
   `agent_question_answer` —— 代码里**不许**出现自读文件 / 拼库路径的痕迹。
3. **答案形状 = 上游 `AskUserQuestionAnswerItem[]`**：`{id, selected: [...], custom?}`（选项标签原文）。
4. **不许交白卷**：每题"选了至少一项"或"自己写了一句话"，否则原地提示、**不发请求**。
5. **单选与自写互斥、多选并存**（上游 `custom` 可伴随 `selected` 的口径）。
6. **单选与多选只用 `span` 区分**（人：「保持单选的多选的圆 ui 一致，单选多选都可以用 `input`，你只需要
   在这说明单选多选 `span`」）⇒ 控件都是原生 `input`、外观同一套圆点，模式**始终**由
   `.-agent-question-mode` 徽标写明（「单选」/「多选」）。
7. **末尾追加加载**（`index.html` 最后一个 script ⇒ 既有行号锚点零漂移）+ 样式块含既有令牌。
8. **文案中英成对**（`agent.question.*` 十一个键）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_CARD = _APP / "js" / "agent-question.js"
_INDEX = _APP / "index.html"
_CSS = _APP / "css" / "app.css"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}

#: 卡片自己声明并用到的 i18n 键（前缀统一 `agent.question.`）。
#: 2026-09-23 去掉 `answered`：人反馈「我回复完 agent 之后这个卡还显示，甚至对话结束还显示」⇒
#: 答完**把卡收起**（不再在卡上写"已作答"，问答记录改由工具行 `ask_user_question` 承载）。
_KEYS = (
    "role", "title", "single", "multi", "custom", "submit",
    "sending", "failed", "needAnswer", "done",
)


def _card() -> str:
    return _CARD.read_text(encoding="utf-8")


def test_answered_card_is_dismissed_and_never_recreated() -> None:
    """人 2026-09-23：「我回复完 agent 之后这个卡还显示，甚至对话结束还显示」⇒ 答完**把卡收起**。

    两件事必须同时成立：① 提交成功后**移除卡片节点**；② 记住该批次已作答 ⇒ 后端还没把它从
    `pending_questions` 收敛掉时，下一帧**不再重建**（否则卡会"闪现回来"）。问答记录不丢：
    改由工具行 `ask_user_question` 以「问→答」文字承载（见 `agent-panel.js::askRecordText`）。
    """
    card = _card()
    assert "if (node) node.remove();" in card, "答完要移除卡片节点"
    assert "delete cards[key];" in card and "answered[key] = true;" in card, "记下已作答"
    assert "if (!key || cards[key] || answered[key]) return;" in card, "已作答的批次不许重建"
    assert 'T("agent.question.answered")' not in card, "别再往卡上写「已作答」—— 那正是它一直挂着的原因"
    assert "questionText," in card and "function questionText(" in card, "题面要留给工具行配「问→答」"


def _code() -> str:
    """剥掉注释行后的源码（注释里为说明而写的词不算越界）。"""
    return "\n".join(
        line for line in _card().splitlines() if not line.strip().startswith(("*", "//", "/*"))
    )


def test_card_exposes_the_module_shape() -> None:
    """`window.MemoriaAgentQuestion = { applyPendingQuestions, cardEl, collect, summary }`。"""
    src = _card()
    assert "global.MemoriaAgentQuestion = {" in src
    for name in ("applyPendingQuestions", "cardEl", "collect", "summary"):
        assert f"{name}," in src or f"{name}:" in src, f"缺导出：{name}"
    assert "const A = () => global.MemoriaApp || {}" in src, "只许依赖应用门面"


def test_card_only_consumes_the_two_faces() -> None:
    """只调 `agent_question_answer`；**不**自读文件、不拼库路径、不自己再调 `agent_ask_poll`。"""
    code = _code()
    called = set(re.findall(r'call\("([a-zA-Z_]+)"', code))
    assert called == {"agent_question_answer"}, f"卡片多调了别的 RPC：{sorted(called)}"
    for banned in (".memoria", "capabilities.json", "fetch(", "XMLHttpRequest", "readFile", "list_files"):
        assert banned not in code, f"卡片不该出现 {banned!r}"
    # 轮询是"包一层 call"钩住的（与 agent-panel.js 的审批卡同款），不是自己另开一路轮询
    assert 'if (fnName !== "agent_ask_poll") return pending;' in code
    assert "if (res && res.pending_questions) applyPendingQuestions(res.pending_questions);" in code


def test_answer_shape_matches_upstream() -> None:
    """答案 = `{id, selected[], custom?}` 的数组；`selected` 放**选项标签原文**。"""
    code = _code()
    assert "const answer = { id: id, selected: selected };" in code
    assert "if (custom) answer.custom = custom;" in code
    assert 'selected.push(String(input.value || ""));' in code, "选项标签原样进 selected"


def test_blank_answers_never_leave_the_browser() -> None:
    """每题都要答（选一项或写一句）：不满足就**原地提示**，一个字节都不发出去。"""
    code = _code()
    assert "if (!id || (!selected.length && !custom)) return null;" in code
    tail = code[code.index("const answers = collect(el);") :]
    assert 'if (!answers) {' in tail, "取不到完整作答时必须原地返回"
    assert 'setState(el, T("agent.question.needAnswer"));' in tail
    assert tail.index("if (!answers) {") < tail.index('call("agent_question_answer"'), "校验必须在发请求之前"
    assert "return;" in tail[tail.index("if (!answers) {") : tail.index('call("agent_question_answer"')]


def test_single_select_and_custom_text_are_mutually_exclusive() -> None:
    """单选：点选项清空自写、自写非空清掉选项；多选（没有 radio）不受此限（上游允许并存）。"""
    code = _code()
    assert 'const radios = item.querySelectorAll(\'input[type="radio"]\');' in code
    assert "if (!radios.length) return;" in code, "多选/无候选的题不该被互斥逻辑碰"
    assert 'if (custom && input.checked) custom.value = "";' in code, "点选项 ⇒ 清空自写"
    assert "radios.forEach((radio) => {" in code and "radio.checked = false;" in code, "自写 ⇒ 清掉选项"


def test_mode_is_stated_by_the_badge_not_the_widget() -> None:
    """单选/多选**长相一致**：控件都是原生 `input`（圆点由 `app.css` 统管），

    模式**始终**由标题后的 `.-agent-question-mode` 徽标写明 —— 人：「保持单选的多选的圆 ui 一致，
    单选多选都可以用 `input`，你只需要在这说明单选多选 `span`」。
    """
    code = _code()
    assert '<span class="-agent-question-mode -muted">' in code, "模式徽标不见了"
    assert 'const type = question.multiSelect ? "checkbox" : "radio";' in code, "控件应是原生 checkbox / radio"
    assert 'type="${type}"' in code
    assert 'question.multiSelect ? esc(T("agent.question.multi")) : esc(T("agent.question.single"))' in code, (
        "徽标必须**常显**二选一（不是只在多选时出现）"
    )
    assert "input:is(" not in code, "别在 JS 里自己画圆点（样式归 app.css 末尾那块）"


def test_a_pending_item_that_vanishes_is_marked_closed() -> None:
    """后端把待答项收敛掉（超时/取消/作业结束）而人没答 ⇒ 标「问题已收起」，绝不假装答过。"""
    code = _code()
    assert 'if (!live[key]) markDone(key, T("agent.question.done"));' in code
    assert "el.classList.contains(\"-agent-question--done\")" in code, "已有终态不覆盖"


def test_index_loads_the_card_as_the_last_script() -> None:
    """末尾追加 ⇒ 既有 `index.html:<行>` 锚点零漂移（2026-09-24 起其后又有两个模块：脚本工作区、
       联网域名名单设置 —— 同样末尾追加；新模块落地时只需更新这一行断言）。"""
    html = _INDEX.read_text(encoding="utf-8")
    assert '<script src="/app/js/agent-question.js"></script>' in html
    scripts = re.findall(r"<script src=\"([^\"]+)\"></script>", html.split("</body>")[0])
    assert scripts and scripts[-1] == "/app/js/net-settings.js", f"最后一个 script 是 {scripts[-1] if scripts else None}"
    assert "/app/js/agent-question.js" in scripts[-3:], "待答卡模块仍在末尾区块里"


def test_card_styles_exist_and_reuse_tokens() -> None:
    """样式落 `app.css` 末尾追加块，且用既有令牌而不是硬编码颜色。"""
    css = _CSS.read_text(encoding="utf-8")
    block = css.rsplit("/* ===== 2026-09-23 追加：**待答卡**", 1)[1]
    for selector in (".-agent-question {", ".-agent-question-item", ".-agent-question-mode", ".-agent-question-opt", ".-agent-question-custom", ".-agent-question-state"):
        assert selector in block, f"样式缺失：{selector}"
    assert "var(--bg-tertiary)" in block and "var(--theme-color)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block), "不许硬编码颜色"


def test_i18n_keys_exist_in_both_locales() -> None:
    """`agent.question.*` 十个键在中英两份语言包里都在（缺一即漏出裸 key）。"""
    src = _card()
    used = set(re.findall(r'T\("(agent\.question\.[a-zA-Z]+)"', src))
    assert used == {"agent.question." + key for key in _KEYS}, f"卡片用到的键变了：{sorted(used)}"
    for locale, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        missing = [key for key in _KEYS if f"{key}:" not in text]
        assert not missing, f"{locale} 缺 agent.question 键：{missing}"
        assert re.search(r"question:\s*\{", text), f"{locale} 缺 `agent.question` 子对象"
