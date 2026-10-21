"""KB 守卫接线助手 —— 供 8 个真机脚本统一调用（task-57 · L6）。

════════════════════════════════════════════════════════════════════════════
设计要点（避免 task-55 踩过的两个坑）
════════════════════════════════════════════════════════════════════════════
① **冻结语料 ≠ 测量 KB**
   坑：`FROZEN_KB_DIR = MEMORIA_KB`，而运行时 `MEMORIA_KB` 指向副本
       ⇒ 守卫盯着副本 ⇒ 副本被写 ⇒ **假红**（"内红外绿"）。
   解：冻结语料一律取自独立变量 **`P5PERF_FROZEN_KB`**（默认 `artifacts/_p5_matrix_kb`），
       与脚本实际使用的 `MEMORIA_KB` **彻底分离**。

② **前快照文件名必须唯一**
   坑：固定名被上一轮 run 覆盖 ⇒ 本轮"前快照"实为旧状态 ⇒ 假红。
   解：快照写到 `tempfile.mkdtemp()` 下，天然唯一。

════════════════════════════════════════════════════════════════════════════
两种用法
════════════════════════════════════════════════════════════════════════════
只读脚本（不写 KB）：
    from _kb_guard_wire import begin_guard, end_guard
    g = begin_guard("run_fidelity", label=args.label)
    ...
    end_guard(g)                    # 不一致 ⇒ 抛异常（进程非 0）

可能写 KB 的脚本（save / 编辑 / 粘贴 / 结构编辑）：
    from _kb_guard_wire import begin_guard, make_measure_kb, end_guard
    g = begin_guard("run_domwrites", label=args.label, writable=True)
    work = make_measure_kb(g)       # 副本；打印路径
    os.environ["MEMORIA_KB"] = str(work)    # 测量跑在副本上
    ...
    end_guard(g)                    # 校验的是**冻结语料**（应始终绿）

PowerShell 见 `_kb_guard_wire.ps1`。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_SURFACE = Path(__file__).resolve().parent
if str(_SURFACE) not in sys.path:
    sys.path.insert(0, str(_SURFACE))

from _kb_guard import FROZEN_DOCS, KbGuard, make_work_copy, snapshot  # noqa: E402

#: 冻结语料目录的**独立**环境变量（与 MEMORIA_KB 分离，见模块 docstring ①）
FROZEN_KB_ENV = "P5PERF_FROZEN_KB"
DEFAULT_FROZEN_KB = "artifacts/_p5_matrix_kb"


def frozen_kb_dir() -> Path:
    """解析冻结语料目录（只用 `P5PERF_FROZEN_KB`，**绝不**回退到 `MEMORIA_KB`）。"""
    raw = os.environ.get(FROZEN_KB_ENV) or DEFAULT_FROZEN_KB
    p = Path(raw)
    if not p.is_absolute():
        # 相对路径按仓库根解析（本文件在 scripts/benchmark/surface/）
        p = _SURFACE.parents[2] / p
    return p.resolve()


class GuardHandle:
    """一次 run 的守卫句柄。"""

    def __init__(self, script: str, label: str, writable: bool) -> None:
        self.script = script
        self.label = label
        self.writable = writable
        self.kb_dir = frozen_kb_dir()
        self.snap_dir = Path(tempfile.mkdtemp(prefix=f"_kbguard_{script}_"))
        self.before_path = self.snap_dir / "before.json"
        self.work_kb: Path | None = None
        self._guard: KbGuard | None = None

    # ── 状态输出 ──────────────────────────────────────────────────────────
    def describe(self) -> str:
        mode = "写类（测量跑副本）" if self.writable else "只读"
        return (f"[kb-guard] 冻结语料: {self.kb_dir}\n"
                f"[kb-guard] 模式: {mode}  快照目录: {self.snap_dir}")

    def manifest(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "script": self.script,
            "label": self.label,
            "writable": self.writable,
            "frozenKb": str(self.kb_dir),
            "frozenKbEnv": FROZEN_KB_ENV,
            "beforeSnapshot": str(self.before_path),
            "workKb": str(self.work_kb) if self.work_kb else None,
        }


def begin_guard(script: str, label: str = "run", *, writable: bool = False) -> GuardHandle:
    """建立前快照。冻结语料缺失 ⇒ 直接报错（拒绝在无守卫下运行）。"""
    h = GuardHandle(script, label, writable)
    if not h.kb_dir.is_dir():
        raise SystemExit(
            f"[kb-guard] ❌ 冻结语料目录不存在: {h.kb_dir}\n"
            f"           环境变量 {FROZEN_KB_ENV} 或默认 {DEFAULT_FROZEN_KB}\n"
            f"           拒绝在无守卫下运行测量。"
        )
    g = KbGuard(h.kb_dir)
    snap = g.snapshot_before()
    missing = [r for r, v in snap.items() if not v.get("exists")]
    if missing:
        raise SystemExit(f"[kb-guard] ❌ 冻结语料缺文档: {missing}")
    h.before_path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    h._guard = g
    print(h.describe(), flush=True)
    return h


def make_measure_kb(h: GuardHandle, *, label: str | None = None) -> Path:
    """为**写类**脚本创建副本；返回副本路径（并设 `MEMORIA_KB` 指向它）。"""
    if not h.writable:
        raise RuntimeError("只读脚本不应调用 make_measure_kb()")
    if h.work_kb is None:
        h.work_kb = make_work_copy(h.kb_dir, label=label or f"{h.script}_{h.label}")
        os.environ["MEMORIA_KB"] = str(h.work_kb)
        print(f"[kb-guard] 测量副本 KB: {h.work_kb}（冻结语料只读，写操作全在副本上）", flush=True)
    return h.work_kb


def end_guard(h: GuardHandle, *, strict: bool = True) -> dict[str, Any]:
    """后校验**冻结语料**。不一致 ⇒ 判红点名（strict 时抛异常使进程非 0）。"""
    if h._guard is None:
        raise RuntimeError("end_guard() 前必须先 begin_guard()")
    r = h._guard.verify()
    r["guard"] = h.manifest()
    out = h.snap_dir / "result.json"
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    if r["ok"]:
        print(f"[kb-guard] ✅ 冻结语料未变（{r['documents']} 篇）  结果: {out}", flush=True)
    else:
        names = ", ".join(c["file"] for c in r["changed"]) or ", ".join(r["missing"])
        print(f"[kb-guard] ❌ **红** —— 冻结语料被写入/删除: {names}", file=sys.stderr, flush=True)
        for c in r["changed"]:
            print(f"   - {c['file']}\n     before={c['before']}\n     after ={c['after']}",
                  file=sys.stderr, flush=True)
        print(f"[kb-guard] 这是**测试缺陷**：写类测试必须在副本上跑。结果: {out}",
              file=sys.stderr, flush=True)
        if strict:
            raise SystemExit(1)
    return r


__all__ = [
    "FROZEN_KB_ENV", "DEFAULT_FROZEN_KB", "frozen_kb_dir",
    "GuardHandle", "begin_guard", "make_measure_kb", "end_guard",
    "FROZEN_DOCS", "snapshot",
]
