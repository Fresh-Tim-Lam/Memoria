#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_p5_matrix_kb.py —— 构建 P5 全量矩阵的**冻结 KB**（task-33）

为什么不能整份复制：`_p2b_kbFrozen` 有 220 个 md、`_kp_probe_kb` 148 个，
  每次 fidelity 都要渲染全部 ⇒ 慢几十倍，且引入无关文档噪声。
  ⇒ **只复制矩阵要用的 13 个文档**，保持相对路径不变。

13 文档 = probe-kb 的 11（scale-5k/1k/10k + corpus 01..07 + README）
        + docs/error_log_format.md + docs/ref/ppt/ocr.md（来自 _kp_golden_kb，三处 hash 一致）

产物：`artifacts/_p5_matrix_kb/`（含 .memoria 索引骨架）+ 清单 `manifest.json`
        清单记录**每篇来源 KB + 源文件 sha256**，保证冻结可复现。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEST = REPO_ROOT / "artifacts" / "_p5_matrix_kb"

# 主源：probe-kb（11 篇）
PRIMARY_SRC = REPO_ROOT / "tests" / "probe-kb"
PRIMARY_FILES = [
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
]

# 副源：冻结副本（2 篇；三处 hash 一致，取 _kp_golden_kb 作规范来源）
SECONDARY_SRC = REPO_ROOT / "artifacts" / "_kp_golden_kb"
SECONDARY_FILES = [
    "docs/error_log_format.md",
    "docs/ref/ppt/ocr.md",
]


def sha256_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if DEST.exists():
        shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True, exist_ok=True)

    entries = []

    def copy_one(rel: str, src_root: Path) -> None:
        src = src_root / rel
        if not src.exists():
            raise SystemExit("源文件缺失: %s" % src)
        dst = DEST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        entries.append({
            "path": rel,
            "source_kb": str(src_root.relative_to(REPO_ROOT)).replace("\\", "/"),
            "source_sha256": sha256_of(src),
            "dest_sha256": sha256_of(dst),
            "bytes": dst.stat().st_size,
        })

    def copy_from_git(rel: str) -> None:
        """probe-kb 的文件优先取 **git HEAD 版本**（权威、干净）。

        !! 为什么：实测 `tests/probe-kb/scale/scale-5k.md` 工作区被别的 agent 的
           变异测试污染过（首行插入了 800+ 个 'z'），直接用工作区文件会把脏数据
           冻进基线。git HEAD 是唯一权威来源。
        """
        import subprocess
        dst = DEST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(
            ["git", "show", "HEAD:tests/probe-kb/" + rel],
            cwd=str(REPO_ROOT), capture_output=True)
        if blob.returncode != 0:
            raise SystemExit("git HEAD 取文件失败: %s\n%s" % (rel, blob.stderr.decode("utf-8", "replace")))
        dst.write_bytes(blob.stdout)
        work = PRIMARY_SRC / rel
        dirty = work.exists() and sha256_of(work) != sha256_of(dst)
        entries.append({
            "path": rel,
            "source_kb": "git:HEAD:tests/probe-kb",
            "source_sha256": sha256_of(dst),
            "dest_sha256": sha256_of(dst),
            "bytes": dst.stat().st_size,
            "worktree_dirty": dirty,
        })

    for rel in PRIMARY_FILES:
        copy_from_git(rel)
    for rel in SECONDARY_FILES:
        copy_one(rel, SECONDARY_SRC)

    # 带上 .memoria 索引骨架（wikilink 解析 / KP 快照需要；不复制 cache）
    mem_src = PRIMARY_SRC / ".memoria"
    mem_dst = DEST / ".memoria"
    if mem_src.exists():
        shutil.copytree(mem_src, mem_dst, ignore=shutil.ignore_patterns("cache", "*.tmp"))

    manifest = {
        "schema": "memoria-p5-matrix-kb/v1",
        "purpose": "task-33 渲染层全量矩阵的冻结 KB（只含矩阵用到的 13 篇）",
        "dest": str(DEST.relative_to(REPO_ROOT)).replace("\\", "/"),
        "doc_count": len(entries),
        "documents": entries,
        "note": "不整份复制源 KB（避免 220 篇带来的耗时与噪声）；每篇记录来源 KB + sha256",
    }
    (DEST / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[p5-kb] 冻结 KB 已建: %s（%d 篇）" % (DEST, len(entries)))
    for e in entries:
        print("  %-34s <- %s  %s" % (e["path"], e["source_kb"], e["source_sha256"][:12]))
    print("__P5KB__" + json.dumps({"dest": str(DEST), "count": len(entries)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
