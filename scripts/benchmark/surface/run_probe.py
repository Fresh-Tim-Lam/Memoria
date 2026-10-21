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
# 性能度量口径契约（C9 的 warmup/逐键/多轮/离散度/判据）
MEASUREMENT_PROTOCOL = "docs/design/benchmark-measurement-protocol.md"

# C9 默认参数。**必须与 cdp.mjs 的 C9_DEFAULTS 逐字一致**（协议 §9）。
C9_DEFAULTS = {
    "warmupKeys": 5,
    "rounds": 5,
    "keysPerRound": 10,
    "settleTimeoutMs": 1500,
}
C9_NOISE_DEFAULTS = {
    "maxIqrOverMedian": 0.25,
    "maxP95OverMedian": 1.60,
    "maxRoundSpread": 0.20,
    "minLiveKeys": 20,
}
C9_BUDGET_MS = 16.0


# ─────────────────────────────────────────────────────────────────────────────
# git / 环境
# ─────────────────────────────────────────────────────────────────────────────
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


def _fmt(v, nd=1, unit=" ms"):
    if v is None:
        return "—"
    try:
        return ("%." + str(nd) + "f") % float(v) + unit
    except (TypeError, ValueError):
        return str(v)


def judge_c9(ev: dict) -> dict:
    """C9 判定：**先噪声、后预算**（协议 §6）。

    返回的 status ∈ {green, red, untested}；其中「测量无效」不新增 status 值，
    而是以 status="untested" + conclude=false 表达 —— 这样 C1–C12 的三态词汇
    （绿/红/未测）**不被破坏**，同时报告里明确写「不确定」。
    """
    if not ev:
        return {"status": "untested", "conclude": False,
                "reading": "用例未跑出读数", "detail": {}}

    measurement = ev.get("measurement")
    verdict = ev.get("verdict") or {}

    # ── v1 旧证据：一次性连发 30 键的批量口径 ⇒ 按契约**不可判**，绝不回退到 max<=16 ──
    if not measurement:
        kts = ev.get("keyToSource") or {}
        legacy = ""
        if kts:
            legacy = ("（该 raw 为 v1 批量口径：median %s / p95 %s / max %s，n=%s —— 一次性连发 30 键，"
                      "测的是批量排队时延，**不可判**绿/红）"
                      % (_fmt(kts.get("median")), _fmt(kts.get("p95")), _fmt(kts.get("max")), kts.get("n")))
        return {
            "status": "untested", "conclude": False,
            "reading": ("**不确定（v1 批量口径，不可判）**：该 raw 缺逐键多轮度量，按协议 §10 不判绿/红。" + legacy +
                        "需用 v2 探针重测（见 %s）。" % MEASUREMENT_PROTOCOL),
            "detail": {"reason": "v1-legacy-batch-evidence", "legacyKeyToSource": kts or None,
                       "protocol": MEASUREMENT_PROTOCOL},
        }

    cfg = measurement.get("config") or {}
    prim = measurement.get("primary") or {}
    pk = prim.get("perKey") or {}
    pr = prim.get("rounds") or {}
    ctrl = measurement.get("control") or {}
    cnt = measurement.get("counts") or {}
    clean = measurement.get("cleanKeys") or {}
    lower_bound = clean.get("median")          # 干净键 median = 单键成本**下界**（真值，协议 §6.6）
    noise = verdict.get("noise") or {}
    th = noise.get("thresholds") or C9_NOISE_DEFAULTS
    obs = noise.get("observed") or {}
    decision = verdict.get("decision")
    reasons = verdict.get("reasons") or []

    header = "文档 scale-5k.md（%s 行）逐键采样：n=%s（R=%s × %s 键）× warmup %s" % (
        ev.get("docLines"), pk.get("n"), pr.get("R"), cfg.get("keysPerRound"), cnt.get("warmup"))
    stats = "min %s / median %s / p95 %s / max %s；IQR %s，IQR/median %s，p95/median %s，轮间极差 %s" % (
        _fmt(pk.get("min")), _fmt(pk.get("median")), _fmt(pk.get("p95")), _fmt(pk.get("max")),
        _fmt(pk.get("iqr"), 2), _fmt(pk.get("iqrOverMedian"), 3, ""),
        _fmt(pk.get("p95OverMedian"), 3, ""), _fmt(pr.get("spread"), 3, ""))
    budget_ms = verdict.get("budgetMs", C9_BUDGET_MS)
    # 判定由分位数**现场重判**（不照抄 raw 的 withinBudget）：这样 python 侧是"独立复核"而非"复述"。
    med = pr.get("median")
    within_budget = (med is not None and float(med) <= float(budget_ms))
    budget = "预算 ≤%s ⇒ median-of-medians %s ⇒ %s" % (
        _fmt(budget_ms, 0), _fmt(med), "在预算内" if within_budget else "**超预算**")
    ctrltxt = ""
    if ctrl.get("perKeyMin") is not None:
        ctrltxt = "；对照口径 fromKeyMs 的键内最小值 %s（仅参考，**不作判据**）" % _fmt(ctrl.get("perKeyMin"))
    if lower_bound is not None and clean.get("n"):
        ctrltxt += "；干净键 %s 个给出**下界** %s（真值，§6.6）" % (clean.get("n"), _fmt(lower_bound))

    base_detail = {
        "decision": decision,
        "conclude": decision in ("green", "red"),
        "budgetMs": budget_ms,
        "medianOfMedians": med,
        "withinBudget": within_budget,
        "lowerBoundMs": lower_bound,
        "cleanKeys": {"n": clean.get("n"), "median": clean.get("median"), "keys": clean.get("keys")},
        "crossCheck": verdict.get("crossCheck"),
        "rawDecision": decision,
        "rawMedianOfMedians": verdict.get("medianOfMedians"),
        "primary": {"metric": prim.get("metric"), "perKey": pk, "rounds": pr},
        "control": {"metric": ctrl.get("metric"), "perKey": ctrl.get("perKey"), "perKeyMin": ctrl.get("perKeyMin")},
        "config": cfg, "counts": cnt,
        "noise": {"thresholds": th, "observed": obs},
        "reasons": reasons,
        "docLines": ev.get("docLines"),
        "protocol": MEASUREMENT_PROTOCOL,
        "reproduce": ("node scripts/benchmark/surface/cdp.mjs --probe … --c9-warmup %s --c9-rounds %s --c9-keys %s"
                      % (cfg.get("warmupKeys"), cfg.get("rounds"), cfg.get("keysPerRound"))),
    }

    if decision == "gray":
        return {
            "status": "untested", "conclude": False,
            "reading": ("**不确定（inconclusive）—— 本次度量无效，不作绿/红**。%s；%s；%s。噪声门未过：%s。"
                        "处置：同机同档位重测。" % (header, stats, budget, "；".join(reasons))),
            "detail": dict(base_detail, inconclusive=True),
        }
    if decision == "red":
        return {
            "status": "red", "conclude": True,
            "reading": ("%s；%s；%s。噪声门通过（%s）%s。"
                        % (header, stats, budget, "；".join(reasons), ctrltxt)),
            "detail": base_detail,
        }
    return {
        "status": "green", "conclude": True,
        "reading": ("%s；%s；%s。噪声门通过（%s）%s。"
                    % (header, stats, budget, "；".join(reasons), ctrltxt)),
        "detail": base_detail,
    }


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

    # ── C9 性能预算 ────────────────────────────────────────────────────────
    #
    # 口径契约：docs/design/benchmark-measurement-protocol.md
    #   旧判据 `max <= 16` 已废止（顺序错误：max 对一次 GC 即红；且与契约 §3.3 的
    #   「median ≤ 16」不是同一个统计量）。新判据：
    #     ① 先过噪声门（键间 IQR/median、p95/median、轮间相对极差、样本量、死键）
    #     ② 再判 median-of-medians ≤ budget
    #     ③ 任一步不过 ⇒ inconclusive（度量状态，不得表述为通过/失败）
    verdicts["C9"] = judge_c9(_ev(raw, "sel_scroll_stress"))

    # ── C1 块身份稳定（2026-10-20 由 metrics-baseline 补实测）──────────────────
    # 契约 C1：编辑一块 ⇒ **被编辑块自身 id 可变**，但**其余块 id 必须完全不变**，块总数不变。
    # 以前是 untested 的真实原因：legacy 的 `data--block-index` 是位置下标而非稳定身份；
    # P2 把 BlockIndex.upsert() 接上、真实写 `data-block-id` 之后才可测。
    # 判据（三态）：无违例 + 块数不变 + **确实存在可测身份** ⇒ 绿；否则红。
    #   ⚠️ `noIdentity`（全块缺 data-block-id，即旧实现）必须判**红**，不能算绿 ——
    #   否则本用例会"假通过"（旧实现根本没有该属性，测不到东西）。
    c1ev = _ev(raw, "sel_id_stability")
    if c1ev and (c1ev.get("subcases") is not None):
        subs = c1ev.get("subcases") or []
        ran = [s for s in subs if s.get("status") == "ran"]
        bad = [s for s in ran if not s.get("ok")]
        noid = [s for s in ran if s.get("noIdentity")]
        # 防假通过：编辑没真正生效的子例不能算绿（否则"id 全没变"会被误读成"其余块不变"）
        notapplied = [s for s in ran if not s.get("editApplied")]
        if not ran:
            verdicts["C1"] = {"status": "untested", "reading": "C1 用例未跑出读数（subcases 全为空/出错）", "detail": c1ev}
        elif noid:
            verdicts["C1"] = {
                "status": "red",
                "reading": "**块无身份**：%s 例中所有块都缺 `data-block-id`（实现未落地稳定块 id）⇒ 契约 C1 不成立。" % len(noid),
                "detail": c1ev,
            }
        elif notapplied:
            verdicts["C1"] = {
                "status": "red",
                "reading": "**编辑未生效**（%s）：按键没有改动目标块文本 ⇒ 本用例无可判性，不能判绿（防假通过）。"
                           % "、".join(s.get("name") for s in notapplied),
                "detail": c1ev,
            }
        elif bad:
            parts = []
            for s in bad:
                vs = s.get("violations") or []
                desc = "、".join(
                    ("块数 %s→%s" % ((v.get("before"), v.get("after")))) if v.get("kind") == "blockCount"
                    else ("#%s id %s→%s" % (v.get("i"), v.get("before"), v.get("after")))
                    for v in vs[:3])
                parts.append("%s（编辑 #%s）: %s" % (s.get("name"), s.get("editIdx"), desc or "未通过"))
            verdicts["C1"] = {
                "status": "red",
                "reading": "**其余块 id 被牵连** ⇒ " + "；".join(parts),
                "detail": c1ev,
            }
        else:
            names = "、".join(s.get("name") for s in ran)
            total = (ran[0].get("blockCount") or {}).get("before")
            allowed = sum(len(s.get("allowedChange") or []) for s in ran)
            verdicts["C1"] = {
                "status": "green",
                "reading": "%d 例（%s）全部：被编辑块 id 可变（允许变化 %d 次）、**其余块 id 全部不变**、块数保持 %s。"
                           % (len(ran), names, allowed, total),
                "detail": c1ev,
            }
    elif c1ev and c1ev.get("status") == "error":
        verdicts["C1"] = {"status": "red", "reading": "C1 用例执行出错：%s" % c1ev.get("error"), "detail": c1ev}
    else:
        verdicts["C1"] = {
            "status": "untested",
            "reading": "C1 用例未跑出读数（`sel_id_stability` 无 evidence）",
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
    # ── C11 / C12：双插头（阶段 2 P1，2026-10-20）────────────────────────────
    #   数据来自 cdp.mjs 的 `runSurfaceSwitchProbe` 用例（含"自证会红"的合成插头结果）。
    #   铁律：**不得假绿**。`new` 未实现 ⇒ C11 = inconclusive（不是绿）；
    #         且只有当合成 `__broken` 确实判红时，C11 的机制才算被证明有效。
    _sw = _ev(raw, "c11_c12_surface_switch")

    def _probe_red_ok(key: str) -> bool:
        sp = (_sw.get("selfProof") or {})
        return sp.get(key) is True

    # C12：无损切换（legacy 往返后 6 项状态全等）+ 自证会红（__lossy 必须检出差异）
    if _sw.get("status") == "error" or not _sw:
        verdicts["C12"] = {
            "status": "untested", "conclude": False,
            "reading": "双插头探针未跑出读数 ⇒ 无法判。",
            "detail": {"error": (_sw or {}).get("error")},
        }
    else:
        _c12 = _sw.get("c12") or {}
        _lossy_red = _probe_red_ok("c12_lossy_red")
        _c12_green = _c12.get("status") == "green"
        if not _lossy_red:
            # 自证失败：合成丢状态插头都没能判红 ⇒ 这个探针没有鉴别力，不能出绿
            verdicts["C12"] = {
                "status": "untested", "conclude": False,
                "reading": ("**探针无鉴别力**：合成丢状态插头 `__lossy` 未被检出差异 ⇒ 即使 legacy 往返"
                            "看起来一致，也不能据此判绿（否则就是假绿）。"),
                "detail": {"c12": _c12, "selfProof": _sw.get("selfProof")},
            }
        else:
            verdicts["C12"] = {
                "status": "green" if _c12_green else "red",
                "reading": (("legacy 往返后 6 项状态（state.doc / currentPath / viewMode / 滚动 / 选区 / KP band）"
                             "逐项一致；且合成丢状态插头 `__lossy` 被正确判红 ⇒ 探针有鉴别力。")
                            if _c12_green else
                            ("legacy 往返后状态**不一致**，差异：" + str(_c12.get("diff")))),
                "detail": {"c12": _c12, "selfProof": _sw.get("selfProof")},
            }

    # C11：新旧等价。
    #   ⚠️ 口径（Lead 裁决 2026-10-20）：`new` 未实现 ⇒ **inconclusive，不是绿、也不是红**。
    #   `__broken` 的红只用来证明"探针有鉴别力"，**不能**当作 C11 的结论（它是合成坏插头，不是 new）。
    _self = (_sw.get("selfProof") or {})
    _broken_red = _self.get("c11_broken_red") is True
    if _sw.get("status") == "error" or not _sw:
        verdicts["C11"] = {
            "status": "untested", "conclude": False,
            "reading": "双插头探针未跑出读数 ⇒ 无法判。",
            "detail": {"error": (_sw or {}).get("error")},
        }
    else:
        _list = _sw.get("list") or []
        _has_new = "new" in _list
        _branch = "new 已注册（占位，方法抛 NotImplemented）" if _has_new else "new 未注册"
        _mech = ("合成坏插头 `__broken`（块数少 2）被正确判红 ⇒ 探针机制有鉴别力。" if _broken_red
                 else "**合成坏插头 `__broken` 未被检出 ⇒ 探针无鉴别力，结论不可信。**")
        # 口径（Lead 裁决 2026-10-20）：`new` 未实现 ⇒ **不确定（inconclusive），不是绿、也不是红**。
        # 遵守本文件既有约定（C9 同此）：**不新增 status 值**（三态词汇绿/红/未测不被破坏），
        # 用 status="untested" + inconclusive=True + conclude=False 表达「有结论但不可判」。
        verdicts["C11"] = {
            "status": "untested", "conclude": False, "inconclusive": True,
            "reading": ("**不确定（inconclusive）—— 不作绿/红。** %s ⇒ 新旧等价对比**尚不可判**；%s"
                        "（机制自证不等于 new 等价通过。）" % (_branch, _mech)),
            "detail": {
                "list": _list, "branches": ["__broken", "__lossy"],
                "selfProof": _self,
                "c11_mechanism_verified": _broken_red,
                "note": "`__broken` 的红是**合成插头**的结果，仅证明探针有鉴别力；"
                        "`new` 真实等价性需等 NewSurface 实现后再判。",
            },
        }

    # C10：双消费者一致（预览栏 vs agent 气泡）—— 需真实流式数据 ⇒ 仍未测（如实）
    verdicts["C10"] = {
        "status": "untested",
        "reading": "两消费者一致需同时渲染「预览栏（可编辑）」与「对话栏气泡（只读流式）」并比对块序列；气泡渲染驱动成本高，本次未实现 ⇒ 未测。",
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
        L.append("### C9 性能（协议 v%s：逐键 / warmup / 多轮）" % ((raw.get("measurementProtocol") or {}).get("version", "?")))
        m = ev.get("measurement") or {}
        if m:
            cfg = m.get("config") or {}
            pk = (m.get("primary") or {}).get("perKey") or {}
            pr = (m.get("primary") or {}).get("rounds") or {}
            ck = (m.get("control") or {}).get("perKey") or {}
            cnt = m.get("counts") or {}
            v = ev.get("verdict") or {}
            L.append("- **采集参数**：R=%s 轮 × %s 键，warmup=%s（丢弃），单键落定超时 %s ms；输入通道 `%s`"
                     % (cfg.get("rounds"), cfg.get("keysPerRound"), cfg.get("warmupKeys"),
                        cfg.get("settleTimeoutMs"), cfg.get("inputChannel")))
            L.append("- **样本**：正式 n=%s，落定 %s，死键 %s，落定超时 %s"
                     % (cnt.get("live"), cnt.get("settledKeys"), cnt.get("deadKeys"), cnt.get("settleTimeouts")))
            L.append("- **主口径 `appendMs`（按键→真源落定，逐键百分位估计）**："
                     "min %s / median %s / p95 %s / max %s"
                     % (_fmt(pk.get("min")), _fmt(pk.get("median")), _fmt(pk.get("p95")), _fmt(pk.get("max"))))
            L.append("- **离散度**：IQR %s ｜ IQR/median %s ｜ p95/median %s ｜ 轮间相对极差 %s"
                     % (_fmt(pk.get("iqr"), 2), _fmt(pk.get("iqrOverMedian"), 3, ""),
                        _fmt(pk.get("p95OverMedian"), 3, ""), _fmt(pr.get("spread"), 3, "")))
            L.append("- **每轮 median**：%s ⇒ **median-of-medians %s**（预算 ≤%s）"
                     % (" / ".join(_fmt(x) for x in (pr.get("perRoundMedian") or [])) or "—",
                        _fmt(pr.get("median")), _fmt(v.get("budgetMs", C9_BUDGET_MS), 0)))
            L.append("- **对照口径**（不作判据）：`fromKeyMs` median %s ｜ **干净键** %s 个 ⇒ 单键成本**下界** %s（真值）｜ 键内最小值 %s"
                     % (_fmt(ck.get("median")), (m.get("cleanKeys") or {}).get("n", 0),
                        _fmt((m.get("cleanKeys") or {}).get("median")), _fmt((m.get("control") or {}).get("perKeyMin"))))
            cc = v.get("crossCheck")
            if cc:
                L.append("- 口径对账（§6.6 自校验）：cleanMedian %s / appendMedian %s = **%s**（期望 ≈1.429）"
                         % (_fmt(cc.get("cleanMedianMs")), _fmt(cc.get("appendMedianMs")), cc.get("ratio")))
            L.append("- **结论**：`%s` %s —— %s"
                     % (v.get("decision"), ("（%s）" % "；".join(v.get("reasons") or [])) if v.get("reasons") else "",
                        {"green": "达标", "red": "超标", "gray": "**不确定**：噪声超过阈值，本次读数**不作**绿/红，需重测"}.get(v.get("decision"), "—")))
            L.append("- 口径契约：[benchmark-measurement-protocol.md](../../../docs/design/benchmark-measurement-protocol.md)\n")
        else:
            kts = ev.get("keyToSource") or {}
            L.append("- ⚠️ **该 raw 为 v1 批量口径**（一次性连发 30 键，无 warmup/多轮）："
                     "median %s / p95 %s / max %s / n=%s —— 按协议 §10 **不可判**，需用 v2 探针重测。"
                     % (_fmt(kts.get("median")), _fmt(kts.get("p95")), _fmt(kts.get("max")), kts.get("n")))
            L.append("- 口径契约：[benchmark-measurement-protocol.md](../../../docs/design/benchmark-measurement-protocol.md)\n")
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
    # ── C9 度量协议参数（协议 §9；默认值必须与 cdp.mjs C9_DEFAULTS 一致）──
    g = ap.add_argument_group("C9 度量协议参数（docs/design/benchmark-measurement-protocol.md §9）")
    g.add_argument("--c9-warmup", type=int, default=C9_DEFAULTS["warmupKeys"], help="预热键数（丢弃，默认 5）")
    g.add_argument("--c9-rounds", type=int, default=C9_DEFAULTS["rounds"], help="轮数 R（默认 5）")
    g.add_argument("--c9-keys", type=int, default=C9_DEFAULTS["keysPerRound"], help="每轮键数（默认 10）")
    g.add_argument("--c9-settle-timeout", type=int, default=C9_DEFAULTS["settleTimeoutMs"], help="单键落定超时 ms（默认 1500）")
    g.add_argument("--c9-max-iqr-over-median", type=float, default=C9_NOISE_DEFAULTS["maxIqrOverMedian"], help="键间 IQR/median 上限（默认 0.25）")
    g.add_argument("--c9-max-p95-over-median", type=float, default=C9_NOISE_DEFAULTS["maxP95OverMedian"], help="键间 p95/median 上限（默认 1.60）")
    g.add_argument("--c9-max-round-spread", type=float, default=C9_NOISE_DEFAULTS["maxRoundSpread"], help="轮间相对极差上限（默认 0.20）")
    g.add_argument("--c9-min-keys", type=int, default=C9_NOISE_DEFAULTS["minLiveKeys"], help="最少正式键数（默认 20）")
    # ── 配置隔离（task-54）：默认密封，不继承开发机 config/ui-settings.json ──
    #   事故背景：ambient 的 search.embedding_enabled=true 会让搜索在单线程 harness 内
    #   同步构建 embedding 索引（阻塞 >45s），导致假红；同类泄漏也可能污染冻结基线。
    _iso_mod = _load_iso_config()
    _iso_mod.add_isolation_arg(ap)
    args = ap.parse_args()
    # ── 应用配置隔离（task-54）：默认密封；--ambient-config 仅诊断 ──
    _iso = _iso_mod.isolate_config(
        script=__file__.rsplit(os.sep, 1)[-1].rsplit('.', 1)[0],
        label=getattr(args, 'label', 'run'),
        ambient=getattr(args, 'ambient_config', False),
    )
    print(_iso.describe())
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

    c9_args = [
        "--c9-warmup", str(args.c9_warmup),
        "--c9-rounds", str(args.c9_rounds),
        "--c9-keys", str(args.c9_keys),
        "--c9-settle-timeout", str(args.c9_settle_timeout),
        "--c9-max-iqr-over-median", str(args.c9_max_iqr_over_median),
        "--c9-max-p95-over-median", str(args.c9_max_p95_over_median),
        "--c9-max-round-spread", str(args.c9_max_round_spread),
        "--c9-min-keys", str(args.c9_min_keys),
    ]
    cmd = [
        "node", str(CDP_MJS), "--probe",
        "--url", "http://127.0.0.1:%d/" % args.port,
        "--kb-root", str(work_kb),
        "--cases", str(cases_path),
        "--out", str(raw_path),
    ] + c9_args
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

    # 协议一致性：raw 实际生效的 C9 参数应等于命令行参数（不一致 ⇒ 以 raw 为准，但要说出来）
    effective_c9 = ((raw.get("measurementProtocol") or {}).get("c9")) or {}
    c9_inconsistent = []
    for k in ("warmupKeys", "rounds", "keysPerRound", "settleTimeoutMs"):
        if k in effective_c9 and effective_c9[k] != getattr(args, {
                "warmupKeys": "c9_warmup", "rounds": "c9_rounds",
                "keysPerRound": "c9_keys", "settleTimeoutMs": "c9_settle_timeout"}[k]):
            c9_inconsistent.append("%s: cli=%s raw=%s" % (k, getattr(args, {
                "warmupKeys": "c9_warmup", "rounds": "c9_rounds",
                "keysPerRound": "c9_keys", "settleTimeoutMs": "c9_settle_timeout"}[k]), effective_c9[k]))
    if c9_inconsistent:
        print("[probe] 警告：C9 参数与 raw 不一致（以 raw 为准）：%s" % "; ".join(c9_inconsistent), file=sys.stderr)

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
        "c9Protocol": "v%s / %s" % ((raw.get("measurementProtocol") or {}).get("version", "?"), MEASUREMENT_PROTOCOL),
        "c9Params": "warmup=%s, R=%s, keysPerRound=%s, settleTimeout=%sms" % (
            args.c9_warmup, args.c9_rounds, args.c9_keys, args.c9_settle_timeout),
        "c9NoiseThresholds": "IQR/median<=%s, p95/median<=%s, roundSpread<=%s, minKeys>=%s" % (
            args.c9_max_iqr_over_median, args.c9_max_p95_over_median,
            args.c9_max_round_spread, args.c9_min_keys),
        "appReady": raw.get("appReady"),
        "runDurationMs": raw.get("durationMs"),
    }
    notes = [
        "绿/红按契约判，不按与老实现一致判。",
        "未测项已写明原因，未默认成绿。",
        "C9 只覆盖「按键→真源」半条；滚动长任务半条未采。",
        "C9 口径 v2：逐键采样（非一次性连发）+ warmup 丢弃 + R 轮 median-of-medians；"
        "判绿/红前先过噪声门（键间 IQR/p95、轮间极差、样本量、死键），不过则标「不确定」而非绿/红。",
        "C9 的「不确定」是**度量状态**而非性能结论：不得据此说达标或退化；处置 = 同机同档位重测。",
        "跳转入口用等价真实入口 openFile(file,{lineHint}) 代替闭包 revealRange。",
        "语料在 artifacts/_probe_kb 副本上运行，tests/probe-kb 未被改动。",
        "观察项（非本次断言）：增量重渲（reRenderBlock→renderRange 换节点 + keepLineMap 跳过 stamp）后，被编辑块节点**瞬时不带** data--src-line，可能影响按该属性定位的入口。",
    ]
    if c9_inconsistent:
        notes.append("C9 参数与 raw 不一致（以 raw 为准）：%s" % "; ".join(c9_inconsistent))
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
        tag = BADGE[v["status"]]
        if v.get("conclude") is False and k == "C9":
            tag = "⚪ 不确定"      # 度量无效：既不是绿也不是红（协议 §6.3 / R5）
        print("  %-4s %-8s %s" % (k, tag, v["reading"][:150]))
    print("\n[probe] 产物：\n  %s\n  %s\n  raw: %s" % (jpath, mpath, raw_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
