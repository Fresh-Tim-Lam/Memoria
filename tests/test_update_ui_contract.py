"""task-180：更新功能的前端/文案契约（静态，不启动浏览器）。

真机交互验证见 `artifacts/agent/verify/update-mechanism/`；
本测试只钉住**不可退化的契约**：UI 必须走这些 RPC、必须有手动替换四要素、
必须没有误导性安全措辞、i18n 双语键齐全。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
UPDATE_JS = APP / "js" / "update-settings.js"
GRAPH_JS = APP / "js" / "graph-settings.js"
UI_PY = ROOT / "src" / "memoria" / "presentation" / "api" / "ui.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_update_ui_calls_the_required_rpcs() -> None:
    src = _text(UPDATE_JS)
    for fn in (
        "get_update_state",
        "check_for_update",
        "start_update_download",
        "get_update_download_status",
        "cancel_update_download",
        "open_update_folder",
        "save_ui_settings",
    ):
        assert f'call("{fn}"' in src, f"update UI 必须调用 {fn}"


def test_update_ui_has_manual_replacement_contract_without_auto_replace() -> None:
    src = _text(UPDATE_JS)
    # 四要素：关闭进程 / 只换应用文件夹 / 配置目录 / lite 别删 hf
    for key in ("update.step1", "update.step2", "update.step3", "update.stepLite", "update.noAuto"):
        assert key in src, f"缺少手动替换说明键 {key}"
    assert "hf/" in src or "update.stepLite" in src
    # 不做自动替换：代码里不得出现“调用后端替换/安装”的入口
    assert "replace_app" not in src
    assert "install_update" not in src


def test_update_ui_has_no_misleading_security_claims() -> None:
    # 只检查**界面文案/代码字符串**；文件头注释允许写“禁止这些词”的纪律说明。
    lines = [
        line
        for line in _text(UPDATE_JS).splitlines()
        if not line.lstrip().startswith(("*", "//", "/*"))
    ]
    src = "\n".join(lines)
    for forbidden in ("防篡改", "已签名", "安全"):
        assert forbidden not in src, f"更新 UI 不得出现误导性措辞：{forbidden}"


def test_settings_tab_is_registered_and_lazy_loaded() -> None:
    gs = _text(GRAPH_JS)
    assert 'data-settings-tab="update"' in gs
    assert "/app/js/update-settings.js" in gs


def test_update_i18n_has_both_languages_and_correct_wording() -> None:
    zh = _text(APP / "i18n" / "zh-CN.js")
    en = _text(APP / "i18n" / "en.js")
    for key in ("settings.tab", "update: {", "verifiedManifest", "stepLite", "noAuto"):
        assert key in zh, f"zh-CN 缺少 {key}"
    for key in ("update: {", "verifiedManifest", "stepLite", "noAuto"):
        assert key in en, f"en 缺少 {key}"
    assert "已校验包结构与完整性（不含数字签名）" in zh
    assert "Package structure and integrity verified (no digital signature)" in en


def test_backend_rpc_methods_exist() -> None:
    src = _text(UI_PY)
    for name in (
        "def get_update_state(",
        "def check_for_update(",
        "def start_update_download(",
        "def get_update_download_status(",
        "def cancel_update_download(",
        "def open_update_folder(",
    ):
        assert name in src, f"ui.py 缺少 RPC {name}"
