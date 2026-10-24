#!/usr/bin/env python3
"""task-69 P1 出口断言：全库 validate 异步入口 + 合并重复提交。

覆盖：
  1. 默认行为不变：replace 仅顶替「排队中」作业；执行中的作业不被合并
  2. coalesce_running=True：排队中 / 执行中的同 kind+key 作业被复用（同一 job_id，只执行一次）
  3. 不同 key 不合并（多库互不干扰）
  4. 真实 validate：两次并发提交 -> 同一作业；结果与同步调用一致（errors/files_checked）

用法：.venv\\Scripts\\python.exe scripts\\benchmark\\maintenance\\executor_coalesce_assert.py
退出码 0=全 PASS，1=有 FAIL。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from memoria.services.executor import MaintenanceExecutor  # noqa: E402

fails: list[str] = []

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def check(name: str, cond: bool, extra=None) -> None:
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {extra}" if extra is not None else ""))
    if not cond:
        fails.append(name)


def test_default_semantics_unchanged() -> None:
    ex = MaintenanceExecutor(max_workers=1, keep=8)
    ex.submit("block", lambda: time.sleep(0.5), key="b")  # 占住唯一 worker
    a = ex.submit("job", lambda: "A", key="x")
    b = ex.submit("job", lambda: "B", key="x")  # 默认 replace：顶替排队中的 a
    check("默认：合并计数>=1", ex.counters()["merged"] >= 1, ex.counters())
    check("默认：a 被顶替", ex.wait(a["job_id"], timeout=10).get("status") == "superseded")

    # 执行中的作业，默认不被合并 -> 第二次提交拿到新的 job_id，且原作业不被顶替
    ex.submit("block2", lambda: time.sleep(0.3), key="b2")
    a2 = ex.submit("job2", lambda: (time.sleep(0.6), "A2")[1], key="y")
    deadline = time.time() + 5
    while time.time() < deadline and ex.status(a2["job_id"]).get("status") != "running":
        time.sleep(0.02)
    check("默认：前置作业已进入 running", ex.status(a2["job_id"]).get("status") == "running")
    b2 = ex.submit("job2", lambda: "B2", key="y")
    check("默认：执行中不被合并（新 job_id）", b2["job_id"] != a2["job_id"])
    check("默认：执行中作业不被顶替", ex.status(a2["job_id"])["status"] in ("running", "done"))
    check("默认：scheduled 计数递增", ex.counters()["scheduled"] >= 4, ex.counters())
    ex.shutdown()


def test_coalesce_running() -> None:
    ex = MaintenanceExecutor(max_workers=1, keep=8)
    ex.submit("block", lambda: time.sleep(0.5), key="b")
    a = ex.submit("validate_kb", lambda: "A", key="kb1", coalesce_running=True)
    b = ex.submit("validate_kb", lambda: "B", key="kb1", coalesce_running=True)  # 排队中 -> 复用
    check("合并(排队)：同一 job_id 复用", a["job_id"] == b["job_id"], (a["job_id"], b["job_id"]))
    check("合并：返回 coalesced 标记", bool(b.get("coalesced")))

    st = ex.wait(a["job_id"], timeout=10)
    check("合并：原作业完成且结果来自首次提交", st.get("status") == "done" and st.get("result") == "A", st.get("result"))

    # 执行中合并
    ex.submit("block2", lambda: time.sleep(0.2), key="b2")
    r1 = ex.submit("validate_kb", lambda: (time.sleep(0.6), "R1")[1], key="kb2", coalesce_running=True)
    deadline = time.time() + 5
    while time.time() < deadline and ex.status(r1["job_id"]).get("status") != "running":
        time.sleep(0.02)
    check("合并(执行中)：前置作业已进入 running", ex.status(r1["job_id"]).get("status") == "running")
    r2 = ex.submit("validate_kb", lambda: "R2", key="kb2", coalesce_running=True)
    check("合并(执行中)：同一 job_id 复用", r1["job_id"] == r2["job_id"], (r1["job_id"], r2["job_id"]))
    check("合并(执行中)：job_status=running", r2.get("job_status") == "running", r2.get("job_status"))
    st2 = ex.wait(r1["job_id"], timeout=10)
    check("合并(执行中)：只执行一次（结果=R1）", st2.get("result") == "R1", st2.get("result"))
    check("合并：coalesced 计数>=2", ex.counters()["coalesced"] >= 2, ex.counters())

    # 不同 key 不合并
    c = ex.submit("validate_kb", lambda: "C", key="kb3", coalesce_running=True)
    check("不同 key 不合并", c["job_id"] != r2["job_id"])
    ex.shutdown()


def test_red_green_coalesce() -> None:
    """先证红：同一份重活并发提交，改前跑 2 次；合并后只跑 1 次。"""
    work_s = 0.5

    # RED：不合并（等价改前行为）——单 worker 下两次执行串行
    red = MaintenanceExecutor(max_workers=1, keep=8)
    t0 = time.perf_counter()
    ra = red.submit("validate_kb", lambda: (time.sleep(work_s), "R")[1], key="kb", coalesce_running=False)
    rb = red.submit("validate_kb", lambda: (time.sleep(work_s), "R")[1], key="kb", coalesce_running=False)
    red.wait(ra["job_id"], timeout=10)
    red.wait(rb["job_id"], timeout=10)
    red_elapsed = time.perf_counter() - t0
    red_executed = red.counters()["executed"]
    red.shutdown()

    # GREEN：coalesce_running=True —— 第二次提交复用同一作业
    green = MaintenanceExecutor(max_workers=1, keep=8)
    t0 = time.perf_counter()
    ga = green.submit("validate_kb", lambda: (time.sleep(work_s), "R")[1], key="kb", coalesce_running=True)
    gb = green.submit("validate_kb", lambda: (time.sleep(work_s), "R")[1], key="kb", coalesce_running=True)
    green.wait(ga["job_id"], timeout=10)
    green_elapsed = time.perf_counter() - t0
    green_executed = green.counters()["executed"]
    green.shutdown()

    print(f"  证红/证绿：改前 executed={red_executed} wall={red_elapsed*1000:.0f}ms | "
          f"合并后 executed={green_executed} wall={green_elapsed*1000:.0f}ms")
    check("证红：改前同活执行 2 次", red_executed == 2, red_executed)
    check("证绿：合并后只执行 1 次", green_executed == 1, green_executed)
    check("证绿：墙钟约省一半", green_elapsed < red_elapsed * 0.75,
          (round(red_elapsed * 1000), round(green_elapsed * 1000)))


def test_real_validate(kb_src: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from memoria.services.document import DocumentService
    from memoria.services.executor import MaintenanceExecutor as _Ex

    tmp = tempfile.mkdtemp(prefix="memoria_p1_assert_")
    kb = os.path.join(tmp, "kb")
    try:
        shutil.copytree(kb_src, kb)
        svc = DocumentService(kb_path=kb)
        sync = svc.validate_kb()
        ex = _Ex(max_workers=1, keep=8)
        t0 = time.perf_counter()
        first = ex.submit("validate_kb", lambda: svc.validate_kb(), key=kb, coalesce_running=True)
        submit_ms = (time.perf_counter() - t0) * 1000
        check("真实 validate：提交立即返回(<80ms)", submit_ms < 80, round(submit_ms, 1))
        second = ex.submit("validate_kb", lambda: svc.validate_kb(), key=kb, coalesce_running=True)
        check("真实 validate：并发提交合并为同一作业", first["job_id"] == second["job_id"])
        st = ex.wait(first["job_id"], timeout=180)
        res = st.get("result") or {}
        check("真实 validate：作业 done", st.get("status") == "done", st.get("status"))
        check("真实 validate：errors 与同步一致", res.get("errors") == sync.get("errors"),
              (res.get("errors"), sync.get("errors")))
        check("真实 validate：files_checked 与同步一致",
              res.get("files_checked") == sync.get("files_checked"))
        check("真实 validate：结果字段完整",
              all(k in res for k in ("status", "issues_count", "graph_audit", "kb_integrity", "manifest_diff")))
        ex.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_default_semantics_unchanged()
    test_coalesce_running()
    test_red_green_coalesce()
    kb = ROOT / "artifacts" / "baseline-kb" / "\u6570\u5b57\u901a\u4fe1\u539f\u7406"
    if kb.is_dir():
        test_real_validate(kb)
    else:
        print("SKIP  基准语料不存在，跳过真实 validate 断言")
    print(f"\ntask-69 P1 执行器合并断言：{'全 PASS' if not fails else str(len(fails)) + ' 项失败'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
