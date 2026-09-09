#!/usr/bin/env python3
"""G4 M6a 回归冒烟：临时副本库走主要维护流程，验证 barrier 持久化未破坏既有功能。

覆盖：barrier 自动保存（延迟落盘+overlay）→ durable_flush → confirm_kp_range（sidecar+pending）
→ rename_file（md/sidecar/pending 级联）→ close_kb 关库冲刷 → 重开 load_document 与 manifest 一致。
用法：python scripts/benchmark/maintenance/regression_smoke_m6a.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ["MEMORIA_FSYNC_MODE"] = "barrier"
os.environ["MEMORIA_BENCH_TIMING"] = "1"


def manifest_disk_text(kb: str) -> str:
    p = Path(kb) / ".memoria" / "manifest.yaml"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def main() -> int:
    from memoria.services.document import DocumentService
    from memoria.storage.manifest import load_manifest, ensure_manifest_baseline, entry_for_md
    from memoria.storage.scanner import collect_md_files

    kb = Path(tempfile.mkdtemp(prefix="m6a-reg-"))
    try:
        # 1) 造迷你库 3 个 md
        (kb / "a.md").write_text("# A\n\n段落一\n段落二\n", encoding="utf-8")
        (kb / "b.md").write_text("# B\n\n正文\n", encoding="utf-8")
        (kb / "sub").mkdir()
        (kb / "sub" / "c.md").write_text("# C\n\n正文c\n", encoding="utf-8")
        ensure_manifest_baseline(str(kb))

        svc = DocumentService(); svc.kb_path = str(kb); svc._cache = {}
        # 2) barrier 自动保存：内容已替换、manifest 未落盘、overlay 一致
        m0 = manifest_disk_text(str(kb))
        r = svc.save_document("a.md", "# A\n\n新段落一\n新段落二\n")
        assert r["status"] == "ok"
        assert (kb / "a.md").read_text(encoding="utf-8") == "# A\n\n新段落一\n新段落二\n"
        assert manifest_disk_text(str(kb)) == m0, "barrier 不应立即写 manifest"
        ov = load_manifest(str(kb))
        assert ov and "a.md" in ov["files_by_path"], "overlay 应可见 a.md"
        # 3) durable_flush：manifest 落盘 + dirty 清空
        fl = svc.durable_flush()
        assert fl["status"] == "ok" and fl["manifest"] >= 1 and fl["flushed"] >= 1, fl
        assert not svc._dirty_fsync
        # 4) confirm_kp_range：建 KP → sidecar + pending(json) 生成
        r = svc.confirm_kp_range("a.md", "kp-a", "知识点A", 3, 4)
        assert r["status"] == "ok", r
        sc_path = kb / ".memoria" / "sidecars" / "a.memoria.yaml"
        assert sc_path.is_file()
        pend = json.loads((kb / ".memoria" / "pending.json").read_text(encoding="utf-8"))
        assert isinstance(pend.get("items"), list), "pending.json 应可解析为 store"
        # 5) rename_file：md/sidecar 移动 + pending 级联
        rn = svc.rename_file("a.md", "aa")
        assert rn["status"] == "ok", rn
        assert (kb / "aa.md").is_file() and not (kb / "a.md").exists()
        assert (kb / ".memoria" / "sidecars" / "aa.memoria.yaml").is_file()
        pend2 = json.loads((kb / ".memoria" / "pending.json").read_text(encoding="utf-8"))
        assert all(i.get("file") != "a.md" for i in pend2.get("items", [])), "pending 旧路径应已迁移"
        # 6) close_kb 冲刷（含 pending manifest）
        svc.close_kb()
        # 7) 重开：全 md 可读且 manifest 与磁盘一致（无 sha 漂移）
        svc2 = DocumentService(); svc2.kb_path = str(kb); svc2._cache = {}
        rels = sorted(collect_md_files(str(kb)))
        assert set(rels) == {"aa.md", "b.md", "sub/c.md"}, rels
        for rel in rels:
            doc = svc2.load_document(rel)
            assert doc["status"] == "ok", (rel, doc.get("status"))
        stored = load_manifest(str(kb))["files_by_path"]
        for rel in rels:
            cur = entry_for_md(str(kb), rel)
            ent = stored.get(rel) or {}
            assert cur["md_sha256"] == ent.get("md_sha256"), f"manifest 漂移: {rel}"
        print("REGRESSION SMOKE PASS")
        return 0
    finally:
        shutil.rmtree(kb, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
