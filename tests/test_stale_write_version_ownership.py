"""task-164 回归守卫：保存 version 的「归属校验」与自伤 stale 自愈必须在位。

背景：v0.4.9 真机误报（无外部写者却弹「文件已被改动」）的真因是
    保存响应回来时**无条件** `state.doc.version = res.version`；
    若保存进行中切了文件（A→B），A 的新 version 被写进 B，B 下次保存用错 base_version ⇒ 误报。
真机证据：artifacts/agent/verify/todo/stale-write-false-positive/
    · stale-verify-before.json：修复前 A 阶段 versionMatchesDisk=false 且 B 保存弹框（无外部写者）
    · stale-verify-after.json ：修复后 A 阶段 true、B 保存 ok、C 6/6 version==disk
    · 真报不丢：外部进程真改盘 ⇒ stale_write=1 且对话框出现（同一 JSON B 阶段）

本测试是**结构回归**（真实行为由上面的真机脚本保证），锁三条不变量：
  ① 成功分支只在「同一 path + 同一 doc 对象」时回写 version；
  ② 同一时刻只有一个 save_document 在飞（_saveInFlight 串行化）；
  ③ stale 的 current_version 若是我方写出的版本 ⇒ 自愈重试，而不是弹框。
"""

from __future__ import annotations

from pathlib import Path

APP_JS = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app" / "js" / "app.js"


def _src() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_success_branch_guards_version_ownership():
    src = _src()
    # ① 成功分支必须同时校验 path 与 doc 对象身份
    assert "state.currentPath === savePath && state.doc === saveDoc" in src, (
        "task-164 回归：syncToDisk 成功分支丢失 version 归属校验（会复现跨文件污染误报）"
    )
    # 旧的无条件写法必须已被删除（保存期间切换文件时它会污染新文档的 version）
    assert "if (state.doc && res.version) state.doc.version = res.version;" not in src, (
        "task-164 回归：发现旧的无条件 version 回写（跨文件污染真因）"
    )
    # 保存前必须记住 savePath/saveDoc 快照
    assert "const savePath = state.currentPath;" in src
    assert "const saveDoc = state.doc;" in src


def test_save_serialization_in_place():
    src = _src()
    # ② 串行化：in-flight 时等待上一个保存，再决定是否继续
    assert "_saveInFlight" in src, "task-164 回归：保存串行化缺失"
    assert "try { await _saveInFlight; }" in src, "task-164 回归：in-flight 等待逻辑缺失"
    assert "_syncToDiskOnce" in src, "task-164 回归：syncToDisk 单次执行体缺失"


def test_self_inflicted_stale_self_heals_not_dialog():
    src = _src()
    # ③ 自伤识别 + 上限 + 重试（不弹框）；外部写者版本不在集合里 ⇒ 仍走 onSaveFailed
    assert "_wasWrittenByUs" in src
    assert "_noteWrittenVersion" in src
    assert "res.code === \"stale_write\" && _wasWrittenByUs(savePath, res.current_version)" in src
    assert "_selfHealCount < 2" in src, "task-164 回归：自愈必须有上限，不能无限重试"
    assert "window.__memoriaNoteWrittenVersion" in src


def test_force_path_also_guards_ownership_and_records_version():
    src = _src()
    # 强制保存（“以我为准”）也必须只写回所属文档，并登记 version 供自伤识别复用
    assert "st.currentPath === path" in src, "task-164 回归：force 分支丢失文档归属校验"
    assert "window.__memoriaNoteWrittenVersion?.(path, r.version)" in src
