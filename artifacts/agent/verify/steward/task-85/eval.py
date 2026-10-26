#!/usr/bin/env python3
"""task-85 只读评估：图谱审计启动重复跑的成本与收益（不修改任何产品代码）。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from memoria.graph.link_audit import audit_kb_graph_links  # noqa: E402

kb = r"artifacts/baseline-kb/数字通信原理"
if not Path(kb).is_dir():
    print("KB 不存在:", kb)
    raise SystemExit(1)

times = []
for _ in range(3):
    t0 = time.perf_counter()
    report = audit_kb_graph_links(kb)
    times.append((time.perf_counter() - t0) * 1000)
print("audit_kb_graph_links ms:", [round(x, 1) for x in times],
      "files:", report["summary"]["files_checked"],
      "issues:", report["summary"]["issue_count"])

# 统计调用点
calls = []
for path in Path("src").rglob("*.py"):
    for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if "audit_kb_graph_links(" in line and "def " not in line:
            calls.append((str(path), no, line.strip()))
print("\naudit_kb_graph_links 调用点:", len(calls))
for item in calls:
    print(" ", item[0], item[1], "|", item[2][:120])

# 前端启动路径里的相关 RPC（只读）
print("\n前端启动路径相关调用（app.js/kb-check.js）:")
for rel in ("src/memoria/ui/static/app/js/app.js", "src/memoria/ui/static/app/js/kb-check.js"):
    path = Path(rel)
    if not path.is_file():
        continue
    for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if any(key in line for key in ("get_graph_data", "get_graph_audit", "validate_kb_async",
                                       "runKbValidate", "submitAsyncValidate", "scheduleSilentValidate")):
            print(f"  {path.name}:{no}: {line.strip()[:130]}")

# 现有缓存痕迹
print("\n可能相关的缓存/构建产物:")
for path in Path("src").rglob("*.py"):
    text = path.read_text(encoding="utf-8", errors="replace")
    if "graph_audit.json" in text or "graph_audit" in text and "cache" in text.lower():
        print(" ", path)
