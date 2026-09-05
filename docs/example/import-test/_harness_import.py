# -*- coding: utf-8 -*-
"""导入模块 UI 验证 harness（browseragent / 浏览器自动化驱动）。

提供四类能力，作为「测试时反馈机制」的载体：

1. 真实后端：bottle 静态服务真实前端 + UIAPI over HTTP /rpc（kb_path 预置，
   前端启动即自动打开该知识库——复用 initKb 的 get_kb_path 分支，无需原生对话框）。
2. 可编程「文件选择」桩：UIAPI.host 替换为 CannedHost，pick_directory /
   pick_import_files 从 FIFO 队列取 canned 值（POST /harness/pick），
   使「打开知识库 / 选择导入源目录 / 选择平面 txt」在无原生对话框时可确定复现。
3. 结构化运行记录（反馈机制核心）：
   - /rpc 全量记录（method/args/耗时/status/错误/trace），落 JSONL + 内存环形缓冲；
   - 前端 console / onerror / unhandledrejection 上报 POST /harness/console；
   - 测试步骤标记 POST /harness/mark（browseragent 每步写入断言与结论）；
   - GET /harness/report 汇总 {meta, marks, rpc, console, summary} 供 Agent 形成
     系统性反馈报告；文件同步落 <KB>/.memoria/harness/。
4. 确定性初始状态：--fresh 复位 KB（清 .md/.memoria 侧车/缓存/构建，重建空 manifest），
   保证「新建库」用例从空库开始可重复。

用法:
    python _harness_import.py [--kb <KB>] [--port 8643] [--fresh]
  默认: kb=docs/example/empty3, md_dir=docs/example/import-test/mdsrc,
        bundle=docs/example/import-test/bundle, flat=.../agent/batch-a.txt
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

sys.path.insert(0, r"d:\AAA_Jupyter\Memoria\src")

# Windows 管道 stdout 默认 cp1252，中文日志会 UnicodeEncodeError；强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

import bottle  # noqa: E402

from memoria.presentation.api.ui import UIAPI  # noqa: E402
from memoria.presentation import static_server  # noqa: E402
from memoria.presentation.paths import UI_STATIC_ROOT, UI_APP_INDEX  # noqa: E402

DEFAULT_KB = Path(__file__).resolve().parent.parent / "empty3"
FIXTURE = Path(__file__).resolve().parent

HERE = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description="导入模块 UI 验证 harness")
parser.add_argument("--kb", default=str(DEFAULT_KB), help="目标知识库目录（默认 empty3）")
parser.add_argument("--port", type=int, default=8643, help="监听端口（默认 8643）")
parser.add_argument(
    "--md-dir", default=str(FIXTURE / "mdsrc"), help="md_dir 夹具目录"
)
parser.add_argument(
    "--bundle", default=str(FIXTURE / "bundle"), help="kb_bundle 夹具目录"
)
parser.add_argument(
    "--flat", action="append", default=[str(FIXTURE / "agent" / "batch-a.txt")],
    help="flat 夹具文件（可多次）",
)
parser.add_argument(
    "--fresh", action="store_true", help="启动前复位 KB（清 md/侧车/缓存，重建空 manifest）"
)
ARGS = parser.parse_args()

KB = str(Path(ARGS.kb).resolve())
MD_DIR = str(Path(ARGS.md_dir).resolve())
BUNDLE_DIR = str(Path(ARGS.bundle).resolve())
FLAT_FILES = [str(Path(f).resolve()) for f in ARGS.flat]
PORT = ARGS.port

# 运行记录落盘目录（KB .memoria/harness/，empty*/ 已 gitignore，不入库）
RUN_DIR = Path(KB) / ".memoria" / "harness"
RUN_DIR.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%d-%H%M%S")
RPC_LOG = RUN_DIR / f"rpc-{TS}.jsonl"
REPORT_FILE = RUN_DIR / "latest-report.json"


def _log(msg: str) -> None:
    try:
        print(f"[import-harness] {msg}", flush=True)
    except (UnicodeEncodeError, OSError):
        pass


# ── 可编程「文件选择」桩（替代原生对话框）──────────────────────────
class CannedHost:
    """pick_directory/pick_import_files 从 FIFO 队列取 canned 值。"""

    frameless = False  # 浏览器 harness 无窗口外壳：get_window_chrome 走默认（原生窗口）

    def __init__(self) -> None:
        self._queue: deque[dict] = deque()
        self._default_dir: str | None = None
        self._default_files: list[str] = []

    def queue(self, pick: dict) -> None:
        self._queue.append(pick)

    def set_default_dir(self, path: str | None) -> None:
        self._default_dir = path

    def set_default_files(self, paths: list[str]) -> None:
        self._default_files = list(paths)

    def pick_directory(self) -> str | None:
        for _ in range(len(self._queue)):
            item = self._queue.popleft()
            if item.get("type") == "dir":
                return str(item.get("value") or "")
        return self._default_dir

    def pick_import_files(self) -> list[str]:
        for _ in range(len(self._queue)):
            item = self._queue.popleft()
            if item.get("type") == "files":
                val = item.get("value")
                if isinstance(val, list):
                    return [str(v) for v in val]
                if val:
                    return [str(val)]
        return list(self._default_files)


host = CannedHost()
# 打开知识库的原生对话框 fallback：默认指向目标 KB，避免误开
host.set_default_dir(KB)
api = UIAPI(kb_path=KB, host=host)

# ── 运行记录缓冲 ────────────────────────────────────────────────────
_lock = threading.Lock()
_rpc_buf: deque[dict] = deque(maxlen=2000)
_console_buf: deque[dict] = deque(maxlen=2000)
_marks: list[dict] = []
_STARTED = time.time()


def _now() -> str:
    return time.strftime("%H:%M:%S.") + f"{int(time.time()*1000)%1000:03d}"


def _record_rpc(entry: dict) -> None:
    with _lock:
        _rpc_buf.append(entry)
        try:
            with open(RPC_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass


def _summarize_result(result, method: str) -> dict:
    if isinstance(result, dict):
        summary = {"status": result.get("status")}
        for key in (
            "files_written", "files_unchanged", "files_skipped",
            "files_renamed", "files_overwritten", "sidecars_written",
            "kp_imported", "kp_skipped", "kp_renamed", "kp_overwritten",
            "errors", "warnings", "issues_count", "files_checked",
        ):
            if key in result:
                summary[key] = result[key]
        if result.get("status") == "error":
            msg = result.get("message")
            # 部分 RPC（如 validate_kb 发现问题时）仅 status=error 而无 message 键；
            # 避免把缺失键 str() 成 "None" 误导报告
            if msg:
                summary["message"] = str(msg)[:500]
        return summary
    return {"raw": str(result)[:200]}


# ── HTTP 应用 ────────────────────────────────────────────────────────
BRIDGE_SCRIPT = """
<script>
(function () {
  function report(level, text) {
    try {
      fetch("/harness/console", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: level, text: String(text) })
      }).catch(function () {});
    } catch (_e) {}
  }
  var proxy = new Proxy({}, {
    get: function (_t, prop) {
      if (prop === "then") return undefined;
      return function () {
        var args = Array.prototype.slice.call(arguments);
        return fetch("/rpc", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ method: prop, args: args })
        }).then(function (r) { return r.text(); })
          .then(function (t) {
            try { return JSON.parse(t); } catch (_e) { return t; }
          });
      };
    }
  });
  // 模拟 pywebview 异步就绪：先空壳，待全部脚本（含 app.js 依赖链）
  // 加载完再挂 api 并派发 pywebviewready，使 app.js onReady 初始化回调
  // 在所有模块定义后执行（否则晚于 app.js 加载的模块 init 会被跳过）。
  window.pywebview = {};
  setTimeout(function () {
    window.pywebview.api = proxy;
    window.dispatchEvent(new Event("pywebviewready"));
  }, 1200);
  (function () {
    var names = ["log", "info", "warn", "error", "debug"];
    for (var i = 0; i < names.length; i++) {
      (function (name) {
        var orig = console[name];
        console[name] = function () {
          try {
            var parts = Array.prototype.map.call(arguments, function (a) {
              return typeof a === "string" ? a : JSON.stringify(a);
            });
            report(name, parts.join(" "));
          } catch (_e) {}
          orig.apply(console, arguments);
        };
      })(names[i]);
    }
    window.addEventListener("error", function (e) {
      report("error", "[window.onerror] " + (e.message || "") + " @" + (e.filename || ""));
    });
    window.addEventListener("unhandledrejection", function (e) {
      var r = e && e.reason;
      report("error", "[unhandledrejection] " + (r && (r.stack || r.message) || String(r)).slice(0, 800));
    });
    window.addEventListener("memoriaready", function () {
      window.__MEMORIA_TEST__ = { ready: true };
      report("info", "[app-ready] memoriaready fired, api installed");
    });
  })();
})();
</script>
"""

app = bottle.Bottle()


@app.post("/rpc")
def rpc():
    try:
        data = json.loads(bottle.request.body.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"bad json: {exc}"}
    method = data.get("method") or ""
    args = data.get("args") or []
    if not isinstance(args, list):
        args = [args]
    started = time.time()
    entry = {"ts": _now(), "method": method, "args_trunc": str(args)[:600]}
    fn = getattr(api, method, None)
    if fn is None or not callable(fn):
        entry.update({"ok": False, "error": f"未知方法: {method}", "ms": 0})
        _record_rpc(entry)
        return {"status": "error", "message": f"未知方法: {method}"}
    try:
        result = fn(*args)
        entry.update(
            {
                "ok": True,
                "ms": round((time.time() - started) * 1000, 1),
                "result": _summarize_result(result, method),
            }
        )
        _record_rpc(entry)
        return result
    except Exception as exc:  # noqa: BLE001
        entry.update(
            {
                "ok": False,
                "ms": round((time.time() - started) * 1000, 1),
                "error": str(exc),
                "trace": traceback.format_exc(limit=3),
            }
        )
        _record_rpc(entry)
        return {
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(limit=3),
        }


@app.get("/")
def root():
    with open(UI_APP_INDEX, encoding="utf-8") as f:
        html = f.read()
    if "</head>" in html:
        html = html.replace("</head>", BRIDGE_SCRIPT + "</head>")
    else:
        html = BRIDGE_SCRIPT + html
    return bottle.HTTPResponse(
        html, headers={"Content-Type": "text/html; charset=utf-8"}
    )


@app.get("/<path:path>")
def asset(path: str):
    if path.startswith("files/"):
        result = static_server._serve_kb_file(path[len("files/") :])
        if result is not None:
            return result
        return bottle.HTTPResponse(status=404, body="File not found in KB")
    if path == "_kb_root_diag":
        return {"kb_root": static_server.get_kb_root()}
    resp = bottle.static_file(path, root=str(UI_STATIC_ROOT))
    if isinstance(resp, bottle.HTTPResponse):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


# ── 测试反馈通道 ────────────────────────────────────────────────────

@app.post("/harness/pick")
def harness_pick():
    """队列一个 canned 原生对话框返回值。
    body: {"type": "dir"|"files", "value": "path" | ["p1","p2"]}"""
    try:
        data = json.loads(bottle.request.body.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}
    host.queue(data)
    return {"status": "ok", "queue": len(host._queue)}


@app.post("/harness/mark")
def harness_mark():
    """记录一条测试步骤/断言。body: {"step","kind","ok","note","data"}"""
    try:
        data = json.loads(bottle.request.body.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}
    mark = {
        "ts": _now(),
        "step": data.get("step", ""),
        "kind": data.get("kind", "info"),
        "ok": bool(data.get("ok")),
        "note": data.get("note", ""),
        "data": data.get("data"),
    }
    with _lock:
        _marks.append(mark)
    return {"status": "ok", "count": len(_marks)}


@app.post("/harness/console")
def harness_console():
    """前端 console / 错误上报入口。"""
    try:
        data = json.loads(bottle.request.body.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}
    with _lock:
        _console_buf.append(
            {
                "ts": _now(),
                "level": data.get("level", "log"),
                "text": str(data.get("text", ""))[:2000],
            }
        )
    return {"status": "ok"}


@app.post("/harness/mutate")
def harness_mutate():
    """冲突播种：向 KB 内某文件追加内容，使重导出现 file/kp 冲突。

    body: {"rel": "imp-kp-alpha.md", "text": "\\n<!-- 冲突播种 -->"}
    """
    try:
        data = json.loads(bottle.request.body.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}
    rel = str(data.get("rel") or "").replace("\\", "/")
    text = str(data.get("text") or "")
    rel_parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not rel_parts or ".memoria" in rel_parts:
        return {"status": "error", "message": f"非法 rel: {rel!r}"}
    target = Path(KB).joinpath(*rel_parts)
    if not target.is_file():
        return {"status": "error", "message": f"文件不存在: {rel}"}
    target.write_text(target.read_text(encoding="utf-8") + text, encoding="utf-8")
    _log(f"mutate: {rel} 追加 {len(text)} 字符")
    return {"status": "ok", "rel": rel}


@app.get("/harness/state")
def harness_state():
    with _lock:
        rpc_tail = list(_rpc_buf)[-50:]
        console_tail = list(_console_buf)[-80:]
        marks = list(_marks)
    return {
        "status": "ok",
        "meta": {
            "kb": KB,
            "port": PORT,
            "started_ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_STARTED)),
            "uptime_s": round(time.time() - _STARTED, 1),
            "rpc_log": str(RPC_LOG),
        },
        "fixtures": {
            "md_dir": MD_DIR,
            "bundle": BUNDLE_DIR,
            "flat": FLAT_FILES,
        },
        "counts": {"rpc": len(_rpc_buf), "console": len(_console_buf), "marks": len(marks)},
        "rpc_tail": rpc_tail,
        "console_tail": console_tail,
        "marks": marks,
    }


@app.get("/harness/report")
def harness_report():
    """汇总结构化报告：meta + marks + 全量 rpc + console + 错误统计。"""
    with _lock:
        rpc_all = list(_rpc_buf)
        console_all = list(_console_buf)
        marks = list(_marks)
    errors = [r for r in rpc_all if not r.get("ok")]
    console_errors = [c for c in console_all if c.get("level") in ("error",)]
    report = {
        "meta": {
            "kb": KB,
            "port": PORT,
            "started_ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_STARTED)),
            "generated_ts": _now(),
            "rpc_log": str(RPC_LOG),
        },
        "fixtures": {"md_dir": MD_DIR, "bundle": BUNDLE_DIR, "flat": FLAT_FILES},
        "summary": {
            "rpc_calls": len(rpc_all),
            "rpc_errors": len(errors),
            "console_events": len(console_all),
            "console_errors": len(console_errors),
            "marks": len(marks),
        },
        "marks": marks,
        "rpc": rpc_all,
        "console": console_all[-500:],
    }
    try:
        REPORT_FILE.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError:
        pass
    return report


# ── 复位与启动 ───────────────────────────────────────────────────────

def _reset_kb(kb: str) -> None:
    """清空知识库为「全新空库」：删 .md/侧车/缓存/构建/pending，重建空 manifest。"""
    root = Path(kb)
    if not root.is_dir():
        _log(f"--fresh: 目录不存在 {kb}，跳过复位")
        return
    removed_files: list[str] = []
    for p in root.rglob("*.md"):
        if ".memoria" not in p.parts:
            p.unlink(missing_ok=True)
            removed_files.append(str(p.relative_to(root)))
    for sub in ("sidecars", "cache", "build", "images", "pending.yaml"):
        target = root / ".memoria" / sub
        if target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
    # 剪除 .md 清空后遗留的空目录（保留 .memoria 内部结构）
    for child in sorted(root.iterdir(), reverse=True):
        if child.is_dir() and child.name != ".memoria":
            try:
                child.rmdir()
            except OSError:
                pass  # 非空则保留
    (root / ".memoria").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00", time.gmtime()),
        "files": [],
    }
    (root / ".memoria" / "manifest.yaml").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # 记录复位于 RPC 日志之前，保证报告可追溯
    with open(RPC_LOG, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": _now(),
                    "method": "(harness--fresh-reset)",
                    "args_trunc": f"removed_md={removed_files}",
                    "ok": True,
                },
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        )
    _log(f"--fresh: 复位 {kb}，删除 .md {len(removed_files)} 个 → {removed_files}")


if __name__ == "__main__":
    if ARGS.fresh:
        _reset_kb(KB)
    _log(f"KB={KB}  ->  http://127.0.0.1:{PORT}/")
    _log(f"fixtures: md_dir={MD_DIR}  bundle={BUNDLE_DIR}  flat={FLAT_FILES}")
    _log(f"rpc log -> {RPC_LOG}   report -> {REPORT_FILE}")
    bottle.run(app, host="127.0.0.1", port=PORT, quiet=True)
