"""R7.1 决策卡实测：KP 边界重算的迁移代价（task-199 · arch-contract）

## 语料快照（必须绑固定）

`../data/corpus-snapshot.json`，`taken_at = 2026-10-27T14:09:46`，26 md / 11 sidecar。
**本脚本先校验**当前库与该快照完全一致，再用它算 ⇒ 数字可复现、不随活动库漂移。

## 要回答的（决策卡数字）

1. 用户已有数据分别绑在**什么键**上（kp_id / card_id / 行号）—— 决定重切后丢不丢
2. 三个选项各自**影响多少个 KP / 多少用户数据**
3. 工作量分解（可脚本化 vs 需人工）

用法：python .../r71_boundary_recompute_probe.py
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE.parent / "data" / "corpus-snapshot.json"
KB_ROOT = Path("D:/AAA_Courses")
KB_NAME = "数字通信原理"
KB = KB_ROOT / KB_NAME


def _load_yaml(p: Path) -> dict:
    import yaml

    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def main() -> int:
    if not KB.is_dir():
        print(f"[SKIP] 真库不可访问：{KB}")
        return 0
    if not SNAPSHOT.is_file():
        print(f"[SKIP] 快照不存在：{SNAPSHOT}")
        return 0

    # ── 0. 快照一致性（先证明数字绑在快照上）────────────────────────
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    ok = miss = diff = 0
    for e in snap["kbs"][KB_NAME]["md"]:
        p = KB / e["path"]
        if not p.is_file():
            miss += 1
        elif hashlib.sha256(p.read_bytes()).hexdigest() == e["sha256"]:
            ok += 1
        else:
            diff += 1
    print("=== 0. 快照一致性 ===")
    print(f"  taken_at = {snap['taken_at']}（26 md / 11 sidecar）")
    print(f"  md 校验: ok={ok} 缺失={miss} 不一致={diff}")
    if miss or diff:
        print("  ⚠️ 当前库已偏离快照 ⇒ 以下数字不绑快照，需重新取快照")
    print()

    # ── 1. 用户数据绑在什么键上 ──────────────────────────────────────
    sidecars = sorted((KB / ".memoria" / "sidecars").rglob("*.yaml"))
    kp_total = 0
    kp_ids: list[str] = []
    kp_with_hint = 0
    n_links = 0

    print("=== 1. KP 与用户数据的绑定关系 ===")
    print(f"  sidecar 文件: {len(sidecars)}")
    for sc in sidecars:
        data = _load_yaml(sc)
        kps = data.get("knowledge_points") or []
        links = data.get("links") or []
        for kp in kps:
            if not isinstance(kp, dict):
                continue
            kp_total += 1
            kid = kp.get("id")
            if isinstance(kid, str):
                kp_ids.append(kid)
            if ((kp.get("range") or {}).get("start") or {}).get("line_hint") is not None:
                kp_with_hint += 1
        n_links += len(links) if isinstance(links, list) else 0

    print(f"  KP 总数: {kp_total}")
    print(f"  有 start.line_hint 的 KP: {kp_with_hint}")
    print(f"  链接数（绑 kp_id）: {n_links}")

    cards_p = KB / ".memoria" / "agent" / "review" / "cards.json"
    prog_p = KB / ".memoria" / "agent" / "review" / "progress.json"
    n_cards = n_cards_kp = n_prog = 0
    if cards_p.is_file():
        try:
            cards = (json.loads(cards_p.read_text(encoding="utf-8")) or {}).get("cards") or []
            n_cards = len(cards)
            n_cards_kp = sum(1 for c in cards if isinstance(c, dict) and c.get("kp_id"))
        except json.JSONDecodeError:
            pass
    if prog_p.is_file():
        try:
            pd = json.loads(prog_p.read_text(encoding="utf-8"))
            n_prog = len((pd.get("cards") or pd) if isinstance(pd, dict) else pd)
        except json.JSONDecodeError:
            pass
    print(f"  复习卡 cards.json: {n_cards} 张（带 kp_id 的 {n_cards_kp} 张）")
    print(f"  复习进度 progress.json: {n_prog} 条（**按 card_id 索引**）")
    print()
    print("  ⇒ 决定性事实：progress.json 绑 card_id，cards.json 里才有 kp_id。")
    print("    ⇒ **只要 kp_id 不变，FSRS 进度零丢失**（与 range 是否变化无关）。")
    print()

    # ── 2. 三个选项影响面 ────────────────────────────────────────────
    dup = [k for k, v in Counter(kp_ids).items() if v > 1]
    print("=== 2. 三个选项的影响面 ===")
    print()
    print("选项① 只重算 end、不动 start：")
    print(f"  kp_id 改动        : 0（id 由 start 派生 ⇒ 不动）")
    print(f"  range 改动        : 最多 {kp_total}（全部 end）")
    print(f"  FSRS 进度丢失     : 0（绑 card_id）")
    print(f"  链接丢失          : 0（绑 kp_id）")
    print(f"  需人工            : 见 §3")
    print()
    print("选项② 全面重切 + 迁移 kp_id：")
    print(f"  kp_id 改动        : 最多 {kp_total}（全部可能变）")
    print(f"  需重写 cards.json : {n_cards_kp} 张卡的 kp_id 字段")
    print(f"  需重映射 links[]  : {n_links} 条")
    print(f"  重名 id 需先消歧  : {len(dup)} 个")
    print()
    print("选项③ 另建切片视图层（不动现有 KP）：")
    print(f"  现有 KP 改动      : 0")
    print(f"  FSRS/链接/图谱    : 全不动 ⇒ 丢失 0")
    print(f"  代价              : 两套边界并存，需一次性映射表（切片数见 corpus-analyst）")
    print()

    # ── 3. 工作量分解 ───────────────────────────────────────────────
    no_hint = kp_total - kp_with_hint
    print("=== 3. 工作量分解（选项②才需要）===")
    print(f"  可脚本定位（有 line_hint）  : {kp_with_hint}")
    print(f"  需人工/重解析（无 line_hint）: {no_hint}")
    print(f"  kp_id 重名需人工消歧        : {len(dup)}")

    out = HERE / "r71-boundary-probe.json"
    out.write_text(
        json.dumps(
            {
                "snapshot_taken_at": snap["taken_at"],
                "snapshot_md_ok": ok,
                "snapshot_md_missing": miss,
                "snapshot_md_diff": diff,
                "sidecars": len(sidecars),
                "kp_total": kp_total,
                "kp_with_line_hint": kp_with_hint,
                "kp_without_line_hint": no_hint,
                "links": n_links,
                "cards": n_cards,
                "cards_with_kp_id": n_cards_kp,
                "progress_entries": n_prog,
                "dup_kp_ids": len(dup),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
