# -*- coding: utf-8 -*-
"""boot 探针 · 子进程启动器（**只做测量，不改产品行为**）。

它 `import` 真实 Memoria 并走 `memoria.app.desktop.main()`，与 `python app.py`
完全同一条启动路径；区别只有两件事（都不改 `src/**`）：
  1. 在**导入前**给关键函数套上计时器（Python 侧 span）；
  2. 把 span 逐行 JSONL 落盘（每行 flush，进程被杀也不丢已发生的阶段）。

被套计时的对象（按启动阶段展开"13–23s 花在哪"）：
  · `DocumentService.__init__` / `UIAPI.__init__`  —— 开库前的服务构建
  · `webview.create_window` / `webview.start` / `BottleServer.start_server` —— 壳
  · `UIAPI.*` —— 前端每一次 RPC 的**服务端**执行时间（不含 JS 桥往返）
  · `DocumentService.{list_files,load_document,get_link_targets,get_graph_data,validate_kb,...}`
    —— 定位 UIAPI 内部真正的重活
  · `memoria.graph.collector.collect_graph_data` / `graph.link_audit.audit_kb_graph_links`
    / `storage.kb_integrity.audit_kb_integrity` / `storage.manifest.audit_manifest_diff`
    / `storage.path_cascade.detect_path_moves` / `services.kp_index.build_kp_index`
    —— 把 get_graph_data / validate_kb 再拆一层（两者都全库解析 + graph audit）

用法（一般由 `run_boot_profile.py` 调用，不直接跑）：
    BOOT_PROBE_JSONL=<path> MEMORIA_KB=<kb> MEMORIA_CONFIG_DIR=<cfg> \
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9661 \
    .venv\\Scripts\\python.exe scripts/benchmark/surface/_boot_launch.py

契约：
  · 环境里没有 `BOOT_PROBE_JSONL` 时**只启动、不写任何文件**（零副作用）；
  · 任何包装失败都只降级为"没这一条 span"，绝不改变产品调用结果。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

T0_PERF = time.perf_counter()
T0_WALL = time.time()
_PID = os.getpid()
_LOCK = threading.Lock()
_OUT = os.environ.get("BOOT_PROBE_JSONL", "").strip()
_SEQ = 0


def emit(kind: str, **fields) -> None:
    """追加一行 JSONL（无 BOOT_PROBE_JSONL 时 no-op）。"""
    global _SEQ
    if not _OUT:
        return
    with _LOCK:
        _SEQ += 1
        rec = {
            "seq": _SEQ,
            "kind": kind,
            "t": round(time.perf_counter() - T0_PERF, 3),
            # wall 统一用**毫秒 epoch**，与浏览器侧 `performance.timeOrigin`（ms）同一量纲
            "wall": round((T0_WALL + (time.perf_counter() - T0_PERF)) * 1000.0, 3),
            "pid": _PID,
            "thread": threading.current_thread().name,
        }
        rec.update(fields)
        try:
            with open(_OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass


def _brief(args: tuple, kwargs: dict) -> str:
    try:
        parts = [repr(a)[:160] for a in args]
        if kwargs:
            parts.append("kwargs=" + repr(kwargs)[:160])
        return ", ".join(parts)[:400]
    except Exception:
        return "<unrepr>"


def _result_brief(value) -> dict:
    """只留**低代价**的结构信息：状态 + 计数（不序列化大 payload）。"""
    info: dict = {"type": type(value).__name__}
    try:
        if isinstance(value, dict):
            for k in ("status", "message", "error"):
                if k in value:
                    info[k] = str(value[k])[:200]
            for k in ("files", "dirs", "lines", "blocks", "nodes", "edges",
                      "issues_count", "files_checked", "items"):
                v = value.get(k)
                if isinstance(v, (list, tuple, dict, str)):
                    info["n_" + k] = len(v)
                elif isinstance(v, (int, float, bool)):
                    info[k] = v
        elif isinstance(value, (list, tuple, dict, str)):
            info["len"] = len(value)
    except Exception:
        pass
    return info


def wrap(owner, name: str, label: str, *, extra=None) -> bool:
    """给 `owner.name` 套计时器；返回是否成功（失败静默）。"""
    try:
        orig = getattr(owner, name)
    except Exception:
        return False
    if orig is None or not callable(orig):
        return False
    if getattr(orig, "__boot_probe_wrapped__", False):
        return True

    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        emit("span_start", name=label, args=_brief(args, kwargs), **(extra or {}))
        ok = True
        err = None
        value = None
        try:
            value = orig(*args, **kwargs)
            return value
        except Exception as exc:  # noqa: BLE001
            ok = False
            err = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            t1 = time.perf_counter()
            emit(
                "span",
                name=label,
                ms=round((t1 - t0) * 1000.0, 2),
                ok=ok,
                error=err,
                result=_result_brief(value),
                **(extra or {}),
            )

    wrapper.__boot_probe_wrapped__ = True
    wrapper.__wrapped__ = orig
    try:
        setattr(owner, name, wrapper)
    except Exception:
        return False
    return True


def wrap_many(owner, names, prefix: str) -> list[str]:
    done = []
    for n in names:
        if wrap(owner, n, f"{prefix}.{n}"):
            done.append(n)
    return done


def main() -> int:
    # --probe-port 只用于**进程身份校验**（safe-kill.psm1 要求命令行含本次调试端口），
    # 本脚本不读取它做任何事。
    probe_port = ""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--probe-port" and i + 1 < len(argv):
            probe_port = argv[i + 1]
    emit(
        "proc_start",
        t0_wall_epoch=round(T0_WALL * 1000.0, 3),
        probe_port=probe_port,
        argv=argv,
        python=sys.version,
        executable=sys.executable,
        frozen=bool(getattr(sys, "frozen", False)),
        cwd=os.getcwd(),
        env={k: v for k, v in os.environ.items()
             if k.startswith(("MEMORIA_", "WEBVIEW2_", "PYTHON"))},
    )

    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    t = time.perf_counter()
    # ── 1) 最重的被调方：DocumentService（先导入先包装，避免 ui.py 绑死未包装引用）
    import memoria.services.document as doc_mod

    emit("import", name="memoria.services.document", ms=round((time.perf_counter() - t) * 1000, 1))
    wrap(doc_mod, "collect_md_files", "doc.collect_md_files")
    wrap_many(
        doc_mod.DocumentService,
        [
            "__init__",
            "set_kb_path",
            "list_files",
            "load_document",
            "get_link_targets",
            "get_graph_data",
            "get_graph_audit",
            "validate_kb",
            "get_kb_pending",
        ],
        "DocumentService",
    )

    # ── 2) 图谱/完整性/清单：把 get_graph_data 与 validate_kb 拆开
    t = time.perf_counter()
    try:
        import memoria.graph.collector as graph_collector
        import memoria.graph.link_audit as graph_link_audit
        import memoria.services.kp_index as kp_index_mod
        import memoria.storage.kb_integrity as kb_integrity_mod
        import memoria.storage.manifest as manifest_mod
        import memoria.storage.path_cascade as path_cascade_mod

        emit("import", name="graph/storage modules", ms=round((time.perf_counter() - t) * 1000, 1))
        wrap(graph_collector, "collect_graph_data", "graph.collect_graph_data")
        wrap(graph_link_audit, "audit_kb_graph_links", "graph.audit_kb_graph_links")
        wrap(kb_integrity_mod, "audit_kb_integrity", "storage.audit_kb_integrity")
        wrap(manifest_mod, "audit_manifest_diff", "storage.audit_manifest_diff")
        wrap(path_cascade_mod, "detect_path_moves", "storage.detect_path_moves")
        wrap(kp_index_mod, "build_kp_index", "services.build_kp_index")
    except Exception as exc:  # noqa: BLE001
        emit("wrap_error", name="graph/storage", error=str(exc))

    # ── 2b) 词法索引载入次数（task-69 实测根因：suggest_group_labels 每个分组
    #        都重新 load 一次 .memoria/cache/lexical/index.json ⇒ 观测"载入 N 次"）
    try:
        import memoria.services.lexical_index as lex_mod

        _lex_stat = {"ensure_calls": 0, "load_calls": 0, "ensure_ms": 0.0, "load_ms": 0.0}

        def _stat_wrap(fn, calls_key: str, ms_key: str, name: str):
            def wrapper(*a, **kw):
                t0 = time.perf_counter()
                try:
                    return fn(*a, **kw)
                finally:
                    _lex_stat[calls_key] += 1
                    _lex_stat[ms_key] += (time.perf_counter() - t0) * 1000.0
                    if _lex_stat[calls_key] % 50 == 0:
                        emit("lexical_load_stat", name=name,
                             **{k: (round(v, 1) if isinstance(v, float) else v)
                                for k, v in _lex_stat.items()})
            wrapper.__boot_probe_wrapped__ = True
            return wrapper

        lex_mod.ensure_lexical_index = _stat_wrap(
            lex_mod.ensure_lexical_index, "ensure_calls", "ensure_ms", "ensure_lexical_index")
        lex_mod.load_lexical_index = _stat_wrap(
            lex_mod.load_lexical_index, "load_calls", "load_ms", "load_lexical_index")

        import atexit

        def _lex_final() -> None:
            emit("lexical_load_stat_final", name="final",
                 **{k: (round(v, 1) if isinstance(v, float) else v)
                    for k, v in _lex_stat.items()})

        atexit.register(_lex_final)
    except Exception as exc:  # noqa: BLE001
        emit("wrap_error", name="lexical_index", error=str(exc))

    # ── 3) 壳：pywebview 的窗口/服务启动（含 create_window 前的 KB 解析）
    t = time.perf_counter()
    import webview

    emit("import", name="webview", ms=round((time.perf_counter() - t) * 1000, 1))
    wrap(webview, "create_window", "webview.create_window")
    wrap(webview, "start", "webview.start")
    try:
        # start_server 是 classmethod：取到已绑定 cls 的对象再包，最后以 staticmethod 装回
        _srv = webview.http.BottleServer.start_server

        def _start_server(*a, **kw):
            t0 = time.perf_counter()
            emit("span_start", name="BottleServer.start_server", args=_brief(a, kw))
            try:
                out = _srv(*a, **kw)
                emit("span", name="BottleServer.start_server",
                     ms=round((time.perf_counter() - t0) * 1000, 2), ok=True,
                     result={"address": str(out[0]) if isinstance(out, tuple) else None})
                return out
            except Exception as exc:  # noqa: BLE001
                emit("span", name="BottleServer.start_server",
                     ms=round((time.perf_counter() - t0) * 1000, 2), ok=False, error=str(exc))
                raise

        webview.http.BottleServer.start_server = staticmethod(_start_server)
    except Exception as exc:  # noqa: BLE001
        emit("wrap_error", name="bottle", error=str(exc))

    # ── 4) 前端 API 面（RPC 服务端执行时间）
    t = time.perf_counter()
    import memoria.presentation.api.ui as ui_mod

    emit("import", name="memoria.presentation.api.ui", ms=round((time.perf_counter() - t) * 1000, 1))
    wrapped = 0
    for name, member in list(vars(ui_mod.UIAPI).items()):
        if name.startswith("__") or not callable(member):
            continue
        if isinstance(member, property):
            continue
        if wrap(ui_mod.UIAPI, name, f"UIAPI.{name}"):
            wrapped += 1
    emit("wrap_done", name="UIAPI", count=wrapped)
    wrap(ui_mod.UIAPI, "__init__", "UIAPI.__init__")

    # ── 5) 静态服务请求（页面把 index.html / 50 个 JS / CSS 逐个拉走的时间点）
    import memoria.app.shell.pywebview as pv

    _create_app = pv.create_app

    def _create_app_wrapped():
        app = _create_app()

        def _wsgi(environ, start_response):
            path = environ.get("PATH_INFO") or ""
            method = environ.get("REQUEST_METHOD") or ""
            t0 = time.perf_counter()
            emit("http_req_start", path=path, method=method)

            def _sr(status, headers, exc_info=None):
                emit("http_req_headers", path=path, method=method, status=str(status),
                     ms=round((time.perf_counter() - t0) * 1000, 2))
                return start_response(status, headers, exc_info)

            try:
                body = app(environ, _sr)
            except Exception as exc:  # noqa: BLE001
                emit("http_req_error", path=path, error=str(exc))
                raise
            emit("http_req_done", path=path, method=method,
                 ms=round((time.perf_counter() - t0) * 1000, 2))
            return body

        return _wsgi

    pv.create_app = _create_app_wrapped

    # ── 6) 真正启动（与 python app.py 同一条路径）
    t = time.perf_counter()
    emit("launcher_ready", imports_ms=round((time.perf_counter() - T0_PERF) * 1000, 1))
    import memoria.app.desktop as desktop

    emit("before_desktop_main")
    try:
        desktop.main()
        emit("after_desktop_main")
        return 0
    except SystemExit as exc:
        emit("desktop_systemexit", code=getattr(exc, "code", None))
        return int(getattr(exc, "code", 0) or 0)
    except BaseException as exc:  # noqa: BLE001
        emit("desktop_crash", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        emit("proc_exit")
