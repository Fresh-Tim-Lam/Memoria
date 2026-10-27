"""R3 证据绑定实测：文件级 sha256 作为 stale 判据的【精度】问题（task-191）。

## 要回答的问题

`manifest.yaml` 已有 `md_sha256`（文件级）。它能低成本检测"文件变了"，
但它**不能告诉你"哪个 KP 变了"** ⇒ 文件改一个字，整文件所有 KP 全变 stale。

本脚本量化这个代价：在真实语料上，**一处编辑会让多少 KP 被误标 stale**。

用法：python .../r3_stale_precision_probe.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))

CORPORA = {
    "AAA_Vocab": REPO / "docs" / "example" / "AAA_Vocab",
    "真库-数字通信原理": Path("D:/AAA_Courses/数字通信原理"),
}


def _load(path: Path) -> dict:
    import yaml

    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _body(kb: Path, sidecar: Path) -> Path | None:
    rel = sidecar.relative_to(kb / ".memoria" / "sidecars")
    name = rel.name[: -len(".memoria.yaml")] if rel.name.endswith(".memoria.yaml") else rel.name
    md = kb / rel.parent / (name + ".md")
    return md if md.is_file() else None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def probe(name: str, kb: Path) -> dict:
    """模拟"在某文档末尾加一行"，看文件级 hash 会让多少 KP 变 stale。"""
    docs = 0
    kps = 0
    stale_by_file_hash = 0  # 文件改了 ⇒ 该文件所有 KP 都算 stale
    actually_affected = 0   # 真正受影响的 KP（range 覆盖被编辑行）

    for sidecar in (kb / ".memoria" / "sidecars").rglob("*.yaml"):
        data = _load(sidecar)
        kp_list = data.get("knowledge_points") or []
        md = _body(kb, sidecar)
        if md is None or not isinstance(kp_list, list) or not kp_list:
            continue
        docs += 1
        text = md.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        n_kp = len(kp_list)
        kps += n_kp

        # 文件级：改 1 个字符（末尾加一行）⇒ 整文件 KP 全部 stale
        edited = text + "\n（新增一行）\n"
        if _sha(edited) != _sha(text):
            stale_by_file_hash += n_kp

        # 理想（块级）：只有 range 覆盖被编辑行的 KP 才算 stale
        edit_line = len(lines) + 1
        for kp in kp_list:
            if not isinstance(kp, dict):
                continue
            rng = kp.get("range") or {}
            s = (rng.get("start") or {}).get("line_hint")
            e = (rng.get("end") or {}).get("line_hint")
            if isinstance(s, int) and isinstance(e, int) and s <= edit_line <= e:
                actually_affected += 1

    return {
        "corpus": name,
        "docs": docs,
        "kps": kps,
        "stale_by_file_hash": stale_by_file_hash,
        "actually_affected": actually_affected,
        "over_invalidation_ratio": (
            stale_by_file_hash / actually_affected if actually_affected else None
        ),
    }


def main() -> int:
    rows = []
    for name, kb in CORPORA.items():
        if kb.is_dir():
            rows.append(probe(name, kb))

    print("=== R3：文件级 sha256 作 stale 判据的精度 ===")
    print("（模拟：每个文档末尾新增一行 ⇒ 统计有多少 KP 被判 stale）")
    print()
    print(f"{'库':<22}{'文档':>6}{'KP':>7}{'文件级stale':>12}{'实际受影响':>12}{'过度失效倍数':>14}")
    for r in rows:
        ratio = r["over_invalidation_ratio"]
        print(
            f"{r['corpus']:<22}{r['docs']:>6}{r['kps']:>7}"
            f"{r['stale_by_file_hash']:>12}{r['actually_affected']:>12}"
            f"{(f'{ratio:.1f}×' if ratio else 'n/a'):>14}"
        )
    print()
    print("解读：文件级 hash 会把【整文件所有 KP】标 stale，")
    print("      而实际只影响【range 覆盖被编辑行】的那些 ⇒ 过度失效倍数即代价。")

    out = REPO / "artifacts/agent/verify/debate/kg-retrieval/r3-stale-precision.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
