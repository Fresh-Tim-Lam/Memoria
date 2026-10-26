"""task-167 专项测试：version.md「说明」行的「最近已发布版本」必须与实际 tag 一致。

为什么单独一个文件：默认 `pyproject.toml [tool.pytest.ini_options] testpaths=["tests"]`
不会收集 `scripts/agent/**`，所以本文件**不影响主门禁基线**（1516）；但它是可显式运行的
针对性回归：

    python -m pytest -q scripts/agent/test_release_preflight.py

覆盖（与 `--selftest` 的检查 7 fixture 互补，这里是 pytest 形态 + 解析器边界）：
  1. 正常态（说明行 = tag）⇒ PASS
  2. 说明行写旧版本、tag 更新 ⇒ FAIL 且 detail 同时给出两侧实际值
  3. 说明行写更新版本、tag 较旧 ⇒ FAIL（严格相等；历史 tag 请勿用本审计复核）
  4. 说明行格式改为无法解析 ⇒ FAIL（不是 SKIP/WARN）
  5. 缺「说明」行 ⇒ FAIL
  6. 缺 version.md ⇒ FAIL
  7. 解析器接受合理格式变体（加粗 / v 前缀 / 全角等号 / 中英文冒号 / 无空格）
  8. 发布模式不包含该检查（只有 --verify-published 跑）
  9. 审计模式端到端（临时 git 仓库 + tag）：说明行改旧 ⇒ FAIL；只改工作区恢复 ⇒ PASS
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_preflight as rp  # noqa: E402

TAG = "v0.4.9"
NOTE_OK = "| 说明 | 最近已发布 = **0.4.9**（2026-10-25，tag `v0.4.9` → `deadbeef`） |"


def _repo(tmp_path: Path, note_row: str | None = NOTE_OK,
          current: str = "0.4.9") -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "conventions").mkdir(parents=True)
    (root / "docs" / "conventions" / "version.md").write_text(
        rp._fixture_version_md(note_row, current=current), encoding="utf-8")
    return root


def _check(root: Path, tag: str = TAG) -> dict:
    return rp.eval_version_note_published(tag, root)


# ── 1–3：一致性判定 ────────────────────────────────────────────────


def test_note_matches_tag_passes(tmp_path: Path) -> None:
    r = _check(_repo(tmp_path))
    assert r["id"] == "VERSION-NOTE-PUBLISHED"
    assert r["level"] == "PASS", r["detail"]


def test_note_older_than_tag_fails_and_shows_both_values(tmp_path: Path) -> None:
    root = _repo(tmp_path, "| 说明 | 最近已发布 = **0.4.8**（旧版本） |")
    r = _check(root)
    assert r["level"] == "FAIL", r["detail"]
    assert "0.4.8" in r["detail"] and "v0.4.9" in r["detail"]
    assert "不一致" in r["detail"]


def test_note_newer_than_tag_fails_strict_equality(tmp_path: Path) -> None:
    root = _repo(tmp_path, "| 说明 | 最近已发布 = **0.4.10**（比被审计 tag 更新） |")
    r = _check(root)
    assert r["level"] == "FAIL", r["detail"]
    assert "0.4.10" in r["detail"] and "v0.4.9" in r["detail"]


# ── 4–6：解析失败必须 FAIL（task-167 的关键：不许静默跳过） ────────────


def test_unparseable_note_fails_not_skipped(tmp_path: Path) -> None:
    root = _repo(tmp_path, "| 说明 | 最近发布：见变更记录 |")
    r = _check(root)
    assert r["level"] == "FAIL", r["detail"]
    assert "无法解析" in r["detail"]
    assert r["level"] != "SKIP"


def test_missing_note_row_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, note_row=None)
    r = _check(root)
    assert r["level"] == "FAIL", r["detail"]
    assert "找不到" in r["detail"]


def test_missing_version_md_fails(tmp_path: Path) -> None:
    r = _check(tmp_path / "no-such-repo")
    assert r["level"] == "FAIL", r["detail"]
    assert "缺失" in r["detail"]


# ── 7：解析器格式变体 ──────────────────────────────────────────────


@pytest.mark.parametrize("note_row", [
    "| 说明 | 最近已发布 = **0.4.9**（tag `v0.4.9`） |",
    "| 说明 | 最近已发布 = v0.4.9 |",
    "| 说明 | 最近已发布：0.4.9 |",
    "| 说明 | 最近已发布: 0.4.9 |",
    "| 说明 | 最近已发布 ＝ **0.4.9** |",
    "|说明|最近已发布=0.4.9|",
    "| 说明 | 下一个待定；最近已发布 = 0.4.9（0.5.0 曾撤回） |",
])
def test_note_parser_accepts_reasonable_variants(tmp_path: Path, note_row: str) -> None:
    assert _check(_repo(tmp_path, note_row))["level"] == "PASS"


# ── 8：发布模式不含该检查（接入点必须在 verify-published） ─────────────


def test_release_mode_does_not_include_note_check(tmp_path: Path) -> None:
    root = _repo(tmp_path)  # 说明行故意写旧版本
    (root / "docs" / "conventions" / "version.md").write_text(
        rp._fixture_version_md("| 说明 | 最近已发布 = **0.4.8** |", current="0.4.9"),
        encoding="utf-8")
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    cfg = {
        "tag": TAG, "title": "Memoria v0.4.9", "body": rp.SELFTEST_BODY,
        "root": root, "mode": "release", "phase": "post", "offline": True,
        "release_meta": None, "review_dir": review_dir, "require_review": False,
    }
    checks, _ = rp.run_release_checks(cfg)
    assert "VERSION-NOTE-PUBLISHED" not in {c["id"] for c in checks}


# ── 9：审计模式端到端（真实 git 仓库 + tag） ─────────────────────────


def test_audit_mode_end_to_end(tmp_path: Path) -> None:
    env = rp._fixture_env(tmp_path)
    rp._push_tag(env)

    def audit() -> dict:
        checks, _ = rp.run_release_checks(rp._cfg(env, mode="audit", require_review=False))
        return next(c for c in checks if c["id"] == "VERSION-NOTE-PUBLISHED")

    assert audit()["level"] == "PASS"

    # 说明行写旧版本 ⇒ 必红
    (env["root"] / "docs" / "conventions" / "version.md").write_text(
        rp._fixture_version_md("| 说明 | 最近已发布 = **9.9.8** |"), encoding="utf-8")
    assert audit()["level"] == "FAIL"

    # 只改工作区（不 commit、不移动 tag）⇒ 恢复绿：证明读的是工作区文档
    (env["root"] / "docs" / "conventions" / "version.md").write_text(
        rp._fixture_version_md(rp.SELFTEST_NOTE_ROW), encoding="utf-8")
    assert audit()["level"] == "PASS"

    # 无法解析 ⇒ 必红
    (env["root"] / "docs" / "conventions" / "version.md").write_text(
        rp._fixture_version_md("| 说明 | 见变更记录 |"), encoding="utf-8")
    assert audit()["level"] == "FAIL"
