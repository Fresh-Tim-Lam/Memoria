"""脚本工作区设置（三个键）的契约钉子：`js/scratch-settings.js` + RPC `agent_script_settings`。

背景（人 2026-09-24 拍板）：AG59 落了 `script_interpreter` / `script_use_bundled` / `script_timeout_s`
三个键，但**只能手改 `config/agent.json`**（台账里如实记着"暂无界面"）⇒ 本轮补上设置页那份界面。

钉住五件事：

1. **只读面不吃知识库**：解释器是**机器级**设置 ⇒ 新 RPC 不收 `kb_path`（没开库也要能改），
   也不并进 `_agent_config_view()`（那是中段函数，加键会推位 `ui.py` 中段锚点）；
2. **解析结果如实回四态**（`explicit` / `bundled` / `system` / `none`）；填了不存在的路径 ⇒ 报
   `error` 而**不静默回落**（`resolve_interpreter()` 的既有口径）；配置读不到 ⇒ 结构化
   `config_error`，不装作没事；
3. 前端**只消费两条 RPC**（`agent_script_settings` / `agent_save_config`）、只走 `MemoriaApp`
   门面，**不碰** `agent_scratch_*`（工作区是库内容，设置页不该读它）、不自己拼库路径；
4. 三个键名与 `llm/config.py` 的键表一致（防拼写漂移）；
5. 文案中英成对、样式用既有令牌（无硬编码颜色）。
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from memoria.presentation.api import ui as ui_mod
from memoria.presentation.api.ui import UIAPI
from memoria.services.agent import scratch as scratch_mod

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_MODULE = _APP / "js" / "scratch-settings.js"
_INDEX = _APP / "index.html"
_CSS = _APP / "css" / "app.css"
_CONFIG = _ROOT / "src" / "memoria" / "services" / "agent" / "llm" / "config.py"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}

#: 三个键（与 `llm/config.py::_JSON_KEYS` 同名；前端只在一处声明）。
KEYS = ("script_interpreter", "script_use_bundled", "script_timeout_s")
_COPY = (
    "title",
    "interpreterLabel",
    "interpreterPh",
    "useBundledLabel",
    "timeoutLabel",
    "hint",
    "resolved",
    "noInterpreter",
    "badPath",
    "bundledPresent",
    "bundledMissing",
    "timeoutRange",
    "clamped",
    "badTimeout",
    "noBridge",
    "saved",
    "failed",
)


def _code() -> str:
    return _MODULE.read_text(encoding="utf-8")


def _code_only() -> str:
    """去掉注释后的源码（注释里允许提"手改 `config/agent.json`"，那不是拼路径）。"""
    text = re.sub(r"/\*[\s\S]*?\*/", "", _code())
    return re.sub(r"^[ \t]*//.*$", "", text, flags=re.M)


def _fake_config(**patch: object) -> SimpleNamespace:
    """假配置：只带本 RPC 会 `getattr` 的三个键（duck-typing，不必构造完整 `AgentConfig`）。"""
    base: dict[str, object] = {"script_interpreter": "", "script_use_bundled": True, "script_timeout_s": 0.0}
    base.update(patch)
    return SimpleNamespace(**base)


def _settings(monkeypatch, **patch: object) -> dict:
    """把 `load_config` 换成假配置后调一次 RPC（函数内是**调用期**导入 ⇒ monkeypatch 生效）。"""
    monkeypatch.setattr("memoria.services.agent.llm.config.load_config", lambda *_a, **_k: _fake_config(**patch))
    return ui_mod._agent_script_settings(None)


# ── ① RPC 形状与四态 ──────────────────────────────────────────────────────────


def test_rpc_is_registered_and_takes_no_knowledge_base(monkeypatch) -> None:
    """注册在 `UIAPI` 上、**不收** `kb_path`（解释器是机器级设置 ⇒ 没开库也能改）。"""
    assert UIAPI.agent_script_settings is ui_mod._agent_script_settings
    res = _settings(monkeypatch)
    assert res["status"] == "ok"
    assert {
        "interpreter",
        "use_bundled",
        "timeout_s",
        "default_timeout_s",
        "resolved",
        "bundled_dir",
        "error",
        "code",
        "limits",
    } <= set(res)
    assert res["code"] == scratch_mod.CODE_NO_INTERPRETER
    assert res["limits"] == {
        "min_timeout_s": float(scratch_mod.MIN_TIMEOUT_S),
        "max_timeout_s": float(scratch_mod.MAX_TIMEOUT_S),
    }


def test_reports_the_three_keys_with_the_documented_defaults(monkeypatch) -> None:
    """配置里没写（`0` / 缺省）⇒ 超时回 `DEFAULT_TIMEOUT_S`、内置开关默认开。"""
    res = _settings(monkeypatch)
    assert res["timeout_s"] == float(scratch_mod.DEFAULT_TIMEOUT_S)
    assert res["use_bundled"] is True and res["interpreter"] == ""
    other = _settings(monkeypatch, script_interpreter="C:\\py\\python.exe", script_use_bundled=False, script_timeout_s=12.5)
    assert other["timeout_s"] == 12.5
    assert other["use_bundled"] is False
    assert other["interpreter"] == "C:\\py\\python.exe", "RPC 只透传（trim / 类型归一归 `config.py` 的读侧管）"


def test_resolution_source_is_honest(monkeypatch) -> None:
    """关掉内置 ⇒ 来源必不是 `bundled`；测试本身跑在 python 上 ⇒ 至少能回落到 `system`。"""
    res = _settings(monkeypatch, script_use_bundled=False)
    assert res["resolved"]["source"] == "system"
    assert res["resolved"]["path"] and res["error"] == ""
    assert res["bundled_dir"] == (scratch_mod.bundled_dir() or ""), "如实报内置目录（没有则空串）"


def test_missing_explicit_path_errors_instead_of_falling_back(monkeypatch) -> None:
    """填了不存在的路径 ⇒ 带 `error` 回来、`source == "none"` —— **不静默回落**到系统解释器。"""
    res = _settings(monkeypatch, script_interpreter=str(Path("no-such-dir") / "python-nope.exe"))
    assert res["status"] == "ok" and res["error"], "要有可读的错误，不能装作没事"
    assert res["resolved"] == {"path": "", "source": "none"}
    assert res["code"] == scratch_mod.CODE_NO_INTERPRETER


def test_config_failure_is_reported_not_swallowed(monkeypatch) -> None:
    """配置读不到（真机踩过 UTF-8 BOM）⇒ 结构化 `config_error`，让设置页能照实显示。"""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("Unexpected UTF-8 BOM")

    monkeypatch.setattr("memoria.services.agent.llm.config.load_config", boom)
    res = ui_mod._agent_script_settings(None)
    assert res["status"] == "error" and res["code"] == "config_error" and "BOM" in res["message"]


# ── ② 前端模块：只走两条 RPC + 门面 ───────────────────────────────────────────


def test_module_only_talks_through_two_rpcs_and_the_app_facade() -> None:
    code = _code()
    assert "global.MemoriaScriptSettings = { mount, refresh, render };" in code
    for method in ("agent_script_settings", "agent_save_config"):
        assert f'call("{method}"' in code, method
    assert "agent_scratch_" not in code, "设置页不该去读工作区（那是库内容，归工作区面板）"
    assert not re.search(r"\.memoria|fetch\(", _code_only()), "不自己拼库路径、不直连网络"
    assert "MemoriaApp" in code, "只用应用门面（call / T / esc / showFlash*）"


def test_mounts_into_the_existing_form_instead_of_rebuilding_it() -> None:
    """DOM 自建后**追加**进 `#agent-settings`（不重建那个表单 ⇒ 既有字段 id 与事件绑定原样保留）。"""
    code = _code()
    assert 'document.getElementById("agent-settings")' in code
    assert "box.appendChild(wrap);" in code
    assert "wrap.id = ID;" in code
    assert 'wrap.className = "-script-settings";' in code


def test_three_keys_match_the_backend_key_table() -> None:
    code = _code()
    config = _CONFIG.read_text(encoding="utf-8")
    for key in KEYS:
        assert f'"{key}"' in code, f"前端缺键名 {key}"
        assert f'"{key}"' in config, f"`llm/config.py` 的键表缺 {key}"


def test_index_loads_the_module_as_the_last_script() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert '<script src="/app/js/scratch-settings.js"></script>' in html
    scripts = re.findall(r"<script src=\"([^\"]+)\"></script>", html.split("</body>")[0])
    assert scripts[-1] == "/app/js/nav-predictor.js", f"最后一个 script 是 {scripts[-1]}"


def test_the_three_input_ids_match_what_the_module_looks_up() -> None:
    """`mount()` 里写死的 `id` 与 `field()` / `querySelector` 的查找键必须逐一对上
    （最容易出的 DOM bug 就是这两处拼错，而它不会报错、只会静默少一个控件）。"""
    code = _code()
    for name in ("interpreter", "bundled", "timeout"):
        assert f'id="-script-{name}"' in code, f"markup 里缺 -script-{name}"
        assert f'field("{name}")' in code, f"没有查找 -script-{name}"
    for hook in ("title", "interpreter", "bundled", "timeout", "hint", "resolved"):
        assert f'data-script="{hook}"' in code, f"markup 里缺 data-script={hook}"
        assert f"[data-script='{hook}']" in code, f"没有回填 data-script={hook}"


def test_copy_exists_in_both_locales() -> None:
    for name, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        assert re.search(r"script:\s*\{", text), f"{name} 缺 settings.script 子对象"
        for key in _COPY:
            assert f"{key}:" in text, f"{name} 缺 {key}"
        for source in ("explicit", "bundled", "system", "none"):
            assert f"{source}:" in text, f"{name} 缺 source.{source}"
    assert '"settings.script.source." + source' in _code(), "四态键是拼出来的，这里钉住拼法"


def test_styles_use_tokens_and_never_hardcode_colors() -> None:
    css = _CSS.read_text(encoding="utf-8")
    block = css.rsplit("/* ===== 2026-09-24 追加：脚本工作区设置的三个键", 1)[1]
    for selector in (".-script-settings {", ".-script-switch {", ".-script-hint,", ".-script-resolved--bad {"):
        assert selector in block, f"样式缺失：{selector}"
    assert "var(--text-secondary)" in block and "var(--warning)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block), "不许硬编码颜色"
