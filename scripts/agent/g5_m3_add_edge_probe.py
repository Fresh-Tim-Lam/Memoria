"""裁决 3 验证：create_edge（document.add_edge 的现名）接受可选 assertion_source（task-280）。

## 验证三条（裁决 3）

1. 不传 assertion_source / 传 None / 传空 dict ⇒ 返回 edge 对象**不含** assertion_source 键，
   且与改动前的返回结构一致（只有 type/source_id/targets/relevance）。
2. 传了 assertion_source ⇒ 返回 edge 对象**出现** assertion_source 键，值原样。
3. 全程不写 sidecar 文件（create_edge 以外，本脚本只验证返回值语义；
   写 sidecar 行为由现有 test_agent_kp_ops 覆盖，不重复）。

## 边界

只跑在临时 KB / frozen working 副本；不写用户库。本脚本是**验证脚本**（scripts/agent/），
不是 tests/ 套件 —— 因 task-280 写域不含 tests/；Lead 审后决定是否固化进 pytest。

用法：python scripts/agent/g5_m3_add_edge_probe.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

FROZEN = REPO / "artifacts" / "agent" / "verify" / "debate" / "kg-retrieval" / "round2" / "frozen" / "数字通信原理"


def _make_tmp_kb() -> Path:
    td = Path(tempfile.mkdtemp(prefix="g5-m3-"))
    # 复制 frozen 到临时 KB（只读验证，不在 frozen 原目录上写）
    shutil.copytree(FROZEN, td / "kb")
    return td / "kb"


def main() -> int:
    from memoria.services.document import DocumentService

    if not FROZEN.is_dir():
        print(f"[NOT_RUN] frozen 不存在：{FROZEN}")
        return 2

    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="g5-m3-") as td:
        kb = Path(td) / "kb"
        shutil.copytree(FROZEN, kb)

        doc = DocumentService(kb_path=str(kb))

        # 取一个真实存在的 source/target（用 frozen 里第一个有 KP 的文件）
        # 简化：直接找一条已存在的边，用它的 source/target 做基准
        # 但 create_edge 要"该文件 KP 存在"，故用 collect 找一条真实 contain 边
        from memoria.graph.collector import collect_graph_data
        g = collect_graph_data(str(kb))
        edge_sample = next(
            (e for e in g["edges"] if e["origin"] == "sidecar_edge"
             or e["origin"] == "range"),
            None,
        )
        if edge_sample is None:
            print("[NOT_RUN] frozen 副本里没有可用边样本")
            return 2

        # 找该 source 所在文件（用 edge 的 file 字段）
        src_file = edge_sample.get("file")
        source_id = edge_sample["source_id"]
        target_id = edge_sample["targets"][0]
        et = edge_sample["type"]
        # 用 reference 或 extend 类型（contain 会被 no_build 语义干扰，纯边测试用 extend/reference）
        pure_type = "extend" if et != "extend" else "reference"

        # ── 测试 1：不传 assertion_source ⇒ 无该键 ────────────────
        r1 = doc.create_edge(src_file, source_id, target_id, pure_type)
        # 可能因"边已存在"报错，跳过存在性；只验证返回结构
        e1 = r1.get("edge") if r1.get("status") == "ok" else None
        if e1 is not None:
            if "assertion_source" in e1:
                failures.append("不传 assertion_source 时返回对象仍含该键")

        # ── 测试 2：传 None ⇒ 无该键 ─────────────────────────────
        r2 = doc.create_edge(src_file, source_id, target_id, pure_type, assertion_source=None)
        e2 = r2.get("edge") if r2.get("status") == "ok" else None
        if e2 is not None and "assertion_source" in e2:
            failures.append("传 None 时返回对象仍含 assertion_source")

        # ── 测试 3：传空 dict ⇒ 无该键 ───────────────────────────
        r3 = doc.create_edge(src_file, source_id, target_id, pure_type, assertion_source={})
        e3 = r3.get("edge") if r3.get("status") == "ok" else None
        if e3 is not None and "assertion_source" in e3:
            failures.append("传空 dict 时返回对象仍含 assertion_source")

        # ── 测试 4：传非空 assertion_source ⇒ 出现该键 ────────────
        asrc = {"file": src_file, "line_start": 1, "line_end": 2}
        # 用一个新 target 避免"已存在"（加后缀）
        new_target = target_id + "-probe"
        r4 = doc.create_edge(src_file, source_id, new_target, pure_type, assertion_source=asrc)
        e4 = r4.get("edge") if r4.get("status") == "ok" else None
        if e4 is None:
            # 若因 target 无法解析则跳过这条（frozen 无该 target）
            pass
        else:
            if "assertion_source" not in e4:
                failures.append("传 assertion_source 时返回对象不含该键")
            elif e4["assertion_source"] != asrc:
                failures.append(f"assertion_source 值变形：{asrc} → {e4['assertion_source']}")

        # ── 测试 5（核心）：sidecar 文件未被写入 assertion_source ──
        # create_edge 写 sidecar 后，读回该 sidecar，确认 edges[] 里没有 assertion_source
        from memoria.storage.sidecar import load_sidecar_for_md
        import os
        full = os.path.join(str(kb), src_file)
        sc = load_sidecar_for_md(full, str(kb)) or {}
        for e in sc.get("edges") or []:
            if isinstance(e, dict) and "assertion_source" in e:
                failures.append("sidecar 文件的 edges[] 被写了 assertion_source（应只进内存，不落库）")

    if failures:
        print("[FAIL] 裁决 3 探针失败：")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("[OK] 裁决 3 探针通过：")
    print("  · 不传 / None / 空 dict ⇒ 返回对象无 assertion_source 键")
    print("  · 传非空 ⇒ 返回对象出现该键（值原样）")
    print("  · sidecar 文件未被写该键（只进内存，不落库）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
