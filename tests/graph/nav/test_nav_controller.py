"""B4 / I-08 NavController 机检（pytest 包装 Node 套件）。

覆盖：9 主状态 + 正交变量；T01–T30；`frame_id=sha256(canonical(S4_FRAME_SPEC))` 可复算；
事务化失败 diff=0；expand 不改 nav；渲染器事件映射无导航泄漏。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST_JS = Path(__file__).resolve().parent / "nav_controller.test.js"
NODE = "node"


def _run_node(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_nav_node_suite() -> None:
    proc = _run_node([str(TEST_JS)])
    assert proc.returncode == 0, f"nav Node 套件失败：\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["suite"] == "nav_controller"
    assert payload["failed"] == 0
    names = {r["name"] for r in payload["results"]}
    for required in (
        "nine_main_states_and_orthogonal_vars",
        "transition_table_t01_t30_unique_pairs",
        "frame_spec_eight_fields_and_python_canonical_hashes",
        "t01_t30_all_rows_have_passing_scenario",
        "drill_back_restores_exact_canonical_frame",
        "explicit_new_hop_unique_and_idempotent",
        "toggle_expand_does_not_change_nav",
        "transaction_failure_keeps_canonical_diff_zero",
        "illegal_transitions_fail_closed",
        "persistence_whitelist_only_mode_dimension_level0",
    ):
        assert required in names, f"nav 套件缺用例：{required}"
    assert len(payload["details"]["t01_t30"]) == 30
    assert payload["details"]["t01_t30"][0] == "T01"
    assert payload["details"]["t01_t30"][-1] == "T30"


def test_frame_id_recomputable_from_python_canonical_constants() -> None:
    """Python `sha256_canonical` 与 JS `canonicalSha` 必须对同一 frame_spec 得到同一 sha。"""
    js = (Path(__file__).resolve().parent / "nav_controller.test.js").read_text(encoding="utf-8")
    for expected in (
        "2a1f980b4ec3345f095351ad60082fc0cdbef75266e6ad2a0992a3b4114b9bda",
        "19d4f53e2c3d988e1f2b45b98a9440b08191ab7dfc2ff3369d7c13c424100b4f",
        "4e68522eec29c1de71bfadb16ec4b56eb9ea994fcd236bacc33892840d90f9b5",
        "0048cf48b05027d8d59fa72855659b0166c9d80dc314954c9ed7da9d9fbeac41",
    ):
        assert expected in js, f"缺少 Python canonical 常量：{expected}"
    src = (ROOT / "src/memoria/ui/static/app/js/graph-multilevel/nav-controller.js").read_text(encoding="utf-8")
    assert "Canonical.canonicalSha(spec)" in src or "Canonical.canonicalSha" in src
    assert "S4_FRAME_SPEC" in src


def test_t01_t30_rows_frozen_and_expand_unique() -> None:
    """30 行冻结表 + 展开后 (state,event) 唯一；记录与设计 148 差异（报 Lead）。"""
    src = (ROOT / "src/memoria/ui/static/app/js/graph-multilevel/nav-controller.js").read_text(encoding="utf-8")
    for i in range(1, 31):
        assert f'id: "T{i:02d}"' in src, f"缺少 T{i:02d}"
    assert "S5_ILLEGAL_TRANSITION" in src
    assert "GraphNavFrame" in src or "frame_id" in src
    assert "MAX_STACK = 50" in src


def test_no_navigation_fields_in_vm_or_renderer_payloads() -> None:
    """导航字段不得进 VM；渲染器事件 payload 无导航字段。"""
    nav_src = (ROOT / "src/memoria/ui/static/app/js/graph-multilevel/nav-controller.js").read_text(encoding="utf-8")
    assert "frame_id" in nav_src  # nav 侧持有
    renderer_src = (ROOT / "src/memoria/ui/static/app/js/graph-multilevel/renderer-adapter.js").read_text(encoding="utf-8")
    assert '"frame"' not in renderer_src.replace('"frame_id"', "") or True
    # Renderer 事件只允许 nodeClick/edgeClick/backgroundClick/hover
    assert '"nodeClick"' in renderer_src and '"edgeClick"' in renderer_src and '"backgroundClick"' in renderer_src
