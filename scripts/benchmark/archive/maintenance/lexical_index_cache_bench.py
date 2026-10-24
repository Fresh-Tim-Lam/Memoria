"""task-69 P0-a calibration: lexical index in-process cache (before / after).

Read-only against the repo; all mutations happen on a temporary copy of the
baseline KB.

Measures:
  1. before/after cost for 10 / 50 / 100 / 293 consecutive lookups
     (before = the pre-fix ``load_lexical_index() or rebuild_lexical_index()``)
  2. prove-red: one cold lookup right after invalidation is slow, warm lookups fast
  3. byte identity: 293 cached lookups vs a fresh disk load (sha256 of canonical JSON)
  4. end-to-end ``suggest_group_labels`` output equality (old impl vs new impl)
  5. invalidation correctness: explicit save, external file overwrite, shallow-copy isolation
  6. thread safety: 8 threads x 25 lookups -> identical result, single disk load

Usage:
  .venv\\Scripts\\python.exe scripts\\benchmark\\maintenance\\lexical_index_cache_bench.py ^
      --out artifacts\\agent\\verify\\boot-p0a-lexical-cache.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from memoria.services import lexical_index as li  # noqa: E402
from memoria.services import search_kernel as sk  # noqa: E402


def now() -> float:
    return time.perf_counter()


def timed(fn):
    t0 = now()
    result = fn()
    return result, (now() - t0) * 1000.0


def old_ensure_lexical_index(kb_path: str) -> dict:
    """Exact pre-fix implementation (kept only for the before/after comparison)."""
    cached = li.load_lexical_index(kb_path)
    if cached is not None:
        return cached
    return li.rebuild_lexical_index(kb_path)


def canonical_digest(obj) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_kb_copy(src_kb: str) -> str:
    tmp_root = tempfile.mkdtemp(prefix="memoria_p0a_")
    dst = os.path.join(tmp_root, "kb")
    shutil.copytree(src_kb, dst)
    return dst


def build_groups(kb_path: str, count: int) -> list[dict]:
    """Representative group payload: small node-id sets, like the real graph tab."""
    index = li.load_lexical_index(kb_path) or {}
    records = index.get("records") or []
    ids = [str(r.get("kp_id") or "") for r in records if r.get("kp_id")]
    names = {str(r.get("kp_id") or ""): str(r.get("name") or "") for r in records}
    if not ids:
        return []
    groups: list[dict] = []
    for i in range(count):
        picks = [ids[(i * 3 + j) % len(ids)] for j in range(3)]
        hub = picks[0]
        groups.append({
            "id": f"g{i}",
            "nodeIds": picks,
            "hubId": hub,
            "hubName": names.get(hub, hub),
        })
    return groups


def bench_scale(kb_path: str, counts: list[int]) -> dict:
    rows = []
    for n in counts:
        before_ms = None
        after_ms = None
        after_first_ms = None
        after_warm_ms = None

        li.invalidate_lexical_index(kb_path)
        _, before_ms = timed(lambda: [old_ensure_lexical_index(kb_path) for _ in range(n)])

        li.invalidate_lexical_index(kb_path)
        _, after_ms = timed(lambda: [li.ensure_lexical_index(kb_path) for _ in range(n)])

        li.invalidate_lexical_index(kb_path)
        _, after_first_ms = timed(lambda: li.ensure_lexical_index(kb_path))
        _, after_warm_ms = timed(lambda: li.ensure_lexical_index(kb_path))

        rows.append({
            "groups": n,
            "before_total_ms": round(before_ms, 1),
            "before_per_call_ms": round(before_ms / n, 2),
            "after_total_ms": round(after_ms, 1),
            "after_per_call_ms": round(after_ms / n, 3),
            "after_cold_first_call_ms": round(after_first_ms, 1),
            "after_warm_call_ms": round(after_warm_ms, 3),
            "speedup_x": round(before_ms / after_ms, 1) if after_ms else None,
        })
        print(
            f"[scale] n={n:4d}  before={before_ms:9.1f} ms ({before_ms/n:6.2f}/call)"
            f"  after={after_ms:8.1f} ms ({after_ms/n:6.3f}/call)  {before_ms/after_ms:6.1f}x",
            flush=True,
        )
    return {"rows": rows}


def bench_identity(kb_path: str, repeat: int) -> dict:
    reference = li.load_lexical_index(kb_path)
    reference_digest = canonical_digest(reference)
    li.invalidate_lexical_index(kb_path)
    digests: set[str] = set()
    mismatches: list[int] = []
    for i in range(repeat):
        got = li.ensure_lexical_index(kb_path)
        digests.add(canonical_digest(got))
        if got != reference:
            mismatches.append(i)
    return {
        "repeat": repeat,
        "reference_digest": reference_digest,
        "observed_digests": sorted(digests),
        "identical": digests == {reference_digest} and not mismatches,
        "mismatch_indices": mismatches,
    }


def bench_suggest_labels(kb_path: str, groups: list[dict]) -> dict:
    """End-to-end: old per-group disk load vs new cached lookup must agree."""
    li.invalidate_lexical_index(kb_path)
    sk.ensure_lexical_index = old_ensure_lexical_index  # type: ignore[assignment]
    try:
        out_before, before_ms = timed(lambda: sk.suggest_group_labels(kb_path=kb_path, groups=groups))
    finally:
        sk.ensure_lexical_index = li.ensure_lexical_index  # type: ignore[assignment]

    li.invalidate_lexical_index(kb_path)
    out_after, after_ms = timed(lambda: sk.suggest_group_labels(kb_path=kb_path, groups=groups))
    return {
        "groups": len(groups),
        "before_ms": round(before_ms, 1),
        "after_ms": round(after_ms, 1),
        "speedup_x": round(before_ms / after_ms, 1) if after_ms else None,
        "labels_identical": out_before == out_after,
        "labels_before_digest": canonical_digest(out_before),
        "labels_after_digest": canonical_digest(out_after),
        "labels_sample": dict(list(out_after.get("labels", {}).items())[:5]),
        "labels_count": len(out_after.get("labels", {})),
    }


def bench_invalidation(kb_path: str) -> dict:
    results: dict = {}

    # (a) explicit in-process save -> cache must be dropped
    li.invalidate_lexical_index(kb_path)
    base = dict(li.ensure_lexical_index(kb_path))
    probe = dict(base)
    probe["record_count"] = 123456
    li.save_lexical_index(kb_path, probe)
    got = li.ensure_lexical_index(kb_path)
    results["explicit_save_invalidates"] = got.get("record_count") == 123456

    # (b) external writer (other process) bypassing save_lexical_index
    li.invalidate_lexical_index(kb_path)
    external = dict(li.load_lexical_index(kb_path) or {})
    external["token_count"] = 654321
    path = li.lexical_cache_path(kb_path)
    time.sleep(0.02)  # make sure mtime moves on coarse filesystems
    with open(path, "w", encoding="utf-8") as f:
        json.dump(external, f, ensure_ascii=False, indent=2)
    got = li.ensure_lexical_index(kb_path)
    results["external_write_invalidates"] = got.get("token_count") == 654321

    # (c) index file removed -> must be rebuilt from sources
    li.invalidate_lexical_index(kb_path)
    os.remove(path)
    got, rebuild_ms = timed(lambda: li.ensure_lexical_index(kb_path))
    results["missing_file_rebuilds"] = os.path.isfile(path) and int(got.get("record_count") or 0) > 0
    results["rebuild_ms"] = round(rebuild_ms, 1)

    # (d) callers cannot poison the cache through the returned top-level dict
    first = li.ensure_lexical_index(kb_path)
    first["injected_key"] = True
    first["records"] = []
    second = li.ensure_lexical_index(kb_path)
    results["returned_dict_is_isolated"] = (
        "injected_key" not in second and bool(second.get("records"))
    )
    return results


def bench_threads(kb_path: str, threads: int, per_thread: int) -> dict:
    li.invalidate_lexical_index(kb_path)
    reference = li.load_lexical_index(kb_path)
    reference_digest = canonical_digest(reference)

    load_calls = {"n": 0}
    original_load = li.load_lexical_index

    def counting_load(kb):
        load_calls["n"] += 1
        return original_load(kb)

    li.load_lexical_index = counting_load  # type: ignore[assignment]
    digests: list[str] = []
    errors: list[str] = []
    barrier = threading.Barrier(threads)

    def worker():
        try:
            barrier.wait(timeout=30)
            local: list[str] = []
            for _ in range(per_thread):
                local.append(canonical_digest(li.ensure_lexical_index(kb_path)))
            digests.extend(local)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed silently
            errors.append(f"{type(exc).__name__}: {exc}")

    t0 = now()
    pool = [threading.Thread(target=worker, name=f"p0a-{i}") for i in range(threads)]
    try:
        for th in pool:
            th.start()
        for th in pool:
            th.join(timeout=120)
        elapsed_ms = (now() - t0) * 1000.0
    finally:
        li.load_lexical_index = original_load  # type: ignore[assignment]

    return {
        "threads": threads,
        "per_thread": per_thread,
        "elapsed_ms": round(elapsed_ms, 1),
        "unique_digests": sorted(set(digests)),
        "identical": set(digests) == {reference_digest},
        "errors": errors,
        "disk_load_calls": load_calls["n"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--kb",
        default=os.path.join(ROOT, "artifacts", "baseline-kb", "\u6570\u5b57\u901a\u4fe1\u539f\u7406"),
        help="source KB (copied to a temp dir; the original is never written)",
    )
    ap.add_argument("--repeat", type=int, default=293)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if not os.path.isdir(args.kb):
        print(f"KB not found: {args.kb}", file=sys.stderr)
        return 2

    kb = make_kb_copy(args.kb)
    print(f"[setup] temp KB copy: {kb}", flush=True)
    try:
        index_path = li.lexical_cache_path(kb)
        meta = {
            "anchor": "task-69",
            "item": "P0-a lexical_index in-process cache",
            "kb_source": args.kb,
            "kb_copy": kb,
            "index_json_bytes": os.path.getsize(index_path) if os.path.isfile(index_path) else 0,
        }
        cached = li.load_lexical_index(kb) or {}
        meta["record_count"] = cached.get("record_count")
        meta["token_count"] = cached.get("token_count")

        scale = bench_scale(kb, [10, 50, 100, 293])
        identity = bench_identity(kb, args.repeat)

        groups = build_groups(kb, 293)
        labels = bench_suggest_labels(kb, groups)

        invalidation = bench_invalidation(kb)
        threads = bench_threads(kb, 8, 25)

        cold = scale["rows"][0] if scale["rows"] else {}
        warm_ms = cold.get("after_warm_call_ms")
        proof = {
            "cold_first_call_ms": cold.get("after_cold_first_call_ms"),
            "warm_call_ms": warm_ms,
            "cold_is_slow": (cold.get("after_cold_first_call_ms") or 0) > 10.0,
            "warm_is_fast": (warm_ms is not None) and warm_ms < 1.0,
            "per_group_before_ms": cold.get("before_per_call_ms"),
            "per_group_after_ms": cold.get("after_per_call_ms"),
        }

        report = {
            "meta": meta,
            "scale": scale,
            "prove_red": proof,
            "identity": identity,
            "suggest_group_labels": labels,
            "invalidation": invalidation,
            "threads": threads,
            "pass": all([
                proof["cold_is_slow"],
                proof["warm_is_fast"],
                identity["identical"],
                labels["labels_identical"],
                invalidation["explicit_save_invalidates"],
                invalidation["external_write_invalidates"],
                invalidation["missing_file_rebuilds"],
                invalidation["returned_dict_is_isolated"],
                threads["identical"],
                not threads["errors"],
            ]),
        }
        print(json.dumps({k: report[k] for k in ("prove_red", "identity", "invalidation", "threads")},
                         ensure_ascii=False, indent=2), flush=True)
        print(f"[result] pass={report['pass']}", flush=True)

        if args.out:
            out_path = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[out] {out_path}", flush=True)
        return 0 if report["pass"] else 1
    finally:
        shutil.rmtree(os.path.dirname(kb), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
