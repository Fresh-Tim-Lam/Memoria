"""wikilink 扫描与"字样式命令"的边界（2026-09-22 修）：`[[\\…]]` **不是**链接。

真机报障的根因：`link_resolver._WIKILINK_RE` 的目标段原先允许反斜杠 ⇒ `[[\\h|…]]` / `[[\\c:red|…]]`
被当成 wikilink，`target_id` 成了 `\\h:green` 这种"目标"，构建期写进 sidecar `links[]` 且 `targets: []`
⇒ 每条贡献一个 `link_no_targets` 警告（真机库实测 5 条），`audit_references` 也把它们全报成断链。

语法权威 = [preview-formats.md §4.2](../docs/reference/preview-formats.md)：「`[[\\…\\|文本]]` 是**字样式命令**，
`]]` 收尾、不嵌套」（`\\h` / `\\h:bg` / `\\h:bg:fg` / `\\c:color` / `\\s:size` / `\\b` / `\\i` / `\\u` / `\\sup` / `\\sub`）。

钉住两件事：
① **扫描侧**：`scan_wikilinks()` / `parse_wikilink()` 一律**不认**字样式命令（新数据不再变脏）；
② **构建侧**：`sync_file_sidecar_links()` 顺手**清掉存量**（`anchor_text` 以 `\\` 开头的 links[] 条目）——
   构建只增不删，不打这个补丁旧库里的脏条目永远留着；判据刻意收窄到"只看 `anchor_text` 前缀"，
   **不误删**"目标尚未创建"的合法虚链（那种 `targets: []` 是有意义的待绑定状态）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria.graph.kb_build import build_knowledge_base, sync_file_sidecar_links
from memoria.services.link_resolver import parse_wikilink, scan_wikilinks
from memoria.storage.sidecar import load_sidecar_for_md

#: 正文第 3 行同时含"字样式命令"与"真链接"：前者必须被忽略、后者必须被收。
A_MD = "# A 文档\n\n见 [[\\h|高亮文字]] 与 [[target-kp|正式链接]]。\n"
B_MD = "# B 文档\n\n目标正文。\n"
A_LINE3 = "见 [[\\h|高亮文字]] 与 [[target-kp|正式链接]]。"


def _sidecar(rel: str, kp_id: str, start: str, end: str, end_line: int, links: str = "links: []") -> str:
    return "\n".join(
        [
            "schema_version: 1",
            f"file: {rel}",
            "knowledge_points:",
            f"- id: {kp_id}",
            f"  name: {kp_id}",
            "  range:",
            "    start:",
            f"      snippet: '{start}'",
            "      line_hint: 1",
            "    end:",
            f"      snippet: '{end}'",
            f"      line_hint: {end_line}",
            links,
            "edges: []",
            "",
        ]
    )


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria" / "sidecars" / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8")
    (root / "notes" / "b.md").write_text(B_MD, encoding="utf-8")
    (root / ".memoria" / "sidecars" / "notes" / "a.memoria.yaml").write_text(
        _sidecar("notes/a.md", "a-kp", "# A 文档", A_LINE3, 3), encoding="utf-8"
    )
    (root / ".memoria" / "sidecars" / "notes" / "b.memoria.yaml").write_text(
        _sidecar("notes/b.md", "target-kp", "# B 文档", "目标正文。", 3), encoding="utf-8"
    )
    return root


# ── ① 扫描侧：字样式命令不是链接 ──────────────────────────────────────────────


def test_scan_skips_style_commands_and_keeps_real_links() -> None:
    body = "见 [[\\h|高亮]]、[[\\c:red|红字]]、[[\\s:20px|大字]] 与 [[a-kp]]、[[b-kp#extend|扩展]]。"
    assert [(wl["target_id"], wl["display"]) for wl in scan_wikilinks(body)] == [
        ("a-kp", None),
        ("b-kp", "扩展"),
    ]
    assert scan_wikilinks("[[\\h|只有样式命令]]") == []


@pytest.mark.parametrize(
    "raw",
    ["[[\\h|x]]", "[[\\h:bg:fg|x]]", "[[\\c:red|x]]", "[[\\s:20px|x]]", "[[\\u|x]]", "[[\\sub|x]]"],
)
def test_parse_wikilink_rejects_style_commands(raw: str) -> None:
    assert parse_wikilink(raw) is None


def test_parse_wikilink_still_accepts_real_links() -> None:
    assert parse_wikilink("[[a-kp]]")["target_id"] == "a-kp"
    assert parse_wikilink("[[a-kp|显示]]")["display"] == "显示"


# ── ② 构建侧：不再新增，并清掉存量 ────────────────────────────────────────────


def test_build_does_not_turn_a_style_command_into_a_link(kb: Path) -> None:
    """正文里那条 `[[\\h|高亮文字]]` **不得**进 `links[]`（修前它会以 `targets: []` 落盘）。"""
    report = build_knowledge_base(str(kb))
    assert report["status"] == "ok", report
    sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [ln.get("anchor_text") for ln in sidecar.get("links") or []] == ["target-kp"]
    assert [(ln.get("anchor_text"), ln.get("targets")) for ln in sidecar.get("links") or []] == [
        ("target-kp", ["target-kp"])
    ]
    assert report["totals"]["pruned_style_links"] == 0


def test_sync_prunes_stale_style_command_entries_but_keeps_dangling_ones(kb: Path) -> None:
    """存量清理：`anchor_text` 以 `\\` 开头的条目被删；`targets: []` 的**合法虚链**必须留着。"""
    sidecar = {
        "schema_version": 1,
        "file": "notes/a.md",
        "knowledge_points": [],
        "links": [
            {"anchor_text": "\\h:green", "targets": [], "instances": [{"line": 3}]},
            {"anchor_text": "\\c:red", "targets": [], "instances": [{"line": 3}]},
            {"anchor_text": "not-created-yet", "targets": [], "instances": [{"line": 3}]},
        ],
    }
    sidecar["knowledge_points"] = [
        {
            "id": "a-kp",
            "name": "甲",
            "range": {"start": {"snippet": "# A 文档", "line_hint": 1}, "end": {"snippet": A_LINE3, "line_hint": 3}},
        }
    ]
    sync = sync_file_sidecar_links("notes/a.md", A_MD, sidecar, resolve_target_kp=lambda tid: None)
    assert sync["pruned_style_links"] == 2
    assert sync["changed"] is True
    assert [ln.get("anchor_text") for ln in sidecar["links"]] == ["not-created-yet", "target-kp"], (
        "虚链留着、样式命令条目清掉、真链接照常收进来"
    )


def test_build_clears_pre_existing_dirty_sidecar(kb: Path) -> None:
    """端到端：脏 sidecar（含样式命令条目）跑一次「构建」⇒ 校验**零** `link_no_targets`。"""
    dirty = (
        _sidecar("notes/a.md", "a-kp", "# A 文档", A_LINE3, 3)
        .replace(
            "links: []",
            "\n".join(
                [
                    "links:",
                    "- anchor_text: \\h:green",
                    "  targets: []",
                    "  instances:",
                    "  - line: 3",
                ]
            ),
        )
    )
    (kb / ".memoria" / "sidecars" / "notes" / "a.memoria.yaml").write_text(dirty, encoding="utf-8")

    report = build_knowledge_base(str(kb))
    assert report["status"] == "ok", report
    assert report["totals"]["pruned_style_links"] == 1
    sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [ln.get("anchor_text") for ln in sidecar.get("links") or []] == ["target-kp"]
    from memoria.storage.sidecar_validate import validate_sidecar

    body = (kb / "notes" / "a.md").read_text(encoding="utf-8").splitlines()
    validation = validate_sidecar(sidecar, "notes/a.md", body)
    assert [w.get("code") for w in validation.get("warnings") or []] == []
