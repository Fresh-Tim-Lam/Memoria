# -*- coding: utf-8 -*-
"""boot 探针 · 后端侧：**不开窗口**，只量 boot 期间前端会依次同步调用的那几个重 RPC。

用途（task-69 测量阶段）：
    前端 `initKb()`（app.js）在自动打开首个文件**之前**按顺序 await 了：
        get_kb_path -> ensure_kb_root -> get_ui_settings(x N) ->
        list_files -> get_link_targets -> get_graph_data -> validate_kb
    本脚本在进程内直接调用同样的 `DocumentService` 方法，逐项量**后端执行时间**
    （不含 pywebview 的 HTTP/JS 桥往返；桥往返由 `_boot_launch.py` 的 UIAPI 包装量）。

为什么先跑它：
    ① 无 GUI ⇒ 可在任何机器上几秒内复现，用来快速定位"大头是不是后端解析/审计"；
    ② 冷/热两轮 ⇒ 区分"每次必付"与"可缓存/可延后"。

用法：
    .venv\\Scripts\\python.exe scripts/benchmark/surface/_boot_backend_probe.py \
        --kb <KB dir> --out artifacts/agent/verify/boot-backend-<label>.json

口径与限制：
    · 只读 KB（不写）；调用前请确保 --kb 指向**副本**或只读语料（validate/list 不写盘）；
    · `validate_kb` 会读全库 + 侧车 + 图谱；`get_graph_data` 会解析全库并做一次 graph audit
      ⇒ 两者都在本脚本里**各量两次**（冷/热），热轮复用 DocumentService 内存缓存。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]


def _utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _timed(label: str, fn, sink: list[dict]) -> object:
    t0 = time.perf_counter()
    ok = True
    err = None
    value = None
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001
        ok = False
        err = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    dt = (time.perf_counter() - t0) * 1000.0
    sink.append({"label": label, "ms": round(dt, 1), "ok": ok, "error": err})
    print(f"[backend] {label:42s} {dt:9.1f} ms  ok={ok}")
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--label", default="backend")
    ap.add_argument("--file", default="", help="首文档相对路径（默认取 list_files 第一个）")
    args = ap.parse_args()
    _utf8_stdio()

    kb = str(Path(args.kb).resolve())
    if not Path(kb).is_dir():
        print(f"[backend] KB 不存在: {kb}", file=sys.stderr)
        return 2

    # 配置隔离：不读开发机 config/ui-settings.json（见 _iso_config.py）
    cfg = Path(os.environ.get("TEMP", ".")) / "memoria_boot_probe" / f"cfg_backend_{os.getpid()}"
    cfg.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg)

    sys.path.insert(0, str(REPO_ROOT / "src"))
    t_import0 = time.perf_counter()
    from memoria.services.document import DocumentService  # noqa: E402

    import_ms = (time.perf_counter() - t_import0) * 1000.0
    print(f"[backend] import document service: {import_ms:.1f} ms")

    rows: list[dict] = []
    result: dict = {
        "schema": "memoria-boot-backend/v1",
        "label": args.label,
        "kb": kb,
        "importDocumentServiceMs": round(import_ms, 1),
        "pid": os.getpid(),
        "python": sys.version,
    }

    svc = None

    def _mk() -> DocumentService:
        nonlocal svc
        svc = DocumentService(kb_path=kb)
        return svc

    _timed("DocumentService(kb_path=)", _mk, rows)

    files_res = _timed("list_files", lambda: svc.list_files(), rows)
    rels = [f["path"] for f in ((files_res or {}).get("files") or [])]
    result["fileCount"] = len(rels)
    result["mdBytes"] = sum(
        (Path(kb) / rel).stat().st_size for rel in rels if (Path(kb) / rel).is_file()
    )

    _timed("get_link_targets", lambda: svc.get_link_targets(), rows)
    first = args.file or (rels[0] if rels else "")
    if first:
        doc = _timed(f"load_document({first})", lambda: svc.load_document(first), rows)
        if isinstance(doc, dict):
            result["firstDoc"] = {
                "path": first,
                "lines": len(doc.get("lines") or []),
                "status": doc.get("status"),
            }
    _timed("get_kb_pending", lambda: svc.get_kb_pending(), rows)
    # 阻塞首屏的两个重活：各量两次（冷/热）
    for rnd in (1, 2):
        _timed(f"get_graph_data  #{rnd}", lambda: svc.get_graph_data(), rows)
        _timed(f"validate_kb     #{rnd}", lambda: svc.validate_kb(), rows)

    # 纯 IO 基线：扫一遍全库 md 的字节读取（分离"磁盘慢"与"解析慢"）
    def _read_all() -> int:
        total = 0
        for rel in rels:
            total += len((Path(kb) / rel).read_bytes())
        return total

    _timed("read_all_md_bytes(IO baseline)", _read_all, rows)

    # ── 根因微证（task-69）：suggest_group_labels 对**每个分组**都重载一次
    #    `.memoria/cache/lexical/index.json`（无进程内缓存）⇒ 单组成本 ≈ 一次索引载入。
    try:
        from memoria.services import lexical_index as lex_mod
        from memoria.services.search_kernel import suggest_group_labels

        for i in (1, 2, 3):
            _timed(f"load_lexical_index #{i}", lambda: lex_mod.load_lexical_index(kb), rows)
        _timed(f"ensure_lexical_index #{1}", lambda: lex_mod.ensure_lexical_index(kb), rows)

        idx = lex_mod.load_lexical_index(kb) or {}
        recs = idx.get("records") or []
        ids = [r.get("kp_id") for r in recs[:3] if r.get("kp_id")]
        lex_size = (Path(kb) / ".memoria" / "cache" / "lexical" / "index.json").stat().st_size \
            if (Path(kb) / ".memoria" / "cache" / "lexical" / "index.json").is_file() else None
        result["lexicalIndex"] = {"bytes": lex_size, "records": len(recs),
                                  "inverted": len(idx.get("inverted") or {})}
        scaling = []
        for n in (10, 50, 100, 293):
            groups = [{"id": f"g{i}", "nodeIds": ids} for i in range(n)]
            t0 = time.perf_counter()
            suggest_group_labels(kb_path=kb, groups=groups)
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            scaling.append({"groups": n, "ms": ms, "msPerGroup": round(ms / n, 2)})
            print(f"[backend] suggest_group_labels({n:4d} groups) {ms:9.1f} ms  ({ms / n:.2f} ms/group)")
        result["suggestGroupLabelsScaling"] = scaling
    except Exception as exc:  # noqa: BLE001
        result["lexicalRootCauseError"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    result["steps"] = rows
    result["totalMs"] = round(sum(r["ms"] for r in rows), 1)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, "utf-8")
        print(f"[backend] wrote {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
