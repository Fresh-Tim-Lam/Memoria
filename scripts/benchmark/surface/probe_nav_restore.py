# -*- coding: utf-8 -*-
"""导航位置记忆探针运行器（2026-10-06）。

编排（复用 `run_probe.py` / `_harness.py` 的既有做法）：
  1) bottle 静态服务 + `/rpc` → `UIAPI` + 注入假 `window.pywebview.api` 桥；
  2) 起 Node 子进程 `scripts/benchmark/surface/cdp.mjs --nav-probe`（CDP 直连 Edge，零新依赖）；
  3) 语料从 `tests/probe-kb` 复制到 `artifacts/_nav_probe_kb`（源目录无 `.memoria/`，由应用自初始化），
     **不改动 `tests/probe-kb/**`**；
  4) 报告落 `results/probe-nav-restore_<sha>.{json,md}`；截图落 `artifacts/_nav_probe/`。

断言（见 cdp.mjs `runNavProbe` 头注）：S1 跨文件后退/前进；S2 同文件两个位置可区分；S3 文件树打开回原处。
绿/红按「首屏第一块 data--src-line 是否命中目标行 ±1」判，读数如实落盘，不默认成绿。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]  # scripts/benchmark/surface -> repo root
HARNESS_PATH = REPO_ROOT / "docs" / "example" / "rich-content-test" / "_harness.py"
CDP_MJS = HERE / "cdp.mjs"
RESULTS_DIR = HERE / "results"


def git_short_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8", "replace").strip() or "nogit"
    except Exception:
        return "nogit"


def node_version() -> str:
    try:
        return subprocess.check_output(["node", "--version"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def load_harness(kb_dir: Path, port: int):
    os.environ["MEMORIA_HARNESS_KB"] = str(kb_dir)
    os.environ["MEMORIA_HARNESS_PORT"] = str(port)
    spec = importlib.util.spec_from_file_location("memoria_nav_probe_harness", str(HARNESS_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # 只执行模块级定义；bottle.run 由我们另起线程
    return mod


def wait_port(port: int, timeout: float = 20.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.15)
    return False


def build_report_md(meta, raw):
    s = (raw.get("scenarios") or {}).get("S1_back_forward") or {}
    s2 = (raw.get("scenarios") or {}).get("S2_same_file_two_positions") or {}
    s3 = (raw.get("scenarios") or {}).get("S3_file_tree_open") or {}
    summ = raw.get("summary") or {}

    def badge(v):
        return "🟢 通过" if v else "🔴 未通过"

    L = []
    L.append("# 导航位置记忆探针报告（前进/后退 + 按文件）\n")
    L.append("> label `%s` ｜ git `%s` ｜ 生成 %s" % (meta["label"], meta["sha"], meta["generated_at"]))
    L.append("> 驱动：CDP 真机 Edge + harness（`_harness.py`）；**端到端（应用级集成）**，非单元级。")
    L.append("> 语料：`tests/probe-kb` 的副本 `%s`（源目录未被改动）\n" % meta["workKb"])

    L.append("## 环境\n")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    for k, v in meta["env"].items():
        L.append("| %s | %s |" % (k, v))
    L.append("")

    L.append("## 结论\n")
    L.append("| # | 断言 | 结论 | 读数 |")
    L.append("|---|---|---|---|")

    def row(name, title, ok, reading):
        L.append("| %s | %s | %s | %s |" % (name, title, badge(ok), reading))

    row("S1a", "后退回到 A 的离开位置（命中 L±1）", summ.get("S1_back_hitLA"),
        "A 行数=%s，目标 L=%s，离开时锚点=%s ⇒ 后退后首屏首块=[%s,%s] 顶部=%s" % (
            s.get("linesA"), s.get("LA"), s.get("anchorA"),
            (s.get("afterBack") or {}).get("first", {}).get("start") if (s.get("afterBack") or {}).get("first") else None,
            (s.get("afterBack") or {}).get("first", {}).get("end") if (s.get("afterBack") or {}).get("first") else None,
            (s.get("afterBack") or {}).get("top")))
    row("S1b", "前进回到 B 的离开位置（命中 L±1）", summ.get("S1_forward_hitLB"),
        "B 行数=%s，目标 L=%s，离开时锚点=%s ⇒ 前进后首屏首块=[%s,%s] 顶部=%s" % (
            s.get("linesB"), s.get("LB"), s.get("anchorB"),
            (s.get("afterForward") or {}).get("first", {}).get("start") if (s.get("afterForward") or {}).get("first") else None,
            (s.get("afterForward") or {}).get("first", {}).get("end") if (s.get("afterForward") or {}).get("first") else None,
            (s.get("afterForward") or {}).get("top")))
    row("S2a", "同文件：后退 1 次命中 L2", summ.get("S2_back1_hitL2"),
        "L1=%s / L2=%s ⇒ 后退#1 首屏首块=[%s,%s] 顶部=%s" % (
            s2.get("L1"), s2.get("L2"),
            (s2.get("back1") or {}).get("first", {}).get("start") if (s2.get("back1") or {}).get("first") else None,
            (s2.get("back1") or {}).get("first", {}).get("end") if (s2.get("back1") or {}).get("first") else None,
            (s2.get("back1") or {}).get("top")))
    row("S2b", "同文件：后退 2 次命中 L1", summ.get("S2_back2_hitL1"),
        "⇒ 后退#2 首屏首块=[%s,%s] 顶部=%s" % (
            (s2.get("back2") or {}).get("first", {}).get("start") if (s2.get("back2") or {}).get("first") else None,
            (s2.get("back2") or {}).get("first", {}).get("end") if (s2.get("back2") or {}).get("first") else None,
            (s2.get("back2") or {}).get("top")))
    row("S3", "文件树点开也回原处（命中 L±1）", summ.get("S3_tree_hitL"),
        "L=%s，锚点=%s，选择器 `%s`，点击=%s ⇒ 首屏首块=[%s,%s] 顶部=%s" % (
            s3.get("L"), s3.get("anchor"), s3.get("treeSelector"), (s3.get("treeClick") or {}).get("ok"),
            (s3.get("afterTreeOpen") or {}).get("first", {}).get("start") if (s3.get("afterTreeOpen") or {}).get("first") else None,
            (s3.get("afterTreeOpen") or {}).get("first", {}).get("end") if (s3.get("afterTreeOpen") or {}).get("first") else None,
            (s3.get("afterTreeOpen") or {}).get("top")))
    L.append("\n- 总判定：**%s**\n" % ("🟢 全部通过" if summ.get("allPass") else "🔴 有未通过项"))

    if raw.get("error"):
        L.append("## 运行错误（如实）\n")
        L.append("- `%s`\n" % raw.get("error"))

    L.append("## 备注（口径）\n")
    L.append("- 顶栏按钮 / 文件树项走 **CDP 真实鼠标点按**；内容打开走真实入口 `MemoriaApp.openFile`。")
    L.append("- 目标行 L：**从实际已渲染的块中按比例挑（~50% / ~75%）**取该块起始行（保证 L 必被某块覆盖）。因 `scale-*.md` 含 mermaid，首次预览渲染可能被 mermaid/初始化并发挡成半截 ⇒ 运行器先做一次 B→A **预热**并 settle 后再测。")
    L.append("- 「文件树双击」：该树绑定的是 `click`（`.-tree-item`），双击=连续两次 click、行为幂等；本探针用**真实鼠标单击**驱动同一条真实入口。")
    L.append("- 落点读数在初始恢复后 ~2s（越过落点二次校准 350ms/1400ms）稳定时采集；命中判据 = 首屏第一块 `data--src-line..data--src-line-end` 覆盖 L±1。")
    L.append("- S2 用 `openFile(fileA,{kpId})` 在同一文件上进新导航帧（这是 `jumpToTarget` 走的同一条真实入栈路径）。")
    L.append("- 诊断（不改应用行为）：页内对 `MemoriaNavStack.push/clear/navBack/navForward` 做**透传包装**记录调用（`navDiagLog`/`navPushLog`），用于定位早期一次「探针与 `initKb` 竞态」。")
    L.append("- 探针等待口径：`app-ready` 需 `state.files.length>0`（`initKb` 会在其后再 `NavStack.clear()`；过早操作会被清栈——这是探针自身的竞态，不是产品缺陷）。")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="nav position-memory probe runner")
    ap.add_argument("--kb", default="tests/probe-kb", help="源语料目录（相对 repo 根）")
    ap.add_argument("--label", default="nav-restore", help="报告 label")
    ap.add_argument("--port", type=int, default=8644, help="harness 端口")
    ap.add_argument("--work-kb", default="artifacts/_nav_probe_kb", help="临时语料副本目录")
    ap.add_argument("--shots", default="artifacts/_nav_probe", help="截图目录（不入库）")
    ap.add_argument("--file-a", default="scale/scale-1k.md")
    ap.add_argument("--file-b", default="scale/scale-5k.md")
    ap.add_argument("--timeout", type=int, default=600, help="node 子进程超时秒数")
    args = ap.parse_args()

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[nav-probe] 源语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2

    work_kb = (REPO_ROOT / args.work_kb).resolve()
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, work_kb)
    had_memoria = (src_kb / ".memoria").exists()
    print("[nav-probe] 语料副本: %s -> %s" % (src_kb, work_kb))

    harness = load_harness(work_kb, args.port)
    import bottle  # harness 已导入
    th = threading.Thread(
        target=bottle.run,
        kwargs=dict(app=harness.app, host="127.0.0.1", port=args.port, quiet=True),
        daemon=True,
    )
    th.start()
    if not wait_port(args.port):
        print("[nav-probe] harness 未能在端口 %s 起来" % args.port, file=sys.stderr)
        return 2
    print("[nav-probe] harness 就绪: http://127.0.0.1:%s/" % args.port)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    shots_dir = (REPO_ROOT / args.shots).resolve()
    sha = git_short_sha()
    stem = "probe-%s_%s" % (args.label, sha)
    raw_path = RESULTS_DIR / ("raw-%s.json" % stem)

    cmd = [
        "node", str(CDP_MJS), "--nav-probe",
        "--url", "http://127.0.0.1:%d/" % args.port,
        "--kb-root", str(work_kb),
        "--out", str(raw_path),
        "--shots", str(shots_dir),
        "--file-a", args.file_a,
        "--file-b", args.file_b,
    ]
    print("[nav-probe] 运行: %s" % " ".join(cmd))
    t0 = time.time()
    raw = None
    attempt = 0
    while attempt < 2:
        attempt += 1
        try:
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            print("[nav-probe] node 驱动超时", file=sys.stderr)
            return 3
        if not raw_path.exists():
            print("[nav-probe] node 驱动未产出 raw（code=%s）" % proc.returncode, file=sys.stderr)
            print("--- stdout ---\n%s\n--- stderr ---\n%s" %
                  (proc.stdout.decode("utf-8", "replace")[-4000:], proc.stderr.decode("utf-8", "replace")[-8000:]),
                  file=sys.stderr)
            return 3
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        err = str(raw.get("error") or "")
        # 偶发的 harness fetch 抖动（URL 已就绪但个别 /rpc 请求网络层失败）→ 重跑一次
        if "Failed to fetch" in err and attempt < 2:
            print("[nav-probe] 命中偶发 fetch 抖动，重试一次：%s" % err)
            time.sleep(1.5)
            continue
        break
    dur = time.time() - t0
    print("[nav-probe] node 驱动完成（%.1fs, attempts=%s）" % (dur, attempt))
    meta = {
        "label": args.label, "sha": sha,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workKb": str(work_kb),
        "env": {
            "browser": raw.get("browser"),
            "edge": raw.get("edgePath"),
            "node": node_version(),
            "kbServed": str(work_kb),
            "kbSource": str(src_kb),
            "kbSourceHasMemoria": ("是" if had_memoria else "否（已用副本让应用自初始化）"),
            "fileA": raw.get("fileA"), "fileB": raw.get("fileB"),
            "durationMs": raw.get("durationMs"),
            "consoleErrors": len((raw.get("console") or {}).get("errors") or []),
        },
    }
    rep_json = {
        "schema": "surface-nav-restore-report/1",
        "label": args.label, "gitSha": sha, "generatedAt": meta["generated_at"],
        "environment": meta["env"],
        "summary": raw.get("summary"),
        "scenarios": raw.get("scenarios"),
        "console": raw.get("console"),
        "error": raw.get("error"),
        "rawPath": str(raw_path.relative_to(REPO_ROOT)),
    }
    rep_md = build_report_md(meta, raw)
    jpath = RESULTS_DIR / (stem + ".json")
    mpath = RESULTS_DIR / (stem + ".md")
    jpath.write_text(json.dumps(rep_json, ensure_ascii=False, indent=2), encoding="utf-8")
    mpath.write_text(rep_md, encoding="utf-8")

    print("\n[nav-probe] ===== 结论摘要 =====")
    print(json.dumps(raw.get("summary") or {}, ensure_ascii=False, indent=2))
    print("\n[nav-probe] 产物：\n  %s\n  %s\n  raw: %s" % (jpath, mpath, raw_path))
    if raw.get("error"):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
