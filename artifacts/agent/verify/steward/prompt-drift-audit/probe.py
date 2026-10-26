#!/usr/bin/env python3
"""prompt_drift_check.py 的"守卫是否真的守卫"审计探针（只读；不修改任何文件）。

做法：import 模块 → 构造 Ctx（真实仓库）→ 用 monkeypatch 让 prompt_doc_rels/read 返回
我们构造的提示词文本 → 调对应 check_* 函数 → 观察 findings。
若"应当 FAIL 的东西没有 FAIL"，即证明该分支是静默放行（guard that doesn't guard）。
"""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("prompt_drift_check", "scripts/agent/prompt_drift_check.py")
pd = importlib.util.module_from_spec(spec)
sys.modules["prompt_drift_check"] = pd
spec.loader.exec_module(pd)

repo = Path(".").resolve()


def run_case(name: str, check_fn, text: str, *, patch_edge_empty: bool = False):
    ctx = pd.Ctx(repo=repo, kb_agent=pd.load_kb_agent(repo))
    original_read = ctx.read
    fake_rel = "resources/agent-prompts/__probe__.md"

    def read(rel: str):
        if rel == fake_rel:
            return text
        return original_read(rel)

    ctx.read = read
    pd.prompt_doc_rels = lambda _ctx: [fake_rel]  # type: ignore[assignment]
    if patch_edge_empty:
        ctx._edge_types = {"edge_types": set(), "aliases": set()}
    check_fn(ctx)
    return ctx.findings


def show(name: str, findings: list, needle: str | None = None):
    print(f"\n### {name}")
    if not findings:
        print("  findings: <none>")
    for f in findings:
        mark = "  *" if needle and needle in f.message else "   "
        print(f"{mark}[{f.severity}] {f.check}: {f.message[:160]}")
    if needle:
        hit = any(needle in f.message for f in findings)
        print(f"  => 含 {needle!r}: {hit}")


edge = pd.Ctx(repo=repo, kb_agent=pd.load_kb_agent(repo)).edge_types()
alias = sorted(edge["aliases"] or edge["edge_types"])[:1]
alias_str = alias[0] if alias else "contain"
print("edge alias sample:", alias_str, "| strip_active:",
      "strip_known_wikilink_edge_hints(" in (repo / "src/memoria/graph/kb_build.py").read_text(encoding="utf-8"))

# 探针 A：C2 点分字段里的 camelCase 段（按设计只校验 snake 段）
a_control = run_case(
    "A-control snake 段",
    pd.check_symbols,
    "示例：`range.fake_snake_field` 是伪造字段。\n",
)
show("A-control：`range.fake_snake_field`（应 FAIL）", a_control, "fake_snake_field")

a_camel = run_case(
    "A-camel 段",
    pd.check_symbols,
    "示例：`range.fakeCamelField` 是伪造字段。\n",
)
show("A-camel：`range.fakeCamelField`（当前实现无 finding？）", a_camel, "fakeCamelField")

# 探针 B：C3 同一行出现任意限定词即整行豁免
b_recommend = run_case(
    "B-control 推荐写法无限定词",
    pd.check_forbidden_syntax,
    f"推荐写法：在正文写 [[某知识点#{alias_str}]] 即可标注关系。\n",
)
show("B-control：推荐 [[...#alias]]（应 FAIL）", b_recommend, "会被构建剥离")

b_qualifier = run_case(
    "B-同句含'不要'",
    pd.check_forbidden_syntax,
    f"推荐写法：在正文写 [[某知识点#{alias_str}]] 即可标注关系，不要写错别字。\n",
)
show("B-限定词绕过：推荐语法 + 同句无关'不要'（应 FAIL，实际？）", b_qualifier, "会被构建剥离")

# 探针 C：C3 当边类型读不到时只 WARN 跳过（门禁层 WARN≠FAIL）
c_degraded = run_case(
    "C-edge_types 读不到",
    pd.check_forbidden_syntax,
    f"推荐写法：在正文写 [[某知识点#{alias_str}]] 即可。\n",
    patch_edge_empty=True,
)
show("C-输入不可读时（应视为'未执行'，当前只 WARN）", c_degraded, "无法从 edge_types.py 读取")
print("  summary:", pd._summary(c_degraded), "=> exit code would be",
      "1" if any(f.severity == pd.FAIL for f in c_degraded) else "0")
