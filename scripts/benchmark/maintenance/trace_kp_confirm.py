#!/usr/bin/env python3
"""confirm_kp_range 子阶段计时（L2 后端归因）。

做法：把真实知识库整体克隆到临时目录（内容/缓存一致，避免改动真实数据），
在克隆库上执行一次真实 confirm_kp_range（写入一个随机临时 KP id），
对沿途关键子阶段插桩计时，输出各阶段 ms，随后删除克隆目录。

用法：
    python scripts/benchmark/maintenance/trace_kp_confirm.py \
        --kb "D:\\AAA_Courses\\软件工程概论" \
        --rel "教材/02_第2章_软件生存期模型.md"
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class _Stage:
    def __init__(self, name: str):
        self.name = name
        self.elapsed = 0.0
        self.count = 0
        self.calls: list[float] = []


def _timed(stage: _Stage, fn):
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            dt = (time.perf_counter() - t0) * 1000
            stage.elapsed += dt
            stage.count += 1
            stage.calls.append(dt)
    return wrapper


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default=r"D:\AAA_Courses\软件工程概论")
    ap.add_argument("--rel", default="教材/02_第2章_软件生存期模型.md")
    ap.add_argument("--repeats", type=int, default=1, help="confirm 重复次数（第 1 次仍保留临时 KP，用同一 id 走更新分支）")
    ap.add_argument("--no-confirm", action="store_true", help="只扫描各文件 pending 重算成本，不执行 confirm")
    args = ap.parse_args()

    src = Path(args.kb)
    if not src.is_dir():
        print(f"知识库不存在: {src}", file=sys.stderr)
        return 2

    # 克隆：保证缓存(词法索引/embedding/manifest/sidecar)与真实库一致
    tmp = Path(tempfile.mkdtemp(prefix="memoria-kp-confirm-trace-"))
    print(f"克隆 KB: {src} -> {tmp}")
    t_clone = time.perf_counter()
    shutil.copytree(src, tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    print(f"克隆耗时: {(time.perf_counter() - t_clone) * 1000:.1f} ms")

    import memoria.services.document as D
    from memoria.services.document import DocumentService

    stages: dict[str, _Stage] = {}
    def s(name: str) -> _Stage:
        st = stages.get(name)
        if st is None:
            st = _Stage(name)
            stages[name] = st
        return st

    # 模块级函数计时（document.py 全局名查找，打补丁即可生效）
    mod_fns = [
        ("build_kp_index", D.build_kp_index),
        ("validate_sidecar", getattr(D, "validate_sidecar", None)),
        ("sync_kb_pending", getattr(D, "sync_kb_pending", None)),
        ("load_sidecar_for_md", getattr(D, "load_sidecar_for_md", None)),
    ]
    saved_mod = {}
    for name, fn in mod_fns:
        if fn is None:
            continue
        saved_mod[name] = fn
        setattr(D, name, _timed(s("mod:" + name), fn))

    svc = DocumentService()
    svc.kb_path = str(tmp)
    svc._cache = {}

    # 实例方法计时
    saved_meth = {}
    for name in ("_write_sidecar", "load_document", "_read_body", "_rebuild_lexical_index"):
        orig = getattr(DocumentService, name)
        saved_meth[name] = orig
        setattr(svc, name, _timed(s("svc:" + name), orig.__get__(svc, DocumentService)))

    # pending 模块内部函数计时（sync_kb_pending 按模块全局名调用，可命中）
    import memoria.storage.pending as P

    saved_P: dict[str, object] = {}
    for name, fn in [
        ("load_pending", getattr(P, "load_pending", None)),
        ("save_pending", getattr(P, "save_pending", None)),
        ("_proposal_to_item", getattr(P, "_proposal_to_item", None)),
        ("is_proposal_covered", getattr(P, "is_proposal_covered", None)),
        ("make_pending_id", getattr(P, "make_pending_id", None)),
        ("propose_all_ranges_patch_none", None),
    ]:
        if fn is None:
            continue
        saved_P[name] = fn
        setattr(P, name, _timed(s("P:" + name), fn))
    # propose_all_ranges 走 range_proposals 模块
    import memoria.services.range_proposals as RP

    saved_RP = RP.propose_all_ranges
    setattr(RP, "propose_all_ranges", _timed(s("RP:propose_all_ranges"), saved_RP))

    rel = args.rel.replace("\\", "/")
    kp_id = "kb-bench-tmp-" + uuid.uuid4().hex[:10]

    # 预估「仅重算单文件 pending」的成本（confirm 后新 KP 只覆盖本文件内的提议）
    print("\n单文件 pending 重算预估:")
    try:
        from memoria.services.kp_resolver import resolve_knowledge_points as rkp
        from memoria.services.range_proposals import propose_all_ranges
        from memoria.storage.pending import is_proposal_covered
        from memoria.storage.scanner import collect_md_files
        strip_frontmatter = D.strip_frontmatter
        load_sc = D.load_sidecar_for_md

        print("  各文件重算成本（1 次）:")
        per_file = []
        for rel_i in sorted({r.replace("\\", "/") for r in collect_md_files(str(tmp))}):
            full_i = Path(tmp) / rel_i
            if not full_i.is_file():
                continue
            t0 = time.perf_counter()
            raw = full_i.read_text(encoding="utf-8")
            body, fm = strip_frontmatter(raw)
            sc = load_sc(str(full_i), str(tmp))
            kps = rkp(body, sc)
            h, m, d, _ = propose_all_ranges(body, fm)
            n = sum(1 for p in h + m + d if not is_proposal_covered(p, kps))
            ms = (time.perf_counter() - t0) * 1000
            per_file.append((ms, rel_i, len(full_i.read_bytes()), len(kps), n))
        for ms, rel_i, size, kp_n, unc in sorted(per_file, reverse=True):
            print(f"    {ms:8.1f} ms  size={size:>9}  kps={kp_n:>3}  uncov={unc:>3}  {rel_i}")

        # 目标文件重复 3 次作参照
        full = Path(tmp) / rel
        for i in range(3):
            t0 = time.perf_counter()
            raw = full.read_text(encoding="utf-8")
            body, fm = strip_frontmatter(raw)
            sc = load_sc(str(full), str(tmp))
            kps = rkp(body, sc)
            h, m, d, _ = propose_all_ranges(body, fm)
            n = sum(1 for p in h + m + d if not is_proposal_covered(p, kps))
            print(f"  target run{i}: {(time.perf_counter() - t0) * 1000:.1f} ms  未覆盖提议数={n}  kps={len(kps)}")
    except Exception as e:  # noqa: BLE001
        print(f"  单文件预估失败: {e}")

    try:
        if args.no_confirm:
            print("--no-confirm：跳过实际 confirm")
        else:
            # 预热 embedding（与真实应用打开库时一致），避免把首次冷启动计入
            try:
                from memoria.services.embedding_provider import warmup_embedding
                warmup_embedding(str(tmp))
                print("embedding 预热完成")
            except Exception as e:  # noqa: BLE001
                print(f"embedding 预热失败（继续）: {e}")
            for i in range(max(1, args.repeats)):
                t0 = time.perf_counter()
                res = svc.confirm_kp_range(rel, kp_id, "基准计时临时知识点", 1, min(5, 1))
                total_ms = (time.perf_counter() - t0) * 1000
                ok = res.get("status") == "ok" if isinstance(res, dict) else False
                print(f"[run {i}] confirm_kp_range total={total_ms:.1f} ms status={'ok' if ok else res.get('status', res)}")
                if not ok:
                    break
                # 第二次起走 update 分支（同一 id）；仍是真实路径
    finally:
        # 还原补丁（对克隆库数据无影响，只是不残留）
        for name, fn in saved_mod.items():
            setattr(D, name, fn)
        for name, fn in saved_P.items():
            setattr(P, name, fn)
        setattr(RP, "propose_all_ranges", saved_RP)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n阶段耗时（累计 ms；每阶段总时长/调用次数/单次明细前 3）:")
    for name, st in sorted(stages.items(), key=lambda kv: -kv[1].elapsed):
        detail = ", ".join(f"{c:.1f}" for c in st.calls[:3])
        print(f"  {name:<32} total={st.elapsed:8.1f}  count={st.count}  calls=[{detail}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
