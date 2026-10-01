# -*- coding: utf-8 -*-
"""显示子系统探针运行器（surface probe runner）。

编排：
  1) 复用 `docs/example/rich-content-test/_harness.py` 的做法：bottle 静态服务 +
     `/rpc` → `UIAPI` + 注入假 `window.pywebview.api` 桥（见该文件的 `BRIDGE_SCRIPT`）；
  2) 起 Node 子进程 `scripts/benchmark/surface/cdp.mjs --probe`（CDP 直连 Edge，零新依赖）；
  3) 读 `tests/probe-kb/cases/cases.json`，对 legacy 插头执行可测用例 → 判定 C1–C12；
  4) 产出 `results/probe-<surface>-<label>_<sha>.{json,md}`。

用法：
    python scripts/benchmark/surface/run_probe.py --kb tests/probe-kb --label legacy-baseline

口径（严格遵守 `scripts/benchmark/surface/README.md` 与 `view-surface-contract.md §5`）：
  - 绿/红按**契约**判（真源文本 + 行为契约），不按"与老实现一致"判；
  - 未覆盖/未能测的 C **标「未测」并写明原因**，绝不默认成绿；
  - 性能读数**绑定文档规模**（本运行器用 `scale/scale-5k.md`，报告写明其真实行数）；
  - C11/C12 因 `new` 插头不存在必然「未测」。
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

CONTRACT = "docs/design/view-surface-contract.md#5（契约测试清单 C1–C12）"


# ─────────────────────────────────────────────────────────────────────────────
# git / 环境
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# harness（复用 _harness.py 的做法）
# ─────────────────────────────────────────────────────────────────────────────
def load_harness(kb_dir: Path, port: int):
    os.environ["MEMORIA_HARNESS_KB"] = str(kb_dir)
    os.environ["MEMORIA_HARNESS_PORT"] = str(port)
    spec = importlib.util.spec_from_file_location("memoria_probe_harness", str(HARNESS_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # 只执行模块级定义（UIAPI + 路由），bottle.run 由我们另起线程
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


# ─────────────────────────────────────────────────────────────────────────────
# 判定 C1–C12
# ─────────────────────────────────────────────────────────────────────────────
def _ev(raw: dict, case_id: str) -> dict:
    c = (raw.get("cases") or {}).get(case_id) or {}
    return c.get("evidence") or {}


def judge(raw: dict):
    """返回 {c_id: {"status": green/red/untested, "reading": str, "detail": {...}}}"""
    verdicts: dict[str, dict] = {}

    # C2 文本保真
    ev = _ev(raw, "sel_text_fidelity")
    if "bodyEqualsDisk" in ev:
        ok = bool(ev["bodyEqualsDisk"])
        verdicts["C2"] = {
            "status": "green" if ok else "red",
            "reading": ("打开 01-ime-zh.md 不编辑：state.doc.body %s 磁盘文件（len body=%s / disk=%s）"
                        % ("逐字等于" if ok else "**不等于**", ev.get("bodyLen"), ev.get("diskLen"))),
            "detail": ev,
        }
    else:
        verdicts["C2"] = {"status": "untested", "reading": "用例未跑出读数", "detail": {}}

    # C3 / C4 打字当帧可见 / 真源不落后
    ev = _ev(raw, "sel_typing_ascii")
    after = ev.get("after") or {}
    setup = ev.get("setup") or {}
    if after:
        c3_ok = bool(after.get("domHasChar"))
        c4_ok = bool(after.get("srcHasChar")) and bool(setup.get("caretMapsToBlock"))
        verdicts["C3"] = {
            "status": "green" if c3_ok else "red",
            "reading": ("受信任输入 keyDown(text='a') 后**不等 rAF** 立刻读 DOM：块文本 %s 'a'"
                        % ("已含" if c3_ok else "**不含**")),
            "detail": {"domText": after.get("domText"), "domHasChar": after.get("domHasChar"),
                       "srcLineText": after.get("srcLineText")},
        }
        verdicts["C4"] = {
            "status": "green" if c4_ok else "red",
            "reading": ("同一次按键后立刻读真源：state.doc.lines[L] %s；caret→块映射 %s%s"
                        % ("已含字符" if after.get("srcHasChar") else "**不含字符**",
                           "正确" if setup.get("caretMapsToBlock") else "**失败**",
                           "（行号取自编辑前捕获：增量重渲后新块节点不带 data--src-line）" if after.get("srcLineFromCaptured") else "")),
            "detail": {"srcLineText": after.get("srcLineText"), "srcHasChar": after.get("srcHasChar"),
                       "caretMapsToBlock": setup.get("caretMapsToBlock"),
                       "srcLineFromCaptured": after.get("srcLineFromCaptured")},
        }
    else:
        verdicts["C3"] = {"status": "untested", "reading": "用例未跑出读数", "detail": {}}
        verdicts["C4"] = {"status": "untested", "reading": "用例未跑出读数", "detail": {}}

    # C6 落点准确
    ev = _ev(raw, "sel_jump_head_mid_tail")
    rows = ev.get("rows") or []
    if rows:
        ok = all(r.get("inRangePlusMinus1") for r in rows)

        def _row(r):
            fb = r.get("firstScreenBlock") or {}
            s = "%s L=%s 首屏块=[%s,%s] %s" % (
                r["heading"], r["targetLine"], fb.get("start"), fb.get("end"),
                "✓" if r.get("inRangePlusMinus1") else "✗")
            if not r.get("inRangePlusMinus1"):
                tb = r.get("targetBlock") or {}
                if r.get("scrollClampedAtBottom") and r.get("targetVisible"):
                    s += "（文档末尾滚动钳制：目标块[%s,%s]已渲染且可见，但无法置顶）" % (tb.get("start"), tb.get("end"))
                else:
                    s += "（目标块 %s）" % ("已渲染" if tb else "未找到")
            return s
        verdicts["C6"] = {
            "status": "green" if ok else "red",
            "reading": "；".join(_row(r) for r in rows),
            "detail": {"rows": rows, "entry": ev.get("entry")},
        }
    else:
        verdicts["C6"] = {"status": "untested", "reading": "用例未跑出读数", "detail": {}}

    # C7 切模式不漂
    ev = _ev(raw, "sel_switch_mode")
    if "delta" in ev:
        d = ev.get("delta")
        ok = (d is not None and d <= 1)
        verdicts["C7"] = {
            "status": "green" if ok else "red",
            "reading": "锚点行 preview#0=%s → preview#1=%s，Δ=%s（≤1 判绿）" % (ev.get("anchor0"), ev.get("anchorFinal"), d),
            "detail": ev,
        }
    else:
        verdicts["C7"] = {"status": "untested", "reading": "用例未跑出读数", "detail": {}}

    # C9 性能预算
    ev = _ev(raw, "sel_scroll_stress")
    kts = ev.get("keyToSource")
    if kts:
        mx = kts.get("max")
        ok = (mx is not None and mx <= 16)
        verdicts["C9"] = {
            "status": "green" if ok else "red",
            "reading": ("文档 scale-5k.md（%s 行）键入 %s 字：按键→真源 median=%s ms / p95=%s ms / max=%s ms（预算 ≤16 ms）"
                        % (ev.get("docLines"), ev.get("typedChars"), kts.get("median"), kts.get("p95"), mx)),
            "detail": {"keyToSource": kts, "insertOnly": ev.get("insertOnly"),
                       "budgetMs": 16, "docLines": ev.get("docLines")},
        }
    else:
        verdicts["C9"] = {"status": "untested", "reading": "用例未跑出读数", "detail": {}}

    # 未测（如实 + 原因）
    verdicts["C1"] = {
        "status": "untested",
        "reading": "legacy 无 RenderCore「块 id」概念（`data--block-index` 是**位置下标**、随块序重编，非稳定 id）⇒ 契约 C1 在 legacy 无对应实现，无法测。",
        "detail": {},
    }
    verdicts["C5"] = {
        "status": "untested",
        "reading": "需「块编辑中（textarea 在文档内）+ 触发块级重渲」两步：双击进块编辑可用，但驱动块级重渲需要一个**未暴露的应用入口**；本次未实现 ⇒ 未测。",
        "detail": {},
    }
    verdicts["C8"] = {
        "status": "untested",
        "reading": "需断言 onLinkActivate 回调、图片双击进编辑、KP band 定位三件交互存活；回调断言需在页面侧挂测试钩子，本次未实现 ⇒ 未测。",
        "detail": {},
    }
    verdicts["C10"] = {
        "status": "untested",
        "reading": "两消费者一致需同时渲染「预览栏（可编辑）」与「对话栏气泡（只读流式）」并比对块序列；气泡渲染驱动成本高，本次未实现 ⇒ 未测。",
        "detail": {},
    }
    verdicts["C11"] = {
        "status": "untested",
        "reading": "`new` 插头尚不存在（契约 §4 双插头未施工）⇒ 无法跑 legacy vs new 等价对比。",
        "detail": {},
    }
    verdicts["C12"] = {
        "status": "untested",
        "reading": "`SurfaceRegistry.switchTo('new')` 不存在（`new` 插头未施工）⇒ 无损切换无法测。",
        "detail": {},
    }
    return verdicts


# ─────────────────────────────────────────────────────────────────────────────
# 报告
# ─────────────────────────────────────────────────────────────────────────────
C_TITLE = {
    "C1": "块 id 稳定", "C2": "文本保真", "C3": "打字当帧可见", "C4": "真源不落后",
    "C5": "冻结不破", "C6": "落点准确", "C7": "切模式不漂", "C8": "交互存活",
    "C9": "性能预算", "C10": "两消费者一致", "C11": "插头等价", "C12": "无损切换",
}
BADGE = {"green": "🟢 绿", "red": "🔴 红", "untested": "⚪ 未测"}


def build_report_json(meta, verdicts, raw):
    return {
        "schema": "surface-probe-report/1",
        "surface": "legacy",
        "label": meta["label"],
        "gitSha": meta["sha"],
        "generatedAt": meta["generated_at"],
        "contract": CONTRACT,
        "casesFile": "tests/probe-kb/cases/cases.json",
        "environment": meta["env"],
        "coverage": {
            "green": [k for k, v in verdicts.items() if v["status"] == "green"],
            "red": [k for k, v in verdicts.items() if v["status"] == "red"],
            "untested": [k for k, v in verdicts.items() if v["status"] == "untested"],
        },
        "verdicts": {k: {"title": C_TITLE[k], "status": v["status"], "reading": v["reading"],
                         "detail": v["detail"]} for k, v in sorted(verdicts.items(), key=lambda kv: int(kv[0][1:]))},
        "rawCases": {k: {"status": (v or {}).get("status"), "covers": (v or {}).get("covers"),
                         "evidence": (v or {}).get("evidence")} for k, v in (raw.get("cases") or {}).items()},
        "console": raw.get("console"),
        "notes": meta["notes"],
    }


def build_report_md(meta, verdicts, raw):
    L = []
    L.append("# 显示子系统探针报告 · legacy 契约基线\n")
    L.append("> 插头 `legacy` ｜ label `%s` ｜ git `%s` ｜ 生成 %s" % (meta["label"], meta["sha"], meta["generated_at"]))
    L.append("> 契约：[view-surface-contract.md §5](%s)" % "../../../docs/design/view-surface-contract.md")
    L.append("> 语料：`tests/probe-kb/`（cases.json + corpus + scale）\n")

    L.append("## 环境与口径\n")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    for k, v in meta["env"].items():
        L.append("| %s | %s |" % (k, v))
    L.append("")
    L.append("- **绿/红按契约判**（真源文本 + 行为契约），不按「与老实现一致」判。")
    L.append("- **性能读数绑定文档规模**：本运行 C9 用 `scale/scale-5k.md`，其真实行数见下表（**不等于**契约基准文档的 5900 行，读数须与档位一起引用）。")
    L.append("- **未测的 C 一律标「未测」并写明原因**，不默认成绿。")
    L.append("- 打字一律走 CDP `Input.dispatchKeyEvent`（受信任输入），非 `el.value=` 伪造。\n")

    L.append("## 复现\n")
    L.append("```powershell")
    L.append("node scripts\\benchmark\\surface\\cdp.mjs --selftest")
    L.append("python scripts\\benchmark\\surface\\run_probe.py --kb tests\\probe-kb --label %s" % meta["label"])
    L.append("```\n")

    L.append("## C1–C12 逐条结论\n")
    L.append("| # | 断言 | 结论 | 读数 / 原因 |")
    L.append("|---|---|---|---|")
    for i in range(1, 13):
        k = "C%d" % i
        v = verdicts.get(k, {"status": "untested", "reading": "—"})
        L.append("| %s | %s | %s | %s |" % (k, C_TITLE[k], BADGE[v["status"]], v["reading"].replace("|", "\\|")))
    L.append("")

    L.append("## 覆盖率\n")
    L.append("- 🟢 绿：%s" % ("、".join(meta["cov"]["green"]) or "（无）"))
    L.append("- 🔴 红：%s" % ("、".join(meta["cov"]["red"]) or "（无）"))
    L.append("- ⚪ 未测：%s\n" % ("、".join(meta["cov"]["untested"]) or "（无）"))

    L.append("## 关键原始读数\n")
    ev = _ev(raw, "sel_typing_ascii")
    if ev:
        L.append("### C3/C4 打字（受信任输入，同一任务内）")
        s = ev.get("setup") or {}
        a = ev.get("after") or {}
        L.append("- 目标块 blockIndex=%s，srcLine=%s，caret→块映射=%s" % (s.get("blockIndex"), s.get("srcLine"), s.get("caretMapsToBlock")))
        L.append("- 打字前 DOM：`%s`" % str((ev.get("before") or {}).get("domText"))[:80])
        L.append("- 打字后 DOM：`%s`（含 'a'=%s）" % (str(a.get("domText"))[:80], a.get("domHasChar")))
        L.append("- 打字后真源行：`%s`（含 'a'=%s）\n" % (str(a.get("srcLineText"))[:80], a.get("srcHasChar")))

    ev = _ev(raw, "sel_jump_head_mid_tail")
    if ev:
        L.append("### C6 跳转落点")
        L.append("- 入口：`%s`" % ev.get("entry"))
        for r in (ev.get("rows") or []):
            fb = r.get("firstScreenBlock") or {}
            L.append("- %s（L=%s）→ 首屏首块 [%s, %s] %s" % (r.get("heading"), r.get("targetLine"), fb.get("start"), fb.get("end"), "✓" if r.get("inRangePlusMinus1") else "✗"))
        L.append("")

    ev = _ev(raw, "sel_switch_mode")
    if ev:
        L.append("### C7 切模式锚点")
        for step in (ev.get("sequence") or []):
            L.append("- %-10s preview top=%s  source top=%s  scrollTop=%s" % (step.get("at"), step.get("previewTopSrcLine"), step.get("sourceTopSrcLine"), step.get("scrollTop")))
        L.append("")

    ev = _ev(raw, "sel_scroll_stress")
    if ev:
        kts = ev.get("keyToSource") or {}
        ins = ev.get("insertOnly") or {}
        L.append("### C9 性能（scale-5k.md，%s 行；键 %s 个）" % (ev.get("docLines"), ev.get("typedChars")))
        L.append("- 按键→真源(ms)：median=%s p95=%s max=%s min=%s n=%s" % (kts.get("median"), kts.get("p95"), kts.get("max"), kts.get("min"), kts.get("n")))
        L.append("- 仅 insertText(ms)：median=%s p95=%s max=%s" % (ins.get("median"), ins.get("p95"), ins.get("max")))
        L.append("- 页面 `[EDIT]`（>20ms 才打）日志条数：%s\n" % len((raw.get("console") or {}).get("editLogs") or []))

    L.append("## 未能做到的事（如实）\n")
    L.append("- **C1/C5/C8/C10**：见上表原因；均因 legacy 缺对应概念或驱动成本/入口缺失，未测。")
    L.append("- **C11/C12**：`new` 插头不存在 ⇒ 必然未测。")
    L.append("- **C9 只覆盖「按键→真源」这一半**：契约另一半「滚动 200 次无长任务 > 50 ms」本次未采（需 PerformanceObserver longtask 采样），故 C9 结论仅对按键预算成立。")
    L.append("- **跳转入口**：契约名义 `revealRange(L,L)`；legacy 中该函数为闭包、未导出 ⇒ 本次改调用**等价真实入口** `MemoriaApp.openFile(file,{lineHint:L})`（→ `highlightRange` → `highlightPreviewRange(scroll)`），落点语义一致。")
    L.append("- **C6 用平滑滚动**：`scrollIntoView({behavior:'smooth'})` 是异步动画，读数在 `scrollTop` 稳定后采集。")
    L.append("- **kb 副本**：`tests/probe-kb` 无 `.memoria/`，直接服务会让应用在源目录生成 sidecar/manifest ⇒ 本次将语料整树复制到 `artifacts/_probe_kb/` 由应用自行初始化，**未改动 `tests/probe-kb/**`**。")
    L.append("\n## 备注（口径；机器可读见 .json 的 `notes`）\n")
    for n in meta.get("notes", []):
        L.append("- %s" % n)
    L.append("")
    return "\n".join(L)


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="surface probe runner (legacy)")
    ap.add_argument("--kb", default="tests/probe-kb", help="源语料目录（相对 repo 根；默认 tests/probe-kb）")
    ap.add_argument("--label", default="baseline", help="报告 label（默认 baseline）")
    ap.add_argument("--port", type=int, default=8643, help="harness 端口（默认 8643）")
    ap.add_argument("--surface", default="legacy", help="插头名（默认 legacy）")
    ap.add_argument("--work-kb", default="artifacts/_probe_kb", help="临时语料副本目录（默认 artifacts/_probe_kb）")
    ap.add_argument("--timeout", type=int, default=900, help="node 子进程超时秒数")
    args = ap.parse_args()

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[probe] 源语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2

    # 复用到临时副本，避免污染 tests/probe-kb
    work_kb = (REPO_ROOT / args.work_kb).resolve()
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, work_kb)
    print("[probe] 语料副本: %s -> %s" % (src_kb, work_kb))
    had_memoria = (src_kb / ".memoria").exists()

    # harness
    harness = load_harness(work_kb, args.port)
    import bottle  # harness 已导入 bottle
    th = threading.Thread(
        target=bottle.run,
        kwargs=dict(app=harness.app, host="127.0.0.1", port=args.port, quiet=True),
        daemon=True,
    )
    th.start()
    if not wait_port(args.port):
        print("[probe] harness 未能在端口 %s 起来" % args.port, file=sys.stderr)
        return 2
    print("[probe] harness 就绪: http://127.0.0.1:%s/" % args.port)

    # node 驱动
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sha = git_short_sha()
    # 产物命名：probe-<surface>-<label>_<sha>；label 已带 surface 前缀则不重复
    label = args.label
    base = label if label.startswith(args.surface + "-") else "%s-%s" % (args.surface, label)
    stem = "probe-%s_%s" % (base, sha)
    raw_path = RESULTS_DIR / ("raw-%s.json" % stem)
    cases_path = REPO_ROOT / "tests" / "probe-kb" / "cases" / "cases.json"

    cmd = [
        "node", str(CDP_MJS), "--probe",
        "--url", "http://127.0.0.1:%d/" % args.port,
        "--kb-root", str(work_kb),
        "--cases", str(cases_path),
        "--out", str(raw_path),
    ]
    print("[probe] 运行: %s" % " ".join(cmd))
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[probe] node 驱动超时", file=sys.stderr)
        return 3
    dur = time.time() - t0
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0 or not raw_path.exists():
        print("[probe] node 驱动失败（code=%s）" % proc.returncode, file=sys.stderr)
        print("--- stdout ---\n%s\n--- stderr ---\n%s" % (out[-4000:], err[-8000:]), file=sys.stderr)
        return 3
    print("[probe] node 驱动完成（%.1fs）" % dur)

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    verdicts = judge(raw)

    env = {
        "browser": raw.get("browser"),
        "edge": raw.get("edgePath"),
        "node": node_version(),
        "kbServed": str(work_kb),
        "kbSource": str(src_kb),
        "kbSourceHasMemoria": ("是" if had_memoria else "否（已用副本让应用自初始化）"),
        "casesFile": "tests/probe-kb/cases/cases.json",
        "scaleDoc": "tests/probe-kb/scale/scale-5k.md",
        "scaleDocLines": (_ev(raw, "sel_scroll_stress") or {}).get("docLines"),
        "appReady": raw.get("appReady"),
        "runDurationMs": raw.get("durationMs"),
    }
    notes = [
        "绿/红按契约判，不按与老实现一致判。",
        "未测项已写明原因，未默认成绿。",
        "C9 只覆盖「按键→真源」半条；滚动长任务半条未采。",
        "C9 读数有运行间波动（同机同档多次实测落在 budget 之上；引用须连同档位/运行环境一起）。",
        "跳转入口用等价真实入口 openFile(file,{lineHint}) 代替闭包 revealRange。",
        "语料在 artifacts/_probe_kb 副本上运行，tests/probe-kb 未被改动。",
        "观察项（非本次断言）：增量重渲（reRenderBlock→renderRange 换节点 + keepLineMap 跳过 stamp）后，被编辑块节点**瞬时不带** data--src-line，可能影响按该属性定位的入口。",
    ]
    meta = {
        "label": args.label, "sha": sha,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "env": env, "notes": notes,
        "cov": {
            "green": [k for k, v in verdicts.items() if v["status"] == "green"],
            "red": [k for k, v in verdicts.items() if v["status"] == "red"],
            "untested": [k for k, v in verdicts.items() if v["status"] == "untested"],
        },
    }

    rep_json = build_report_json(meta, verdicts, raw)
    rep_md = build_report_md(meta, verdicts, raw)
    jpath = RESULTS_DIR / (stem + ".json")
    mpath = RESULTS_DIR / (stem + ".md")
    jpath.write_text(json.dumps(rep_json, ensure_ascii=False, indent=2), encoding="utf-8")
    mpath.write_text(rep_md, encoding="utf-8")

    print("\n[probe] ===== 结论摘要 =====")
    for i in range(1, 13):
        k = "C%d" % i
        v = verdicts[k]
        print("  %-4s %-8s %s" % (k, BADGE[v["status"]], v["reading"][:110]))
    print("\n[probe] 产物：\n  %s\n  %s\n  raw: %s" % (jpath, mpath, raw_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
