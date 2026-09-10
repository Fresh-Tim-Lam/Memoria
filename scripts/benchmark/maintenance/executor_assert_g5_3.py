#!/usr/bin/env python3
"""G5.3 出口断言：后端执行器——提交不阻塞 / replace 合并 / 真实 validate 异步一致。

用法：python scripts/benchmark/maintenance/executor_assert_g5_3.py
退出码 0=全 PASS，1=有 FAIL。
"""
from __future__ import annotations

import sys
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


def main() -> int:
    # 1) 提交不阻塞：即时返回 job_id，执行在后台
    ex = MaintenanceExecutor(max_workers=1, keep=8)
    t0 = time.perf_counter()
    r = ex.submit("slow", lambda: (time.sleep(1.2), "ok")[1], key="k1")
    ret_ms = (time.perf_counter() - t0) * 1000
    check("submit 立即返回(<80ms)", ret_ms < 80, round(ret_ms, 1))
    check("初始状态 queued/running", ex.status(r["job_id"])["status"] in ("queued", "running"))
    st = ex.wait(r["job_id"], timeout=10)
    check("作业完成 done", st.get("status") == "done", st.get("status"))
    check("结果正确", st.get("result") == "ok", st.get("result"))

    # 2) replace 合并：同 kind+key 仍排队时被顶替
    ex2 = MaintenanceExecutor(max_workers=1, keep=8)
    ex2.submit("block", lambda: time.sleep(0.6), key="b")  # 占住唯一 worker
    a = ex2.submit("job", lambda: "A", key="x")
    b = ex2.submit("job", lambda: "B", key="x")
    check("合并计数>=1", ex2.counters()["merged"] >= 1, ex2.counters())
    check("旧作业被顶替(superseded)", ex2.wait(a["job_id"], timeout=10).get("status") == "superseded")
    sb = ex2.wait(b["job_id"], timeout=10)
    check("新作业完成且结果=B", sb.get("status") == "done" and sb.get("result") == "B", sb.get("result"))

    # 3) 真实 validate：异步作业结果与同步调用一致（RPC 不再被重活占用）
    kb = ROOT / "artifacts" / "_bench_maintenance" / "kb"
    if kb.is_dir():
        from memoria.services.document import DocumentService
        from memoria.services.executor import get_executor

        svc = DocumentService(kb_path=str(kb))
        sync = svc.validate_kb()
        ex3 = get_executor()
        t0 = time.perf_counter()
        r3 = ex3.submit("validate_kb", lambda: svc.validate_kb(), key=str(kb))
        ret3 = (time.perf_counter() - t0) * 1000
        check("validate 提交立即返回(<80ms)", ret3 < 80, round(ret3, 1))
        st3 = ex3.wait(r3["job_id"], timeout=180)
        check("validate 作业 done", st3.get("status") == "done", st3.get("status"))
        res = st3.get("result") or {}
        check("异步 errors 与同步一致", res.get("errors") == sync.get("errors"), (res.get("errors"), sync.get("errors")))
        check("异步 files_checked 一致", res.get("files_checked") == sync.get("files_checked"))
        print("  执行器快照:", ex3.snapshot())
    else:
        print("SKIP  基准语料不存在，跳过真实 validate 断言")

    print(f"\nG5.3 执行器断言：{'全 PASS' if not fails else str(len(fails)) + ' 项失败'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
