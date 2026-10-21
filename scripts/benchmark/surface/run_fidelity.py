#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_fidelity.py —— 渲染保真度指标的 harness 驱动 + 报告落盘

复用 load_harness（与 run_probe.py 同款做法），驱动 fidelity_cli.mjs，
产出 results/fidelity-<label>_<sha>.{md,json}。

用法：
    python scripts/benchmark/surface/run_fidelity.py \
        --label baseline \
        --files corpus/01-ime-zh.md,corpus/04-non-editable.md,corpus/07-extremes.md \
        [--mutate char|math|strong|reorder]   # 变异测试（可选，一次一个）

约束：不改 src/**；--port 自动选（默认 8644，与 run_probe.py 的 8643 错开避免冲突）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_PATH = REPO_ROOT / "docs" / "example" / "rich-content-test" / "_harness.py"
RESULTS_DIR = REPO_ROOT / "scripts" / "benchmark" / "surface" / "results"
CDP_CLI = REPO_ROOT / "scripts" / "benchmark" / "surface" / "fidelity_cli.mjs"


def _load_kb_guard_wire():
    """加载 KB 守卫接线助手（task-57）。

    冻结语料缺失即报错：**拒绝在无守卫下运行测量**（R-17 已实际发生两次）。
    """
    import importlib.util as _ilu
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_kb_guard_wire.py")
    if not os.path.exists(_p):
        raise SystemExit("缺少 KB 守卫助手 _kb_guard_wire.py —— 拒绝在无守卫下运行测量")
    _spec = _ilu.spec_from_file_location("_kb_guard_wire", _p)
    if _spec is None or _spec.loader is None:
        raise SystemExit("无法加载 _kb_guard_wire.py")
    _m = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m


def _load_iso_config():
    """加载共用配置隔离助手（同目录 `_iso_config.py`）。

    隔离失败必须**直接报错**：静默降级回 ambient 会让测量在无提示的情况下失去密封性，
    正是 task-53 假红的成因。
    """
    import importlib.util as _ilu
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_iso_config.py")
    if not os.path.exists(_p):
        raise SystemExit("缺少配置隔离助手 _iso_config.py —— 拒绝在无隔离下运行测量")
    _spec = _ilu.spec_from_file_location("_iso_config", _p)
    if _spec is None or _spec.loader is None:
        raise SystemExit("无法加载 _iso_config.py")
    _m = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m


def load_harness(kb_dir: Path, port: int):
    os.environ["MEMORIA_HARNESS_KB"] = str(kb_dir)
    os.environ["MEMORIA_HARNESS_PORT"] = str(port)
    spec = importlib.util.spec_from_file_location("memoria_probe_harness", str(HARNESS_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wait_port(port: int, timeout: float = 20.0) -> bool:
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def git_short_sha() -> str:
    p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    return p.stdout.strip() or "nogit"


def main():
    ap = argparse.ArgumentParser(description="渲染保真度指标 runner")
    ap.add_argument("--kb", default="tests/probe-kb", help="源语料目录（相对 repo 根）")
    ap.add_argument("--label", default="baseline", help="报告 label")
    ap.add_argument("--port", type=int, default=8644, help="harness 端口（默认 8644）")
    ap.add_argument("--work-kb", default="artifacts/_probe_kb", help="临时语料副本目录")
    ap.add_argument("--files", default="", help="逗号分隔的相对文档路径；空则用内置三文档")
    ap.add_argument("--mutate", default=None, help="变异测试 kind：char|math|strong|reorder（可选）")
    ap.add_argument("--timeout", type=int, default=120, help="node 子进程超时秒数")
    ap.add_argument("--cdp", default=None,
                    help="真机模式：已运行应用的 CDP 端点（如 http://127.0.0.1:9500）。"
                         "给了它就不起 harness、直连真机；与 --url 语义互斥（本 runner 不起 --url）")
    ap.add_argument("--ready-timeout", type=int, default=None,
                    help="渲染就绪等待上限 ms（公式/mermaid 异步）；原样透传给 fidelity_cli.mjs")
    # ── 配置隔离（task-54）：默认密封，不继承开发机 config/ui-settings.json ──
    #   事故背景：ambient 的 search.embedding_enabled=true 会让搜索在单线程 harness 内
    #   同步构建 embedding 索引（阻塞 >45s），导致假红；同类泄漏也可能污染冻结基线。
    _iso_mod = _load_iso_config()
    _iso_mod.add_isolation_arg(ap)
    args = ap.parse_args()
    # ── KB 完整性守卫（task-57）：冻结语料只读 + 前后 sha 校验 ──
    #    ★ 用 try/finally 包裹主体，保证**任何 return 路径**都做后校验：
    #      主体内有 `return 0 if ... else 1` 早退，若把 end_guard 放在末尾语句，
    #      早退时会被跳过 ⇒ 守卫形同虚设（task-57 实测踩到）。
    _kbw = _load_kb_guard_wire()
    _kb_guard = _kbw.begin_guard(
        'run_fidelity', label=getattr(args, 'label', 'run'), writable=False,
    )
    try:
        return _run_fidelity_body(args)
    finally:
        _kbw.end_guard(_kb_guard)


def _run_fidelity_body(args):
    """run_fidelity 的主体（原 main 中 args 解析之后的部分）。"""
    # ── 应用配置隔离（task-54）：默认密封；--ambient-config 仅诊断 ──
    _iso = _iso_mod.isolate_config(
        script=__file__.rsplit(os.sep, 1)[-1].rsplit('.', 1)[0],
        label=getattr(args, 'label', 'run'),
        ambient=getattr(args, 'ambient_config', False),
    )
    print(_iso.describe())
    # ── 模式：real（--cdp）or headless（默认 harness）──
    #   !! 两种模式**绝不能混跑**：真机 MathJax 排 270 个、无头只排 ≈3，
    #      混着比就是假 diff。故 mode 显式标注并写进产物。
    mode = "real" if args.cdp else "headless"

    DEFAULT_FILES = [
        "corpus/03-block-boundaries.md",   # 小文档
        "corpus/04-non-editable.md",       # 含 table+math+mermaid 的教材
        "corpus/05-images.md",             # 图片（A5 断言样本）
        "corpus/07-extremes.md",           # 含 table+list
        "README.md",                       # 含 bold（A9 加粗样本）+ table + mermaid
    ]
    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else DEFAULT_FILES

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[fidelity] 源语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2

    if mode == "real":
        # 真机模式：**不复制语料、不起 harness**（应用已在自己的 KB 上运行）
        print("[fidelity] mode=real，直连 CDP: %s（不起 harness）" % args.cdp)
        work_kb = None
        harness = None
    else:
        work_kb = (REPO_ROOT / args.work_kb).resolve()
        if work_kb.exists():
            shutil.rmtree(work_kb, ignore_errors=True)
        work_kb.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_kb, work_kb)

        harness = load_harness(work_kb, args.port)
        import bottle
        th = threading.Thread(target=bottle.run, kwargs=dict(app=harness.app, host="127.0.0.1", port=args.port, quiet=True), daemon=True)
        th.start()
        if not wait_port(args.port):
            print("[fidelity] harness 未在端口 %s 起来" % args.port, file=sys.stderr)
            return 2

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sha = git_short_sha()
    label = args.label
    stem = "fidelity-%s_%s" % (label, sha)
    out_path = RESULTS_DIR / ("%s.json" % stem)

    # ── 构建 node 驱动命令：两种模式互斥（fidelity_cli.mjs 内含同样的互斥校验）──
    cmd = ["node", str(CDP_CLI)]
    if mode == "real":
        cmd += ["--cdp", args.cdp]
    else:
        cmd += ["--url", "http://127.0.0.1:%d/" % args.port]
    cmd += [
        "--files", ",".join(files),
        "--out", str(out_path),
    ]
    # 原样透传渲染就绪等待上限（公式/mermaid 异步；仅显式给出时透传，保持默认行为不变）
    if args.ready_timeout is not None:
        cmd += ["--ready-timeout", str(args.ready_timeout)]
    if args.mutate:
        cmd += ["--mutate", args.mutate]
    print("[fidelity] 运行: %s" % " ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[fidelity] node 驱动超时", file=sys.stderr)
        return 3
    if proc.returncode != 0 or not out_path.exists():
        print("[fidelity] node 驱动失败（code=%s）" % proc.returncode, file=sys.stderr)
        print("--- stdout ---\n%s\n--- stderr ---\n%s" % (proc.stdout.decode("utf-8", "replace")[-4000:], proc.stderr.decode("utf-8", "replace")[-8000:]), file=sys.stderr)
        return 3

    raw = json.loads(out_path.read_text(encoding="utf-8"))

    # ── 模式标注（**不得混跑**：真机/无头不可混比）──
    raw["mode"] = mode
    raw["cdp"] = args.cdp if mode == "real" else None
    raw["readyTimeoutMs"] = args.ready_timeout
    # 回写，保证落盘 JSON 自带模式标注（下游 Comparator 可据此拒绝跨模式比较）
    out_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # 渲染 markdown 报告
    md_path = RESULTS_DIR / ("%s.md" % stem)
    L = []
    L.append("# 渲染保真度 · %s（%s）\n" % (label, sha))
    L.append("> **mode = %s**%s" % (mode, "（真机 CDP：%s）" % args.cdp if mode == "real" else "（无头 harness）"))
    L.append("> ⚠️ 真机与无头**不可混比**：真机 MathJax 排 270 个，无头只排 ≈3；跨模式比较 = 假 diff\n")
    L.append("> 指标：`scripts/benchmark/surface/fidelity.mjs` + `fidelity_cli.mjs`")
    L.append("> 文档：%s" % "、".join(files))
    if args.mutate:
        L.append("> **变异测试**：`%s`（必须判 FAIL）\n" % args.mutate)
    else:
        L.append("")
    L.append("## A 级（硬门槛）整体：**%s**\n" % ("🟢 全绿" if raw.get("allGreen") else "🔴 有红"))

    # ── 渲染就绪（task-31/32）：只有 ready 的快照才可信 ──
    ready_rows = []
    for f, d in (raw.get("documents") or {}).items():
        rr = d.get("renderReady") or {}
        if not rr:
            continue
        mm = rr.get("math") or {}
        md_ = rr.get("mermaid") or {}
        ready_rows.append((f, rr.get("status"), rr.get("elapsedMs"),
                           "%s/%s" % (mm.get("nonEmpty"), mm.get("expected")) if mm.get("expected") else "-",
                           "%s/%s" % (md_.get("withSvg"), md_.get("containers")) if md_.get("containers") else "-"))
    if ready_rows:
        L.append("## 渲染就绪（task-31）\n")
        L.append("| 文档 | status | 等待 ms | 公式(已排/期望) | mermaid(有svg/容器) |")
        L.append("|---|---|---|---|---|")
        for f, st, el, math_c, mmd_c in ready_rows:
            icon = {"ready": "✅", "timeout": "⏱️", "failed": "🔴", "inconclusive": "⚪"}.get(st, "?")
            L.append("| `%s` | %s `%s` | %s | %s | %s |" % (f, icon, st, el, math_c, mmd_c))
        L.append("")
        L.append("> **只有 `ready` 的快照可信**；`timeout`/`failed` 表示快照可能早取或渲染异常；")
        L.append("> `inconclusive` = 无头环境（MathJax 排不完），**不据此判绿也不判红**。\n")


    # ── 变异测试判定（语义与常规相反：注入破坏后**必须**判红，否则说明指标没有判别力）──
    mutation_verdict = None
    if args.mutate:
        muts = [(f, d.get("mutation")) for f, d in (raw.get("documents") or {}).items() if d.get("mutation")]
        caught = [f for f, m in muts if m and not m.get("ok")]
        missed = [f for f, m in muts if m and m.get("ok")]
        mutation_verdict = {
            "kind": args.mutate,
            "documents": len(muts),
            "caughtRed": len(caught),
            "missed": missed,
            # 判别力成立 = 至少有一个文档被该变异抓成红
            "hasDiscriminatingPower": len(caught) > 0,
            # 全抓不到 ⇒ 指标对该类破坏无判别力 ⇒ 判 FAIL
            "verdict": "PASS" if len(caught) > 0 else "FAIL",
        }
        L.append("## 变异判别力：`%s` → **%s**\n" % (args.mutate, mutation_verdict["verdict"]))
        L.append("| 文档 | 变异后 A 级 | 期望 | 结果 |")
        L.append("|---|---|---|---|")
        for f, m in muts:
            ok = m.get("ok")
            L.append("| `%s` | %s | 🔴 必须红 | %s |" % (f, "🟢 仍绿" if ok else "🔴 抓到", "❌ 无判别力" if ok else "✓ 有判别力"))
        L.append("")
        L.append("- 抓到（判红）：**%d / %d** 文档" % (len(caught), len(muts)))
        if missed:
            L.append("- ⚠️ **未被抓到**：%s ⇒ 该变异类型在这些文档上无判别力" % "、".join("`%s`" % x for x in missed))
        L.append("")
    L.append("| 文档 | A 级 | 块数(A/DOM) | 签名 | 可复现 |")
    L.append("|---|---|---|---|---|")
    for f, d in (raw.get("documents") or {}).items():
        r1 = d.get("run1") or {}
        a = r1.get("aLevel") or {}
        a1 = a.get("a1") or {}
        ok = "🟢" if r1.get("ok") else "🔴"
        sig = (r1.get("signature") or "")[:12]
        rep = "✓" if d.get("reproducible") else "✗"
        L.append("| `%s` | %s | %s/%s | `%s…` | %s |" % (f, ok, r1.get("astCount"), r1.get("domCount"), sig, rep))
    L.append("")
    # 逐文档 A 级明细
    for f, d in (raw.get("documents") or {}).items():
        r1 = d.get("run1") or {}
        a = r1.get("aLevel") or {}
        L.append("### `%s`\n" % f)
        L.append("- A1 块数：%s" % ("PASS" if (a.get("a1") or {}).get("ok") else "FAIL（%s vs %s）" % ((a.get("a1") or {}).get("ast"), (a.get("a1") or {}).get("dom"))))
        a2 = a.get("a2") or {}
        L.append("- A2 块序+类型：%s（orderOk=%s，typeMismatch=%d 处）" % ("PASS" if a2.get("ok") else "FAIL", a2.get("orderOk"), len(a2.get("kindMismatch") or [])))
        a3 = a.get("a3") or {}
        L.append("- A3 公式：%s（块 %s/%s，行内 %s/%s，残留 %s）" % ("PASS" if a3.get("ok") else "FAIL", a3.get("blockWithTypesetMath"), a3.get("expectBlocks"), a3.get("blockWithInlineMath"), a3.get("expectInline"), a3.get("residual")))
        a4 = a.get("a4") or {}
        w1 = a4.get("w1") or []; w2 = a4.get("w2") or []
        L.append("- A4 看门狗：W1=%s（%d 空文本越界）W2=%s（%d classless）" % ("PASS" if not w1 else "FAIL", len(w1), "PASS" if not w2 else "FAIL", len(w2)))
        # B 级摘要
        b = r1.get("bLevel") or {}
        b5 = b.get("b5") or {}; b6 = b.get("b6") or {}
        L.append("- B5 文本（warn）：diff %d 块　B6 结构（warn）：diff %d 处" % (b5.get("diffCount", 0), b6.get("diffCount", 0)))
        if args.mutate and d.get("mutation"):
            m = d["mutation"]
            L.append("- **变异 `%s` 后 ok=%s**（期望 False ⇒ 判红）" % (m["kind"], m["ok"]))
        L.append("")
    md_path.write_text("\n".join(L), encoding="utf-8")
    print("[fidelity] 产物：\n  %s\n  %s" % (md_path, out_path))
    if mutation_verdict is not None:
        print("[fidelity] 变异 `%s` => %s（抓到 %d/%d 文档）" % (
            mutation_verdict["kind"], mutation_verdict["verdict"],
            mutation_verdict["caughtRed"], mutation_verdict["documents"]))
        return 0 if mutation_verdict["verdict"] == "PASS" else 1
    print("[fidelity] %s" % ("A 级全绿 ✓" if raw.get("allGreen") else "A 级有红 ✗（见报告）"))
    return 0



if __name__ == "__main__":
    sys.exit(main())
