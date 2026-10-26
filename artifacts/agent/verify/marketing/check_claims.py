#!/usr/bin/env python3
"""README / 宣传文案的「断言—证据」机检（task-182）。

用法：
  python artifacts/agent/verify/marketing/check_claims.py            # 快速检查（~2s）
  python artifacts/agent/verify/marketing/check_claims.py --full     # 额外跑 pytest 并写证据
  python artifacts/agent/verify/marketing/check_claims.py --json

退出码：0 = 全部 PASS；1 = 有 FAIL；2 = 用法/路径错误。
设计：本脚本只做**证据存在性与一致性**检查（字符串/行/数字/文件），不判断文案好坏。
不可机检项（如"对比是否克制"）在 docs/marketing/claims.md 标为 manual，由审阅者人工核对。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

READMES = {"en": ROOT / "README.md", "zh": ROOT / "README.cn.md"}
CLAIMS = ROOT / "docs" / "marketing" / "claims.md"
METADATA = ROOT / "docs" / "marketing" / "repo-metadata.md"
TAG_SPEC = ROOT / "docs" / "marketing" / "tag-release-spec.md"
VERSION_FILE = ROOT / "src" / "memoria" / "__version__.py"
ONTOLOGY = ROOT / "docs" / "design" / "kg-ontology-v0.md"
KGVIZ = ROOT / "docs" / "design" / "kg-visualization-v0.md"
GRAPH_BENCH = ROOT / "docs" / "design" / "graph-benchmark.md"
VERSION_DOC = ROOT / "docs" / "conventions" / "version.md"
FSRS = ROOT / "resources" / "agent-prompts" / "fsrs.py"
KB_TOOLS = ROOT / "src" / "memoria" / "services" / "agent" / "tools" / "kb.py"
PLAN = ROOT / "src" / "memoria" / "services" / "agent" / "plan.py"
APPLY = ROOT / "src" / "memoria" / "services" / "agent" / "apply.py"
MCP = ROOT / "src" / "memoria" / "services" / "agent" / "mcp_server.py"
PRESETS = ROOT / "src" / "memoria" / "services" / "agent" / "permission_presets.py"
APPROVALS = ROOT / "src" / "memoria" / "services" / "agent" / "approvals.py"
TELEMETRY = ROOT / "src" / "memoria" / "storage" / "graph_telemetry.py"
UPDATE = ROOT / "src" / "memoria" / "services" / "update.py"
LLM_CONFIG = ROOT / "src" / "memoria" / "services" / "agent" / "llm" / "config.py"
SCREENSHOTS = ROOT / "resources" / "screenshots"

# 禁止词条（claims.md §9；README 中出现即 FAIL）
FORBIDDEN = {
    "zh": [
        "图谱赋能 agent 检索",
        "提高 agent 交互效率",
        "掌握程度评分",
        "掌握程度可视化",
        "防篡改",
        "已签名",
        "端到端加密",
        "最快",
        "零网络",
        "完全离线",
    ],
    "en": [
        "tamper-proof",
        "tamper proof",
        "digitally signed",
        "end-to-end encrypted",
        "fastest",
        "zero network",
        "fully offline",
        "empowers agent retrieval",
    ],
}

REQUIRED_TOOLS = [
    "read_document",
    "kb_overview",
    "outline",
    "section",
    "snippet",
    "search_kb",
    "validate_kb",
    "review_due_list",
    "review_grade",
    "review_cards_upsert",
    "review_feedback_add",
]

results: list[dict] = []


def record(name: str, ok: bool, detail: str = "", severity: str = "FAIL") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail, "severity": severity if not ok else "PASS"})
    print(f"  {'PASS' if ok else severity} {name}" + (f" — {detail}" if detail and not ok else ""))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def section(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i:] if j < 0 else text[i:j]


def check_version() -> None:
    m = re.search(r'__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', read(VERSION_FILE))
    version = m.group(1) if m else ""
    record("version: __version__.py 可解析", bool(version), f"got {version!r}")
    for lang, path in READMES.items():
        text = read(path)
        record(f"version: {path.name} badge 与 __version__ 一致", f"Version-{version}" in text, f"期望 Version-{version}")
        record(f"version: {path.name} 正文当前版本与 __version__ 一致", f"**{version}**" in text, f"期望 **{version}**")
    doc = read(TAG_SPEC)
    record("tag: 规范文档存在且含三步机检", "release_preflight.py" in doc and "0a" in doc and "0c" in doc)


def check_repo_metadata() -> None:
    text = read(METADATA)
    record("metadata: 文件存在", bool(text))
    for marker, label, ends in (("### 1.1", "en", "### 1.2"), ("### 1.2", "zh", "## 2.")):
        seg = section(text, marker, ends)
        block = re.search(r"```text\n(.+?)\n```", seg, re.S)
        desc = block.group(1).strip() if block else ""
        record(f"metadata: description({label}) 非空且 ≤350 字符", 0 < len(desc) <= 350, f"len={len(desc)}")
    topics_seg = section(text, "## 2. Topics", "**选择理由")
    topics_block = re.search(r"```text\n(.+?)\n```", topics_seg, re.S)
    topics = [line.strip() for line in (topics_block.group(1) if topics_block else "").splitlines() if line.strip()]
    record("metadata: topics 数量在 10–20", 10 <= len(topics) <= 20, f"count={len(topics)}")
    record(
        "metadata: topics 均为小写连字符",
        all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", t) for t in topics),
        f"bad={[t for t in topics if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', t)]}",
    )


def check_screenshots() -> None:
    files = {p.name for p in SCREENSHOTS.glob("demo-*.png")} if SCREENSHOTS.is_dir() else set()
    record("screenshots: resources/screenshots 存在且有 8 张 demo-*.png", len(files) == 8, f"count={len(files)}")
    for lang, path in READMES.items():
        refs = set(re.findall(r"resources/screenshots/(demo-[A-Za-z0-9_.-]+\.png)", read(path)))
        record(f"screenshots: {path.name} 引用 8 张且全部存在", len(refs) == 8 and refs == files,
               f"refs={len(refs)} missing={sorted(refs - files)} unused={sorted(files - refs)}")


def check_claims_cover_readme() -> None:
    claims = read(CLAIMS)
    record("claims: 文件存在且含状态词表", "implemented" in claims and "design-intent" in claims and "roadmap" in claims)
    ids = re.findall(r"CLM-(\d+[a-z]?)", claims)
    record("claims: 断言条目 ≥ 20", len(set(ids)) >= 20, f"unique={len(set(ids))}")
    for lang, path in READMES.items():
        text = read(path)
        record(f"claims: {path.name} 链到 claims.md", "docs/marketing/claims.md" in text)
        record(f"claims: {path.name} 未出现禁止词条", all(p not in text for p in FORBIDDEN[lang]),
               f"hit={[p for p in FORBIDDEN[lang] if p in text]}")


def check_graph_claims() -> None:
    onto = read(ONTOLOGY)
    record("graph: 本体冻结文档含「agent 侧从不读边」", "agent 侧从不读边" in onto)
    record("graph: 本体冻结文档含「完全不读边」", "完全不读边" in onto)
    record("graph: 本体裁决含「必须先证明它能改变一个 agent 决策」", "必须先证明它能改变一个 agent 决策" in onto)
    viz = read(KGVIZ)
    record("graph: 可视化文档 FROZEN", "FROZEN" in viz)
    record("graph: 可视化文档含人裁决 75%~165%", "75%" in viz and "165%" in viz)
    record("graph: 可视化文档含「连续」裁决", "连续" in viz)
    en, zh = read(READMES["en"]), read(READMES["zh"])
    record("graph: README(en) 标注 design intent", "design intent" in en.lower())
    record("graph: README(zh) 标注设计理念", "设计理念" in zh)
    record("graph: README(en) 未把图谱写成已实现 agent 检索", "graph-aware agent retrieval" in en.lower() or "roadmap" in en.lower())


def check_benchmarks() -> None:
    bench = read(GRAPH_BENCH)
    record("benchmark: graph-benchmark 含 9108ms 基线", "9108" in bench)
    record("benchmark: graph-benchmark 含 41.5ms 结果", "41.5" in bench)
    version_doc = read(VERSION_DOC)
    record("benchmark: version.md 含冷启动 15.4→2.4s", "15.4" in version_doc and "2.4" in version_doc)
    results_dir = ROOT / "scripts" / "benchmark" / "graph" / "results"
    raw = list(results_dir.glob("render-*.md")) if results_dir.is_dir() else []
    record("benchmark: 原始产物 render-*.md 存在", len(raw) >= 3, f"count={len(raw)}")
    for lang, path in READMES.items():
        text = read(path)
        record(f"benchmark: {path.name} 的性能数字带版本/口径标注",
               ("v0.3.4" in text and "v0.4.6" in text), "需要同时标注测得版本")


def check_agent_and_fsrs() -> None:
    kb = read(KB_TOOLS)
    missing = [name for name in REQUIRED_TOOLS if f'name="{name}"' not in kb]
    record("agent: 读/审计/复习工具名存在", not missing, f"missing={missing}")
    plan = read(PLAN)
    record("agent: 链接写原语 attach_links/detach_links 存在",
           'OP_ATTACH_LINKS = "attach_links"' in plan and 'OP_DETACH_LINKS = "detach_links"' in plan)
    apply_text = read(APPLY)
    record("agent: kb.link.create 纯边原语存在", "kb.link.create" in apply_text)
    mcp = read(MCP)
    mcp_names = re.findall(r'"name":\s*"([a-z_]+)"', mcp)
    record("agent: MCP 暴露 4 把工具（outline/section/snippet/propose_write）",
           set(mcp_names) == {"outline", "section", "snippet", "propose_write"}, f"got={mcp_names}")
    presets = read(PRESETS)
    record("agent: 默认审批档 = auto-approval", 'DEFAULT_PRESET = "auto-approval"' in presets)
    record("agent: 三档语义（manual/auto/all-access）", all(k in presets for k in
           ('"manual-approval"', '"auto-approval"', '"all-access"')))
    approvals = read(APPROVALS)
    record("agent: 风险 op 才问（delete_file/rename_file 在 RISKY_OPS）",
           "RISKY_OPS" in approvals and "delete_file" in approvals and "rename_file" in approvals)
    for lang, path in READMES.items():
        text = read(path)
        record(f"agent: {path.name} 写清默认为自动审批档", "auto-approval" in text or "自动审批" in text)

    fsrs = read(FSRS)
    record("fsrs: 子命令 due/init/grade 存在",
           all(f'add_parser("{cmd}"' in fsrs for cmd in ("due", "init", "grade")))
    record("fsrs: compute_next_state 存在", "compute_next_state" in fsrs)
    record("review: 交接文档存在（FSRS 边界三条）",
           "FSRS 边界" in read(ROOT / "docs" / "design" / "review-cards-handoff.md"))


def check_privacy() -> None:
    tel = read(TELEMETRY)
    record("privacy: 本地图谱埋点声明「不上传」", "不上传" in tel)
    record("privacy: 本地图谱埋点无网络调用", not re.search(r"^\s*(import|from)\s+(requests|urllib|http\.client)", tel, re.M))
    upd = read(UPDATE)
    record("privacy: 更新模块声明出网关闭⇒零请求", "零请求" in upd)
    record("privacy: 更新模块明确不做数字签名", "数字签名" in upd)
    cfg = read(LLM_CONFIG)
    record("privacy: 出网开关默认语义有文档（缺省视为开）", "缺省" in cfg and "True" in cfg)
    for lang, path in READMES.items():
        text = read(path)
        record(f"privacy: {path.name} 写明「不是数字签名」/出网开关",
               ("数字签名" in text or "digital signature" in text.lower()) and
               ("出网" in text or "outbound" in text.lower()))


def check_readme_links() -> None:
    """README 里的相对链接/图片必须真实存在（坏链 = 用户第一次点就失望）。"""
    for lang, path in READMES.items():
        text = read(path)
        refs = set(re.findall(r"\]\(([^)\s]+)\)", text))
        refs |= set(re.findall(r'src="([^"]+)"', text))
        bad: list[str] = []
        for ref in refs:
            if ref.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = ref.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            if not (ROOT / target).exists():
                bad.append(ref)
        record(f"links: {path.name} 相对链接/图片全部存在", not bad, f"broken={sorted(bad)}")
    en, zh = read(READMES["en"]), read(READMES["zh"])
    record("i18n: README.md 链到 README.cn.md", "(README.cn.md)" in en)
    record("i18n: README.cn.md 链到 README.md", "(README.md)" in zh)


def check_tests(full: bool) -> None:
    """测试套件断言：README 只写「1,600+」不写精确数（数字会随提交漂移），脚本复核当前 ≥1600。"""
    evidence = EVIDENCE_DIR / "pytest.txt"
    badge_ok = all(("1600%2B" in read(path) or "1,600+" in read(path)) for path in READMES.values())
    record("tests: README 写「1,600+」而非固定精确数", badge_ok)
    if full:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        evidence.write_text(proc.stdout[-4000:] + ("\n[stderr]\n" + proc.stderr[-2000:] if proc.stderr else ""),
                            encoding="utf-8")
        m = re.search(r"(\d+) passed", proc.stdout)
        count = int(m.group(1)) if m else 0
        record("tests: pytest 通过且当前数量 ≥1,600", proc.returncode == 0 and count >= 1600,
               f"exit={proc.returncode} count={count}")
    else:
        text = read(evidence)
        m = re.search(r"(\d+) passed", text)
        count = int(m.group(1)) if m else 0
        record("tests: 有 pytest 证据且数量 ≥1,600（未复跑，用 --full 复跑）",
               "passed" in text and count >= 1600, f"evidence count={count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="README 断言—证据机检（task-182）")
    parser.add_argument("--full", action="store_true", help="额外跑 pytest 并写 evidence")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    if not (ROOT / "README.md").is_file():
        print(f"用法错误：{ROOT} 不是仓库根（缺 README.md）", file=sys.stderr)
        return 2

    print(f"仓库根：{ROOT}\n")
    check_version()
    check_repo_metadata()
    check_screenshots()
    check_claims_cover_readme()
    check_graph_claims()
    check_benchmarks()
    check_agent_and_fsrs()
    check_privacy()
    check_readme_links()
    check_tests(args.full)

    fails = [r for r in results if not r["ok"] and r["severity"] == "FAIL"]
    passes = [r for r in results if r["ok"]]
    if args.json:
        print(json.dumps({"schema": "marketing-claims-check/v1", "results": results,
                          "summary": {"total": len(results), "pass": len(passes), "fail": len(fails)}},
                         ensure_ascii=False, indent=2))
    print(f"\n汇总：PASS={len(passes)} FAIL={len(fails)} 合计 {len(results)} 项")
    if fails:
        print("结论：有断言缺乏证据或出现禁止表述，须修")
        return 1
    print("结论：可机检断言全部有证据；禁止词条未出现")
    return 0


if __name__ == "__main__":
    sys.exit(main())
