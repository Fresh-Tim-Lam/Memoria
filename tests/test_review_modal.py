"""R3a 复习界面（模态弹窗）—— 后端 UI RPC 与前端模块的钉子。

设计见 `docs/design/preview-render-refactor.md` 附 R3a / R3a-2。本文件钉三件事：
① **免审批路径只给 UI**：两条 RPC 是 `UIAPI` 方法、**不进 `KB_TOOL_NAMES` / 注册表** ⇒ agent 取不到；
   而 `review_grade` 工具仍 `read_only=False`（逐次审批），未被这条新路径削弱。
② UI RPC 复用同一份领域实现：取到期（只读）/ 评分（写前备份 + 可撤销 + 审计 + 失败分类）。
③ 前端模块与 i18n / index.html 的落点（末尾追加、`#btn-review` 同行追加）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"


class _Stub:
    """只实现 `_agent_kb` 的最小 UIAPI 替身（不建 DocumentService，避开其引导副作用）。"""

    def __init__(self, kb: Path) -> None:
        self._kb = str(kb)

    def _agent_kb(self, kb_path: str | None = None) -> str | None:  # noqa: ARG002
        return self._kb


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / ".memoria" / "agent").mkdir(parents=True)
    return root


def _card(cid: str, ctype: str = "basic", front: str = "F", back: str = "B") -> dict[str, Any]:
    return {
        "card_id": cid, "kp_id": "", "file": "", "type": ctype,
        "front": front, "back": back, "source": "test", "created_at": "2026-01-01T00:00:00Z",
    }


def _write_kb(kb: Path, cards: list[dict]) -> Path:
    """写入真实 `fsrs.py`（随包模板）+ cards.json，返回 review 目录。"""
    from memoria.app.runtime import resources_dir

    agent = kb / ".memoria" / "agent"
    review = agent / "review"
    review.mkdir(parents=True, exist_ok=True)
    (agent / "fsrs.py").write_bytes((resources_dir() / "agent-prompts" / "fsrs.py").read_bytes())
    (review / "cards.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "2026-01-01T00:00:00Z", "cards": cards}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return review


# ── ① 免审批路径只给 UI：两条 RPC 不在工具面 ────────────────────────────────────


def test_ui_rpc_exists_and_agent_cannot_reach_it(kb: Path) -> None:
    """两条 RPC 是 `UIAPI` 方法；**不在 `KB_TOOL_NAMES`**、注册表也解析不到 ⇒ agent 走不到这条免审批路。"""
    from memoria.presentation.api.ui import UIAPI
    from memoria.services.agent.tools import KB_TOOL_NAMES, ToolRegistry, build_kb_tools

    assert callable(getattr(UIAPI, "review_due_start", None))
    assert callable(getattr(UIAPI, "review_grade_one", None))
    assert "review_due_start" not in KB_TOOL_NAMES
    assert "review_grade_one" not in KB_TOOL_NAMES

    reg = ToolRegistry(build_kb_tools(str(kb)))
    assert reg.get("review_due_start") is None
    assert reg.get("review_grade_one") is None
    # agent 仍只能走 review_grade 工具 ⇒ 仍逐次审批（read_only=False）
    grade_tool = reg.get("review_grade")
    assert grade_tool is not None and grade_tool.read_only is False


# ── ② UI RPC：取到期（只读）─────────────────────────────────────────────────────


def test_review_due_start_returns_json_payload(kb: Path) -> None:
    from memoria.presentation.api.ui import _review_ui_due

    _write_kb(kb, [_card("c1"), _card("c2")])
    res = _review_ui_due(_Stub(kb), "2026-01-02", None)
    assert res["status"] == "ok"
    assert res["date"] == "2026-01-02"
    assert res["due"] == ["c1", "c2"]  # 新卡（progress 无记录）⇒ 到期
    assert res["count"] == 2
    assert res["cards"][0]["front"] == "F" and res["cards"][0]["type"] == "basic"
    # 只读：不产生 progress.json
    assert not (kb / ".memoria" / "agent" / "review" / "progress.json").exists()


def test_review_due_start_no_kb() -> None:
    from memoria.presentation.api.ui import _review_ui_due

    class _None:
        def _agent_kb(self, kb_path=None):  # noqa: ARG002
            return None

    res = _review_ui_due(_None(), None, None)
    assert res["status"] == "error" and res["category"] == "unavailable"


# ── ③ UI RPC：评分（写前备份 + 可撤销 + 审计 + 失败分类）─────────────────────────


def test_review_grade_one_writes_progress_with_backup_and_audit(kb: Path) -> None:
    from memoria.presentation.api.ui import _review_ui_grade

    _write_kb(kb, [_card("c1")])
    res = _review_ui_grade(_Stub(kb), "c1", 3, "2026-01-02", None)
    assert res["status"] == "ok" and res["card_id"] == "c1" and res["grade"] == 3

    review = kb / ".memoria" / "agent" / "review"
    prog = json.loads((review / "progress.json").read_text(encoding="utf-8"))
    assert prog["cards"]["c1"]["reps"] == 1
    assert prog["cards"]["c1"]["due"] == "2026-01-05"  # 首次 Good ⇒ 间隔 3 天

    # 写前备份：`backups/ui-review/<txid>/journal.json` 在（**可撤销点**）
    batches = list((kb / ".memoria" / "agent" / "backups" / "ui-review").glob("*/journal.json"))
    assert batches, "写前必须留下可撤销的备份批次"

    # 审计：sessions/ui-review.jsonl 含 `review/write`
    audit = (kb / ".memoria" / "agent" / "sessions" / "ui-review.jsonl").read_text(encoding="utf-8")
    assert "review/write" in audit


def test_review_grade_one_unreviewable_for_unknown_card(kb: Path) -> None:
    from memoria.presentation.api.ui import _review_ui_grade

    _write_kb(kb, [_card("c1")])
    res = _review_ui_grade(_Stub(kb), "NOPE", 3, "2026-01-02", None)
    assert res["status"] == "error" and res["category"] == "unreviewable"
    assert not (kb / ".memoria" / "agent" / "review" / "progress.json").exists()


def test_review_grade_one_unreviewable_for_disabled_card(kb: Path) -> None:
    from memoria.presentation.api.ui import _review_ui_grade

    card = _card("c1")
    card["disabled"] = True
    _write_kb(kb, [card])
    res = _review_ui_grade(_Stub(kb), "c1", 3, "2026-01-02", None)
    assert res["status"] == "error" and res["category"] == "unreviewable" and "禁用" in res["message"]


# ── ④ 前端模块 / i18n / index.html 落点 ─────────────────────────────────────────


def test_review_module_honors_no_optimistic_and_key_gates() -> None:
    src = (_APP / "js" / "review-modal.js").read_text(encoding="utf-8")
    assert "review_due_start" in src and "review_grade_one" in src
    # 冲突规避闸：IME + 输入控件聚焦 + 捕获阶段 Esc
    assert "isComposing" in src and "keyCode === 229" in src
    assert "isContentEditable" in src and "INPUT|TEXTAREA|SELECT" in src
    assert 'addEventListener("keydown", onKeyDown, true)' in src
    # 不做乐观更新：成功分支才 +1
    assert 'res.status === "ok"' in src and "S.done += 1" in src
    # cloze 挖空分词器
    assert "{{c" in src


def test_review_i18n_keys_present_in_both_locales() -> None:
    keys = ("button", "buttonTitle", "title", "dueCount", "progress", "flipHint", "empty",
            "doneAll", "donePartial", "unreviewedTitle", "unavailable", "loadFailed",
            "gradeFailed", "retry", "blankAria", "revealFailed")
    grades = ("again", "hard", "good", "easy")
    for name, rel in (("zh-CN", "i18n/zh-CN.js"), ("en", "i18n/en.js")):
        text = (_APP / rel).read_text(encoding="utf-8")
        assert "review: {" in text, f"{name} 缺 review 命名空间"
        for key in keys:
            assert f"{key}:" in text, f"{name} 缺 review.{key}"
        for key in grades:
            assert f"{key}:" in text, f"{name} 缺 review.grade.{key}"


def test_index_has_review_button_and_loads_module_last() -> None:
    html = (_APP / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-review"' in html and 'data-i18n="review.button"' in html
    scripts = re.findall(r'<script src="([^"]+)"></script>', html.split("</body>")[0])
    assert scripts and scripts[-1] == "/app/js/review-modal.js", f"最后一个 script 是 {scripts[-1] if scripts else None}"


# ── ⑤ legacyMath 开关：复习路径卡面不做"旧式公式"归一化 ─────────────────────────


def test_review_face_render_disables_legacy_math() -> None:
    """人实测缺陷：卡面正文若含 `=` / `_` / `^`、且中文占比低 ⇒ `MemoriaMathNormalize.isLegacyFormulaLine()`
    （`math-normalize.js:31-50`）判它为"旧式公式行" ⇒ **整行**包成 `$$…$$` ⇒ 渲染成 `mjx-container` **吞掉整句**
    （如 `The ratio x = 1 for this case.` 只剩 `Theratiox=1forthiscase.`）。

    修法（按任务口径，风险最小）：给预览管线加**显式、有名字**的 `legacyMath` 开关（**默认仍启用** ⇒ 零回归），
    **只**在复习路径关掉它（卡面是自然语言，本就该按普通文本渲染）；**不**收紧启发式本身（那会改动用户已有文档的渲染）。

    钉两处（等价于"复习卡面里不含 `mjx-container`"）：
    ① 复习路径 `paintFace()` 以 `{ legacyMath: false }` 调 `renderToElement`；
    ② 预览管线把 `legacyMath` 逐层透传 `normalizeBody(body, options)` → `MemoriaMathNormalize.normalize(body, options)`。
    ③ 实跑真实 `math-normalize.js`（node）：默认仍包 `$$…$$`（**默认行为未变**），`{ legacyMath:false }` 不包。
    """
    import shutil
    import subprocess

    review = (_APP / "js" / "review-modal.js").read_text(encoding="utf-8")
    assert "await pv.renderToElement(el, src, { legacyMath: false });" in review, (
        "复习卡面必须走 legacyMath:false"
    )
    mp = (_APP / "js" / "markdown-preview.js").read_text(encoding="utf-8")
    assert "function normalizeBody(body, options) {" in mp
    assert "return MemoriaMathNormalize.normalize(body, options);" in mp
    assert "const normalized = normalizeBody(body, options);" in mp

    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH")
    js = (_APP / "js" / "math-normalize.js").read_text(encoding="utf-8")
    script = (
        "global.window = {};\n" + js + "\nconst N = window.MemoriaMathNormalize;"
        "\nconsole.log(JSON.stringify(["
        "N.normalize('a_1 = b'),"
        "N.normalize('a_1 = b', {legacyMath:false}),"
        "N.normalize('The ratio x = 1 for this case.'),"
        "N.normalize('The ratio x = 1 for this case.', {legacyMath:false})"
        "]));"
    )
    proc = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    # 默认（不传 options）⇒ 仍当旧式公式包成 $$（**默认渲染行为零回归**）
    assert out[0] == "$$a_1 = b$$"
    assert out[2] == "$$The ratio x = 1 for this case.$$"
    # legacyMath:false ⇒ 原样（复习卡面走这条 ⇒ 不产生 mjx-container）
    assert out[1] == "a_1 = b"
    assert out[3] == "The ratio x = 1 for this case."


# ── ⑥ R4.2（2026-10-11）：答案隔离 + 后端判分 ────────────────────────────────────
# 人已批准：**答案不回前端**（UI 取卡剔除 `answer`/`accept`/`explain`；`options` 保留），判分放**后端**
# （`auto`：精确匹配 / `accept` 白名单命中；**不做归一化**）或交 agent（`judge: agent` ⇒ `unjudged`）；
# **agent 的 `review_due_list` 工具仍回答案**（agent 是判分方），该钉子见 `test_agent_scratch.py`。


def _answer_cards() -> list[dict]:
    """含 mcq（auto，带 options/answer/explain）、gapfill（auto，answer + accept 白名单）、short（agent）。"""
    return [
        {"card_id": "m1", "kp_id": "k", "file": "", "type": "mcq", "front": "f", "back": "b",
         "source": "t", "judge": "auto", "options": ["a", "b"], "answer": "a", "explain": "e-mcq"},
        {"card_id": "g1", "kp_id": "k", "file": "", "type": "gapfill", "front": "f", "back": "b",
         "source": "t", "judge": "auto", "answer": "cat", "accept": ["Cat"], "explain": "e-gap"},
        {"card_id": "s1", "kp_id": "k", "file": "", "type": "short", "front": "f", "back": "b",
         "source": "t", "judge": "agent", "answer": "some answer", "explain": "e-short"},
    ]


def test_review_due_start_hides_answer_fields_but_keeps_options(kb: Path) -> None:
    """**UI 取卡不带答案**：逐卡无 `answer`/`accept`/`explain`；`options`（选项文本）保留（mcq 可作答）。"""
    from memoria.presentation.api.ui import _review_ui_due

    _write_kb(kb, _answer_cards())
    res = _review_ui_due(_Stub(kb), "2026-01-02", None)
    assert res["status"] == "ok"
    by_id = {c["card_id"]: c for c in res["cards"]}
    assert set(by_id) == {"m1", "g1", "s1"}
    for card in by_id.values():
        assert "answer" not in card and "accept" not in card and "explain" not in card
    assert by_id["m1"]["options"] == ["a", "b"]  # 选项文本必须在 ⇒ mcq 能作答
    # 只读：不产生 progress.json
    assert not (kb / ".memoria" / "agent" / "review" / "progress.json").exists()


def test_review_submit_one_is_ui_only_not_a_tool(kb: Path) -> None:
    """`review_submit_one` 是 `UIAPI` 方法，**不进 `KB_TOOL_NAMES` / 注册表** ⇒ agent 取不到。"""
    from memoria.presentation.api.ui import UIAPI
    from memoria.services.agent.tools import KB_TOOL_NAMES, ToolRegistry, build_kb_tools

    assert callable(getattr(UIAPI, "review_submit_one", None))
    assert "review_submit_one" not in KB_TOOL_NAMES
    assert ToolRegistry(build_kb_tools(str(kb))).get("review_submit_one") is None


def test_review_submit_one_auto_verdict_and_reveal(kb: Path) -> None:
    """`auto` 判分：**精确匹配 / accept 白名单**；对错都揭晓 `answer`/`explain`；
    **不做归一化**（大小写/空白不同 ⇒ `wrong`，有意行为）；`judge: agent` ⇒ `unjudged`（不揭晓）。"""
    from memoria.presentation.api.ui import _review_ui_submit_one

    _write_kb(kb, _answer_cards())
    stub = _Stub(kb)
    # mcq 正确 / 错误（都揭晓 answer + explain）
    ok = _review_ui_submit_one(stub, "m1", "a", None, "2026-01-02", None)
    assert ok["verdict"] == "correct" and ok["answer"] == "a" and ok["explain"] == "e-mcq"
    bad = _review_ui_submit_one(stub, "m1", "b", None, "2026-01-02", None)
    assert bad["verdict"] == "wrong" and bad["answer"] == "a" and bad["explain"] == "e-mcq"
    # gapfill：answer 逐字精确命中
    assert _review_ui_submit_one(stub, "g1", None, "cat", "2026-01-02", None)["verdict"] == "correct"
    # gapfill：accept 白名单逐字命中（含大小写）
    assert _review_ui_submit_one(stub, "g1", None, "Cat", "2026-01-02", None)["verdict"] == "correct"
    # gapfill：白名单外的近似写法（大小写不同 / 多空白）⇒ **有意行为：wrong**（不归一化，交 agent 判）
    assert _review_ui_submit_one(stub, "g1", None, "CAT", "2026-01-02", None)["verdict"] == "wrong"
    assert _review_ui_submit_one(stub, "g1", None, "cat ", "2026-01-02", None)["verdict"] == "wrong"
    # judge: agent ⇒ 不在此判（unjudged，不揭晓）
    un = _review_ui_submit_one(stub, "s1", None, "x", "2026-01-02", None)
    assert un["verdict"] == "unjudged" and "answer" not in un and "explain" not in un


def test_review_submit_one_is_read_only(kb: Path) -> None:
    """只读：判分前后 `cards.json` 逐字节一致；不得建 `progress.json`。"""
    import hashlib

    from memoria.presentation.api.ui import _review_ui_submit_one

    _write_kb(kb, _answer_cards())
    review = kb / ".memoria" / "agent" / "review"
    before = hashlib.sha256((review / "cards.json").read_bytes()).hexdigest()
    _review_ui_submit_one(_Stub(kb), "m1", "a", None, "2026-01-02", None)
    after = hashlib.sha256((review / "cards.json").read_bytes()).hexdigest()
    assert before == after
    assert not (review / "progress.json").exists()


# ── ⑦ R4.3（2026-10-11）：作答交互（只 auto 三型）────────────────────────────────
# 范围收窄：mcq / gapfill / 带 accept|answer 的 cloze 才渲染作答区；basic/reverse/self-cloze/short/produce
# 维持现状。判分走后端只读入口 `review_submit_one`；界面只在作答后才揭晓 answer/explain（不乐观、不藏前端）。


def test_review_r43_mcq_renders_options_and_submits_via_rpc() -> None:
    """钉住：mcq 卡渲染选项按钮，提交走 `review_submit_one`（不是前端自判）。"""
    src = (_APP / "js" / "review-modal.js").read_text(encoding="utf-8")
    assert 'call("review_submit_one"' in src, "作答提交必须实际调后端只读判分入口（不是注释/前端自判）"
    for fn in ("isAutoCard", "answerUIHtml", "setupAnswerUI", "handleAutoKey", "submitAnswer", "revealVerdict"):
        assert f"function {fn}" in src, f"缺 R4.3 函数 {fn}"
    assert "-review-option" in src and "data-choice" in src, "mcq 必须建选项按钮"


def test_review_r43_answers_not_revealed_before_submit() -> None:
    """钉住：界面**只在** `review_submit_one` 返回后揭晓 `answer`/`explain`；绝不从卡面取（判分前无答案）。"""
    import re

    src = (_APP / "js" / "review-modal.js").read_text(encoding="utf-8")
    # 任何 `.answer` / `.explain` 访问都必须来自 RPC 返回 `res.*`（即卡面字段从不被读取）
    assert re.search(r"(?<!res)\.answer\b", src) is None, "不得从卡面读 answer"
    assert re.search(r"(?<!res)\.explain\b", src) is None, "不得从卡面读 explain"
    assert "res.answer" in src and "res.explain" in src
    # 作答区 HTML 构建函数体内不得渲染答案/解析
    seg = src[src.index("function answerUIHtml"): src.index("function optionKeyLabel")]
    assert "res.answer" not in seg and "answer:" not in seg and "explain" not in seg


def test_review_r43_auto_scope_and_only_rpc_writes() -> None:
    """钉住：作答交互门是 `judge:auto`；界面写路径只有两条 RPC，绝不直写 cards.json / progress.json。"""
    src = (_APP / "js" / "review-modal.js").read_text(encoding="utf-8")
    assert 'String(card.judge || "") === "auto"' in src, "作答交互只给 auto 判分卡"
    assert 'call("review_grade_one"' in src and 'call("review_submit_one"' in src, "写评分/判分只走 RPC 调用点"
    # 界面不做任何直接的网络/存储写入，只经应用门面 RPC
    for bad in ("fetch(", "XMLHttpRequest", "localStorage.setItem", "indexedDB"):
        assert bad not in src, f"界面不得直连 {bad}"
    # JS 语法（node --check 等价）
    import shutil
    import subprocess

    node = shutil.which("node")
    if node:
        proc = subprocess.run([node, "--check", str(_APP / "js" / "review-modal.js")],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr


def test_review_r43_i18n_keys_present_in_both_locales() -> None:
    keys = ("answerHint", "submit", "inputPlaceholder", "verdictCorrect", "verdictWrong",
            "verdictUnjudged", "revealAnswer", "explainLabel", "submitFailed")
    for name, rel in (("zh-CN", "i18n/zh-CN.js"), ("en", "i18n/en.js")):
        text = (_APP / rel).read_text(encoding="utf-8")
        for key in keys:
            assert f"{key}:" in text, f"{name} 缺 review.{key}"


# ── ⑧ R4.2 收尾（2026-10-11）：cloze 答案隔离（front 挖空，back 隐藏）──────────────
# 漏洞：cloze 答案天然写在 `front` 的 `{{cN::答案}}` 里，R4.2 原先只剔 `answer`/`accept`/`explain`
# ⇒ 网络响应可搜到答案。修法：`front` 挖空答案但**保留 `{{cN::}}` 标记**（界面靠它定位挖空）；
# `back`（schema 定义 = 完整原文，含明文答案）**整键不回前端**。`gapfill`/`mcq` 不受影响。


def _cloze_cards() -> list[dict]:
    return [
        {"card_id": "cz1", "kp_id": "k", "file": "", "type": "cloze",
         "front": "巴黎是{{c1::法国}}的首都", "back": "巴黎是法国的首都，答案是法国",
         "source": "t", "answer": "法国", "accept": ["法国"], "explain": "France 的解释"},
        {"card_id": "cz2", "kp_id": "k", "file": "", "type": "cloze",
         "front": "多空{{c1::aa}}与\n{{c2::bb}}", "back": "多空 aa 与 bb",
         "source": "t", "answer": "aa", "accept": ["aa"]},
    ]


def test_review_due_start_blank_cloze_front_answers_but_keeps_markers(kb: Path) -> None:
    """**cloze 答案隔离**：UI 取卡返回的 cloze `front` **不含答案文本**、且**仍含 `{{cN::}}` 标记**；
    `back`（完整原文含明文答案）整键不回前端；`answer`/`accept`/`explain` 仍被剔除。"""
    from memoria.presentation.api.ui import _review_ui_due, _review_ui_submit_one

    _write_kb(kb, _cloze_cards())
    by = {c["card_id"]: c for c in _review_ui_due(_Stub(kb), "2026-01-02", None)["cards"]}
    # 单空：答案文本被挖掉，标记与编号保留
    assert by["cz1"]["front"] == "巴黎是{{c1::}}的首都"
    assert "法国" not in by["cz1"]["front"] and "{{c1::}}" in by["cz1"]["front"]
    # 多空 / 跨行：两个答案都挖空，标记都保留
    assert by["cz2"]["front"] == "多空{{c1::}}与\n{{c2::}}"
    assert "aa" not in by["cz2"]["front"] and "bb" not in by["cz2"]["front"]
    assert "{{c1::}}" in by["cz2"]["front"] and "{{c2::}}" in by["cz2"]["front"]
    # back（完整原文）不回前端；answer/accept/explain 仍被剔除
    for card in by.values():
        assert "back" not in card
        assert "answer" not in card and "accept" not in card and "explain" not in card
    # 判分揭晓仍可用（读未改的 cards.json）
    out = _review_ui_submit_one(_Stub(kb), "cz1", None, "法国", "2026-01-02", None)
    assert out["verdict"] == "correct" and out["answer"] == "法国" and out["explain"] == "France 的解释"


def test_review_due_start_gapfill_mcq_back_untouched(kb: Path) -> None:
    """对照：`gapfill`/`mcq` 的 `back` **原样保留**（只 cloze 走挖空/隐藏），其答案在已剔除的 `answer` 字段。"""
    from memoria.presentation.api.ui import _review_ui_due

    gap = {"card_id": "g1", "kp_id": "k", "file": "", "type": "gapfill",
           "front": "The animal", "back": "b", "source": "t", "answer": "cat", "accept": ["Cat"]}
    mcq = {"card_id": "m1", "kp_id": "k", "file": "", "type": "mcq",
           "front": "Which?", "back": "b", "source": "t", "options": ["alpha", "beta"], "answer": "alpha"}
    _write_kb(kb, [gap, mcq])
    by = {c["card_id"]: c for c in _review_ui_due(_Stub(kb), "2026-01-02", None)["cards"]}
    assert by["g1"]["front"] == "The animal" and by["g1"]["back"] == "b"
    assert by["m1"]["back"] == "b" and by["m1"]["options"] == ["alpha", "beta"]
    for card in by.values():
        assert "answer" not in card and "accept" not in card


def test_review_ui_blank_cloze_tokenizer_edges() -> None:
    """分词器边界：多空 / 无 `::` 的 `{{cN}}` 原样 / 跨行 / 非字符串原样。"""
    from memoria.presentation.api.ui import _review_ui_blank_cloze

    assert _review_ui_blank_cloze("{{c1::a}}{{c2::b}}") == "{{c1::}}{{c2::}}"
    assert _review_ui_blank_cloze("{{c1}}") == "{{c1}}"  # 无 `::` ⇒ 原样保留
    assert _review_ui_blank_cloze("x{{c1::答\n案}}y") == "x{{c1::}}y"  # 跨行
    assert _review_ui_blank_cloze(None) is None


# ── ⑨ R4.3 收尾（2026-10-11）：按需揭晓（修 judge:self cloze 翻面看不到答案）──────────
# 取卡路径（`_review_ui_due`）把 cloze 的 `front` 挖空、`back` 剔除 ⇒ `judge:self` 的 cloze 没
# `answer`/`accept`，答案只在 `front` 的 `{{cN::答案}}` 里 ⇒ 翻面回填 token 时一片空白。
# 修法（人已拍板 方案 B）：新增 **UI 专用 · 只读** 入口 `review_reveal_one`（读未改的 cards.json 原样卡面），
# 前端**只对 cloze 卡 · 翻面时**调（不翻面不请求）；`auto` 卡揭晓仍走 `review_submit_one`。


def test_review_reveal_one_returns_full_raw_card_restores_cloze_answer(kb: Path) -> None:
    """**回归直证（后端层）**：取卡把 cloze 的 `front` 挖空、`back` 剔除；`review_reveal_one` 返回**原样**卡面
    ⇒ 前端翻面能回填出答案（`{{c1::法国}}`）。"""
    from memoria.presentation.api.ui import _review_ui_due, _review_ui_reveal

    _write_kb(kb, _cloze_cards())
    stub = _Stub(kb)
    due = {c["card_id"]: c for c in _review_ui_due(stub, "2026-01-02", None)["cards"]}
    # 取卡路径：答案被挖空、back 被剔除（回归的成因）
    assert due["cz1"]["front"] == "巴黎是{{c1::}}的首都" and "back" not in due["cz1"]
    # 揭晓入口：原样卡面（含明文答案）；token 回填后即为答案来源
    rev = _review_ui_reveal(stub, "cz1", "2026-01-02", None)
    assert rev["status"] == "ok" and rev["card_id"] == "cz1"
    assert rev["front"] == "巴黎是{{c1::法国}}的首都" and "法国" in rev["front"]
    assert rev["back"] == "巴黎是法国的首都，答案是法国"
    assert rev["answer"] == "法国" and rev["accept"] == ["法国"] and rev["explain"] == "France 的解释"
    # 多空 / 跨行也原样回来
    rev2 = _review_ui_reveal(stub, "cz2", None, None)
    assert rev2["front"] == "多空{{c1::aa}}与\n{{c2::bb}}"


def test_review_reveal_one_is_ui_only_not_a_tool(kb: Path) -> None:
    """`review_reveal_one` 是 `UIAPI` 方法，**不进 `KB_TOOL_NAMES` / 注册表** ⇒ agent 取不到。"""
    from memoria.presentation.api.ui import UIAPI
    from memoria.services.agent.tools import KB_TOOL_NAMES, ToolRegistry, build_kb_tools

    assert callable(getattr(UIAPI, "review_reveal_one", None))
    assert "review_reveal_one" not in KB_TOOL_NAMES
    assert ToolRegistry(build_kb_tools(str(kb))).get("review_reveal_one") is None


def test_review_reveal_one_is_read_only(kb: Path) -> None:
    """只读：揭晓前后 `cards.json` 逐字节一致；不得建 `progress.json`。"""
    import hashlib

    from memoria.presentation.api.ui import _review_ui_reveal

    _write_kb(kb, _cloze_cards())
    review = kb / ".memoria" / "agent" / "review"
    before = hashlib.sha256((review / "cards.json").read_bytes()).hexdigest()
    _review_ui_reveal(_Stub(kb), "cz1", "2026-01-02", None)
    after = hashlib.sha256((review / "cards.json").read_bytes()).hexdigest()
    assert before == after
    assert not (review / "progress.json").exists()


def test_review_reveal_one_unreviewable_for_unknown_card(kb: Path) -> None:
    """未找到 card_id ⇒ 结构化错误（不静默、不伪造空卡面）。"""
    from memoria.presentation.api.ui import _review_ui_reveal

    _write_kb(kb, _cloze_cards())
    res = _review_ui_reveal(_Stub(kb), "NOPE", None, None)
    assert res["status"] == "error" and res["category"] == "unreviewable"


def test_review_reveal_on_demand_only_on_flip_for_cloze() -> None:
    """**按需性（前端静态钉）**：`review_reveal_one` 只在 `revealForFlip` 里调；`revealForFlip` 只在 `flip()`
    里调 ⇒ 取卡（`open`/`showCard`）**不请求** reveal；且只对 cloze 卡（`auto` 卡不调）。"""
    src = (_APP / "js" / "review-modal.js").read_text(encoding="utf-8")
    assert src.count('call("review_reveal_one"') == 1, "揭晓 RPC 只应有一个调用点"
    # 调用点落在 flip()：flip 体里出现 revealForFlip(S.card)
    flip_seg = src[src.index("async function flip() {"): src.index("function dedupe")]
    assert "revealForFlip(S.card)" in flip_seg
    # 取卡 / 渲染路径不得请求 reveal
    open_seg = src[src.index("async function open() {"): src.index("function close()")]
    show_seg = src[src.index("async function showCard"): src.index("async function flip()")]
    for seg, tag in ((open_seg, "open"), (show_seg, "showCard")):
        assert 'call("review_reveal_one"' not in seg and "revealForFlip(" not in seg, f"{tag} 不得请求 reveal"
    # 只对 cloze 卡（auto 卡维持现状：不调 reveal）
    rf_seg = src[src.index("async function revealForFlip"): src.index("global.MemoriaReviewModal")]
    assert 'String(card.type || "") !== "cloze"' in rf_seg and "isAutoCard(card)" in rf_seg
    # 失败如实提示（不假装有答案）
    assert 'T("review.revealFailed"' in rf_seg
    # JS 语法（node --check 等价）
    import shutil
    import subprocess

    node = shutil.which("node")
    if node:
        proc = subprocess.run([node, "--check", str(_APP / "js" / "review-modal.js")],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
