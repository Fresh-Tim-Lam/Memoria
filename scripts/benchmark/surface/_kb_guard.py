"""KB 完整性守卫 —— 冻结语料只读 + 前后 sha 校验（task-55）。

════════════════════════════════════════════════════════════════════════════
为什么必须有它（持续发生的真实缺陷，不是历史残留）
════════════════════════════════════════════════════════════════════════════
2026-10-21 实测证据链：
  · `artifacts/_p5_matrix_kb/corpus/03-block-boundaries.md` 修改时间 **22:57:54**
  · P6a 的 diag（20:49 finish）里该文档**不含** `ZZZ`
  ⇒ 污染**发生在测试运行期间**（task-54 窗口），不是早年遗留。
  · 后果：`p5_perf_frozen` 的 `blocks=32` / `upsert=48` 是污染态下的值，基线失效。

**根因**：测量脚本用 `MEMORIA_KB=<冻结语料>` 直接跑 `save` / `paste` / 编辑类操作，
应用的自动保存把测试改动**写回冻结语料**。逐次累积（`ZZZ` / CRLF 转换 / `.memoria` 缓存写入）。

**铁律**（已写入 `scripts/benchmark/surface/README.md`）：
   冻结语料只读；测试写入一律在副本上；每次真机测试前后校验 sha。

════════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════════
    from _kb_guard import KbGuard, make_work_copy

    guard = KbGuard(frozen_kb_dir)          # 建立基线快照（before）
    ...                                      # 跑测量
    result = guard.verify()                  # 校验（after）
    if not result["ok"]:
        raise SystemExit("KB 被测试写入: %s" % result["changed"])   # 判红

需要写 KB 的测试：
    work = make_work_copy(frozen_kb_dir, label="save-test")   # 副本
    # 用 work 作为 MEMORIA_KB，不要用 frozen_kb_dir

命令行自检：
    python scripts/benchmark/surface/_kb_guard.py --kb artifacts/_p5_matrix_kb
    python scripts/benchmark/surface/_kb_guard.py --kb artifacts/_p5_matrix_kb --manifest <manifest.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

#: 冻结矩阵的 13 个文档（与 make_p5_matrix_kb.py 的输出严格一致）
FROZEN_DOCS: tuple[str, ...] = (
    "scale/scale-5k.md",
    "scale/scale-1k.md",
    "scale/scale-10k.md",
    "corpus/01-ime-zh.md",
    "corpus/02-inline-edges.md",
    "corpus/03-block-boundaries.md",
    "corpus/04-non-editable.md",
    "corpus/05-images.md",
    "corpus/06-links-and-kp.md",
    "corpus/07-extremes.md",
    "README.md",
    "docs/error_log_format.md",
    "docs/ref/ppt/ocr.md",
)

#: 冻结身份锚点（用于识别"是否同一份冻结语料"）
FROZEN_ANCHOR = {
    "path": "scale/scale-5k.md",
    "sha256": "a626b6961576bf6d",
    "size": 92760,
    "last_byte": 0x0A,
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(kb_dir: Path, docs: tuple[str, ...] = FROZEN_DOCS) -> dict[str, dict[str, Any]]:
    """对 `docs` 逐文档取 (sha256, size, last_byte)。缺失记 None（不算通过）。"""
    out: dict[str, dict[str, Any]] = {}
    for rel in docs:
        p = Path(kb_dir) / rel
        if not p.is_file():
            out[rel] = {"sha256": None, "size": None, "last_byte": None, "exists": False}
            continue
        b = p.read_bytes()
        out[rel] = {
            "sha256": hashlib.sha256(b).hexdigest(),
            "size": len(b),
            "last_byte": b[-1] if b else None,
            "exists": True,
        }
    return out


def diff_snapshots(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """列出 before/after 之间变化的文档（点名）。"""
    changed: list[dict[str, Any]] = []
    for rel in before:
        b, a = before[rel], after.get(rel, {})
        if b.get("sha256") != a.get("sha256"):
            changed.append({
                "file": rel,
                "before": b,
                "after": a,
                "kind": "deleted" if not a.get("exists", True) else "modified",
            })
    return changed


class KbGuard:
    """冻结语料完整性守卫：建立 before 快照 → 运行 → verify() 判红/绿。"""

    def __init__(self, kb_dir: Path | str, docs: tuple[str, ...] = FROZEN_DOCS) -> None:
        self.kb_dir = Path(kb_dir).resolve()
        self.docs = docs
        self.before: dict[str, dict[str, Any]] | None = None

    def snapshot_before(self) -> dict[str, dict[str, Any]]:
        self.before = snapshot(self.kb_dir, self.docs)
        return self.before

    def verify(self) -> dict[str, Any]:
        """校验。返回 `{ok, changed[], kb_dir, ...}`；`ok=False` 必须判红。"""
        if self.before is None:
            raise RuntimeError("KbGuard.verify() 前必须先 snapshot_before()")
        after = snapshot(self.kb_dir, self.docs)
        changed = diff_snapshots(self.before, after)
        missing = [r for r, v in after.items() if not v.get("exists")]
        return {
            "ok": not changed and not missing,
            "kb_dir": str(self.kb_dir),
            "documents": len(self.docs),
            "changed": changed,
            "missing": missing,
            "before": self.before,
            "after": after,
        }

    def manifest(self) -> dict[str, Any]:
        """可落盘的自证清单（补上冻结产物此前 `file: None` 的缺口）。"""
        snap = snapshot(self.kb_dir, self.docs)
        return {
            "schema": "memoria-frozen-kb-manifest/v1",
            "kb_dir": str(self.kb_dir),
            "documents": len(self.docs),
            "files": {rel: {"sha256": v["sha256"], "size": v["size"], "last_byte": v["last_byte"]}
                      for rel, v in snap.items()},
            "anchor": FROZEN_ANCHOR,
            "anchor_matches": (
                snap.get(FROZEN_ANCHOR["path"], {}).get("sha256", "").startswith(FROZEN_ANCHOR["sha256"])
                and snap.get(FROZEN_ANCHOR["path"], {}).get("size") == FROZEN_ANCHOR["size"]
            ),
        }

    def assert_clean(self, when: str = "after") -> None:
        """不干净即抛异常（供测量脚本直接调用）。"""
        r = self.verify()
        if not r["ok"]:
            names = ", ".join(c["file"] for c in r["changed"]) or ", ".join(r["missing"])
            raise SystemExit(
                f"[kb-guard] ❌ 冻结语料在测试{when}被写入/删除: {names}\n"
                f"           这是**测试缺陷**（测试不该写冻结语料）。请在副本上跑写类测试。\n"
                f"           冻结语料: {r['kb_dir']}"
            )


def make_work_copy(
    frozen_kb_dir: Path | str,
    label: str = "work",
    *,
    root: Path | None = None,
) -> Path:
    """为需要写 KB 的测试创建**副本**（冻结语料只读，绝不直接写）。"""
    src = Path(frozen_kb_dir).resolve()
    parent = (root or REPO_ROOT) / "artifacts"
    parent.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in label)[:40]
    dst = parent / f"_kbwork_{safe}"
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    return dst


def _cli() -> int:
    ap = argparse.ArgumentParser(description="冻结 KB 完整性校验（task-55）")
    ap.add_argument("--kb", default=str(REPO_ROOT / "artifacts" / "_p5_matrix_kb"))
    ap.add_argument("--manifest", default=None, help="写 manifest 到此路径")
    ap.add_argument("--expected", default=None,
                    help="对比既有 manifest（判定是否与冻结身份一致）")
    ap.add_argument("--claim", action="store_true",
                    help="只做**前**快照并打印（配合 --verify 用）")
    ap.add_argument("--verify", default=None,
                    help="与前一次快照 json 对比；不一致 ⇒ exit 1 并点名")
    args = ap.parse_args()

    kb = Path(args.kb).resolve()

    if args.verify:
        before = json.loads(Path(args.verify).read_text(encoding="utf-8"))
        after = snapshot(kb)
        changed = diff_snapshots(before, after)
        missing = [r for r, v in after.items() if not v.get("exists")]
        if changed or missing:
            print("[kb-guard] ❌ 冻结语料被测试写入/删除：", file=sys.stderr)
            for c in changed:
                print(f"   - {c['file']}  ({c['kind']})", file=sys.stderr)
                print(f"     before: {c['before']}", file=sys.stderr)
                print(f"     after : {c['after']}", file=sys.stderr)
            for m in missing:
                print(f"   - {m}  (missing)", file=sys.stderr)
            print("[kb-guard] 判定：**红**（测试缺陷，禁止写冻结语料）", file=sys.stderr)
            return 1
        print(f"[kb-guard] ✅ 冻结语料未变（{len(after)} 篇）")
        print("[kb-guard] 判定：**绿**")
        return 0

    g = KbGuard(kb)
    snap = g.snapshot_before()
    if args.claim:
        out = Path(args.manifest) if args.manifest else None
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[kb-guard] 前快照已写: {out}")
        else:
            print(json.dumps(snap, ensure_ascii=False))
        return 0

    # 单次校验模式
    man = g.manifest()
    ok = all(v["sha256"] for v in snap.values())
    print(f"[kb-guard] KB={kb}")
    print(f"[kb-guard] 文档数={len(snap)}  全部存在={ok}")
    print(f"[kb-guard] 锚点 scale-5k.md 匹配冻结身份={man['anchor_matches']}")
    for rel, v in snap.items():
        flag = "OK " if v["exists"] else "MISS"
        print(f"  {flag} {rel:32s} {str(v['sha256'])[:16]}  {v['size']:>7}  last=0x{(v['last_byte'] or 0):02X}")
    if args.manifest:
        out = Path(args.manifest)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[kb-guard] manifest 已写: {out}")

    if args.expected:
        exp = json.loads(Path(args.expected).read_text(encoding="utf-8"))
        exp_files = exp.get("files") or {}
        bad = [rel for rel, v in exp_files.items()
               if snap.get(rel, {}).get("sha256") != v.get("sha256")]
        if bad:
            print(f"[kb-guard] ❌ 与既有 manifest 不一致: {bad}", file=sys.stderr)
            return 1
        print(f"[kb-guard] ✅ 与既有 manifest 一致（{len(exp_files)} 篇）")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
