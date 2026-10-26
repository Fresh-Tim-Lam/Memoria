"""重签 freeze-v2 收据（rules sha 因 v2.1 变化）。"""
import datetime
import io
import json
import pathlib
import sys

sys.path.insert(0, "scripts/agent")
from team_audit import content_sha256  # noqa: E402

P = pathlib.Path("artifacts/agent/verify/debate/freeze-v2.json")
TARGET = "docs/guides/lead-dispatch-rules.md"
new_sha = content_sha256(pathlib.Path(TARGET))

d = json.load(io.open(P, encoding="utf-8"))
old = None
for it in d["standards"]:
    if it.get("path") == TARGET:
        old = it["sha256_lf"]
        it["sha256_lf"] = new_sha
assert old and old != new_sha, "sha 未变化，检查是否真的改了文件"

now = datetime.datetime.now().astimezone().isoformat()
d.setdefault("standards_updated", []).append({
    "at": now,
    "by": "lead",
    "commit_before": None,
    "reason": "B-danger-1 v2.1（steward SF-056 审计 4 点：worktree 独占措辞 / 删除不可机检的独占(a) / R1 谁可执行 / 位置前移）",
    "changed": [{"path": TARGET, "from": old, "to": new_sha}],
})
d["standards_frozen_at"] = now
io.open(P, "w", encoding="utf-8", newline="").write(
    json.dumps(d, ensure_ascii=False, indent=2) + "\n")
print("  rules sha %s -> %s" % (old[:12], new_sha[:12]))
print("  standards_updated 条数 =", len(d["standards_updated"]))
