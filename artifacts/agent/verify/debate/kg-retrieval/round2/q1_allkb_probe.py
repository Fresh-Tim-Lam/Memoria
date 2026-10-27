"""Q1 跨库迁移代价汇总（task-199 · arch-contract）

对快照里的 **5 个库**逐个统计"重切时会影响多少用户数据"。
解决单库结论不可外推的问题（数字通信原理 cards=0/progress=0，不代表其它库也空）。

数字绑 `data/corpus-snapshot.json`（taken_at 2026-10-27T14:09:46），并先校验一致性。

用法：python .../q1_allkb_probe.py
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE.parent / "data" / "corpus-snapshot.json"
ROOT = Path("D:/AAA_Courses")


def _yaml(p: Path) -> dict:
    import yaml

    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def probe(name: str, snap_entry: dict) -> dict:
    kb = ROOT / name
    row = {
        "kb": name,
        "accessible": kb.is_dir(),
        "md_in_snapshot": len(snap_entry.get("md") or []),
    }
    if not row["accessible"]:
        return row

    # 快照一致性
    ok = miss = diff = 0
    for e in snap_entry.get("md") or []:
        p = kb / e["path"]
        if not p.is_file():
            miss += 1
        elif hashlib.sha256(p.read_bytes()).hexdigest() == e["sha256"]:
            ok += 1
        else:
            diff += 1
    row["snapshot_md_ok"] = ok
    row["snapshot_md_missing"] = miss
    row["snapshot_md_diff"] = diff

    sidecars = sorted((kb / ".memoria" / "sidecars").rglob("*.yaml"))
    row["sidecars"] = len(sidecars)

    kp = links = with_hint = 0
    ids: list[str] = []
    for sc in sidecars:
        d = _yaml(sc)
        for k in d.get("knowledge_points") or []:
            if not isinstance(k, dict):
                continue
            kp += 1
            if isinstance(k.get("id"), str):
                ids.append(k["id"])
            if ((k.get("range") or {}).get("start") or {}).get("line_hint") is not None:
                with_hint += 1
        lk = d.get("links")
        links += len(lk) if isinstance(lk, list) else 0

    row["kp"] = kp
    row["kp_with_line_hint"] = with_hint
    row["links"] = links
    row["dup_kp_ids"] = sum(1 for _, v in Counter(ids).items() if v > 1)

    cards_p = kb / ".memoria" / "agent" / "review" / "cards.json"
    prog_p = kb / ".memoria" / "agent" / "review" / "progress.json"
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
    row["cards"] = n_cards
    row["cards_with_kp_id"] = n_cards_kp
    row["progress"] = n_prog

    # 外部引用行号的锚（markdown 里 `:行号` 形式引用）
    return row


def main() -> int:
    if not SNAPSHOT.is_file():
        print(f"[SKIP] 快照不存在：{SNAPSHOT}")
        return 0
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = [probe(n, e) for n, e in snap["kbs"].items()]

    hdr = ("库", "md快照", "一致", "sidecar", "KP", "有hint", "links", "重名id",
           "cards", "卡带kp_id", "progress")
    print(f"{'库':<16}{'md':>4}{'一致':>5}{'sc':>5}{'KP':>6}{'hint':>6}"
          f"{'links':>7}{'重名':>6}{'cards':>7}{'带kp':>7}{'prog':>6}")
    print("-" * 82)
    tot = Counter()
    for r in rows:
        if not r["accessible"]:
            print(f"{r['kb']:<16}  不可访问")
            continue
        print(
            f"{r['kb']:<16}{r['md_in_snapshot']:>4}{r['snapshot_md_ok']:>5}"
            f"{r.get('sidecars',0):>5}{r.get('kp',0):>6}{r.get('kp_with_line_hint',0):>6}"
            f"{r.get('links',0):>7}{r.get('dup_kp_ids',0):>6}"
            f"{r.get('cards',0):>7}{r.get('cards_with_kp_id',0):>7}{r.get('progress',0):>6}"
        )
        for k in ("kp", "kp_with_line_hint", "links", "dup_kp_ids", "cards",
                  "cards_with_kp_id", "progress", "sidecars"):
            tot[k] += r.get(k, 0)
    print("-" * 82)
    print(f"{'合计':<16}{'':>4}{'':>5}{tot['sidecars']:>5}{tot['kp']:>6}"
          f"{tot['kp_with_line_hint']:>6}{tot['links']:>7}{tot['dup_kp_ids']:>6}"
          f"{tot['cards']:>7}{tot['cards_with_kp_id']:>7}{tot['progress']:>6}")
    print()
    print("判读：")
    print(f"  · 选项②需重写的 cards 数 = {tot['cards_with_kp_id']}（只有带 kp_id 的卡才受影响）")
    print(f"  · 选项②需重映射的 links = {tot['links']}")
    print(f"  · 需人工消歧的重名 kp_id = {tot['dup_kp_ids']}")
    print(f"  · 无 line_hint 需重解析的 KP = {tot['kp'] - tot['kp_with_line_hint']}")
    print(f"  · FSRS 进度条目 = {tot['progress']}（绑 card_id ⇒ kp_id 不变即不丢）")

    out = HERE / "q1-allkb.json"
    out.write_text(json.dumps({"snapshot": snap["taken_at"], "rows": rows,
                               "totals": dict(tot)}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
