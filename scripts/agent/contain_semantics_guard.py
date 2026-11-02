#!/usr/bin/env python3
"""contain 语义区分的机检（v0.2：`contain_kind` structural|semantic）。

背景（人，2026-11-02）：「文本上的 contain 不一定真实具有 contain 的语义，所以有必要做一些
区分，别让程序自动一视同仁处理为 contain 边。」批准重开 ontology v0.2：
`dec-20261102-3b8e6eb6`（人批）。

事实与口径：
- `derive_contain_edges()` 只按知识点 **区间几何包含** 生成 `type="contain"`，因此派生层
  静态写 `contain_kind="structural"`（不承诺整体-部分语义，也不写 sidecar——B1/dec-50f0acdb）。
- `semantic` 只能来自作者/人工 curation，且必须带 `assertion_source`（schema `allOf` 强制）；
  旧数据/缺字段按 `structural`（fail-safe）。
- 消费侧文案必须区分两种含义；本脚本把口径与消费点钉住，改文案/删字段会报红。

用法：
    python scripts/agent/contain_semantics_guard.py            # 机检（FAIL → exit 1）
    python scripts/agent/contain_semantics_guard.py --selftest # 红路径自测
    python scripts/agent/contain_semantics_guard.py --json     # 机器可读输出
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: (检查名, 相对路径, 必须出现的片段)
REQUIRED = [
    ("i18n-zh-structural-label", "src/memoria/ui/static/app/i18n/zh-CN.js", 'typeContain: "结构包含"'),
    ("i18n-zh-note", "src/memoria/ui/static/app/i18n/zh-CN.js", 'containNote: "由知识点区间推导，语义未验证"'),
    ("i18n-zh-semantic-label", "src/memoria/ui/static/app/i18n/zh-CN.js", 'typeContainSemantic: "包含（作者确认）"'),
    ("i18n-zh-semantic-note", "src/memoria/ui/static/app/i18n/zh-CN.js", 'containSemanticNote: "作者/人工确认的整体-部分关系"'),
    ("i18n-en-structural-label", "src/memoria/ui/static/app/i18n/en.js", 'typeContain: "Structural contain"'),
    ("i18n-en-note", "src/memoria/ui/static/app/i18n/en.js", 'containNote: "Derived from note ranges; semantic containment is NOT verified"'),
    ("i18n-en-semantic-label", "src/memoria/ui/static/app/i18n/en.js", 'typeContainSemantic: "Contain (author-confirmed)"'),
    ("i18n-en-semantic-note", "src/memoria/ui/static/app/i18n/en.js", 'containSemanticNote: "Whole-part relation asserted by the author/curation"'),
    ("badge-kind-branch", "src/memoria/ui/static/app/js/app.js", 'const isSemantic = type === "contain" && edge && edge.contain_kind === "semantic";'),
    ("badge-semantic-label", "src/memoria/ui/static/app/js/app.js", 'T("cfg.edge.typeContainSemantic")'),
    ("derivation-structural", "src/memoria/graph/edge_derivation.py", '"contain_kind": "structural"'),
    ("agent-prompt-v02", "src/memoria/services/agent/tools/kb.py", "contain_kind=structural"),
    ("schema-field", "docs/design/kg-edge-provenance.schema.json", '"contain_kind"'),
    ("ontology-v02", "docs/design/kg-ontology-v0.md", "contain_kind"),
    # v0.2 作者流程（semantic 的唯一合法写入通路；人批 dec-20261102-2dcefd31）
    ("ontology-overlay-rule", "docs/design/kg-ontology-v0.md", "curation overlay"),
    ("collector-overlay-merge", "src/memoria/graph/collector.py", "merge_contain_curation_overlays"),
    ("derivation-overlay-valid", "src/memoria/graph/edge_derivation.py", "validate_contain_curation_overlay"),
    ("document-curate-api", "src/memoria/services/document.py", "def curate_contain("),
    ("curate-requires-human", "src/memoria/services/document.py", "confirmed_by 不能为空"),
    # v0.2 作者流程的 UI 入口（人确认按钮 + RPC + i18n）
    ("ui-curate-button", "src/memoria/ui/static/app/js/app.js", "-edge-btn-curate"),
    ("ui-curate-rpc", "src/memoria/ui/static/app/js/app.js", 'call("curate_contain"'),
    ("ui-uncurate-rpc", "src/memoria/ui/static/app/js/app.js", 'call("remove_contain_curation"'),
    ("ui-i18n-zh-curate", "src/memoria/ui/static/app/i18n/zh-CN.js", 'curateBtn: "确认为整体-部分"'),
    ("ui-i18n-en-curate", "src/memoria/ui/static/app/i18n/en.js", 'curateBtn: "Confirm whole-part"'),
    ("ui-rpc-backend", "src/memoria/presentation/api/ui.py", "def curate_contain("),
]
#: 必须**不存在**的文本（agent 只能提议，落库仅人确认）。
NEGATIVE = [
    ("agent-tools-no-curate", "src/memoria/services/agent/tools/kb.py", "curate_contain",
     "agent 只能提议；semantic 落库仅允许人确认（curate_contain 不得进 agent 工具面）"),
]

#: 已知 contain 消费/定义点：删改必须显式面对（读取点清单是审计对象）。
CONSUMERS = [
    ("src/memoria/graph/edge_derivation.py", "derive_contain_edges", "唯一派生者；v0.2 写 structural"),
    ("src/memoria/graph/edge_derivation.py", '"contain_kind": "structural"', "structural 的静态来源"),
    ("src/memoria/graph/collector.py", "dedupe_graph_edges", "拼装 contain+link+sidecar 后 dedupe"),
    ("src/memoria/graph/edge_types.py", "DERIVE_ONLY_EDGE_TYPES", "contain 属派生专用（禁手标）"),
    ("src/memoria/services/agent/plan.py", "contain", "agent 边类型允许集合"),
    ("src/memoria/services/agent/tools/kb.py", "contain_kind=structural", "agent 工具文案"),
    ("src/memoria/ui/static/app/js/graph-engine.js", "expandLinks", "主图渲染只读 type/source/targets/relevance"),
    ("src/memoria/ui/static/app/js/app.js", 'e.type === "contain"', "KP 边页签按 type 判断可抑制派生边"),
    ("src/memoria/ui/static/app/js/app.js", "contain_kind === \"semantic\"", "badge 按 contain_kind 分支"),
    ("src/memoria/ui/static/app/js/graph-synthetic.js", "expandLinks", "合成图同口径"),
    ("src/memoria/ui/static/app/i18n/zh-CN.js", "typeContainSemantic", "中文 semantic 文案"),
    ("src/memoria/ui/static/app/i18n/en.js", "typeContainSemantic", "英文 semantic 文案"),
    ("docs/design/kg-ontology-v0.md", "contain_kind", "v0.2 契约字段"),
    ("docs/design/kg-edge-provenance.schema.json", '"contain_kind"', "canonical schema 字段"),
]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def run_checks(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    required: list[dict] = []
    for name, rel, needle in REQUIRED:
        text = read_text(root / rel)
        ok = text is not None and needle in text
        required.append({
            "check": name,
            "file": rel,
            "needle": needle,
            "pass": ok,
            "detail": None if ok else f"缺少必需文本：{needle!r}",
        })
    consumers: list[dict] = []
    for rel, needle, role in CONSUMERS:
        text = read_text(root / rel)
        ok = text is not None and needle in text
        consumers.append({"file": rel, "needle": needle, "role": role, "present": ok})
    negatives: list[dict] = []
    for name, rel, needle, why in NEGATIVE:
        text = read_text(root / rel)
        # 文件不存在时视为"没有该文本"（不因缺文件而误判为违规）
        absent = text is None or needle not in text
        negatives.append({"check": name, "file": rel, "needle": needle, "why": why,
                          "pass": absent, "detail": None if absent else f"禁止出现：{needle!r}"})
    return required, consumers, negatives


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="contain 语义区分机检（v0.2）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--selftest", action="store_true", help="红路径自测")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    required, consumers, negatives = run_checks(REPO)
    failures = [item for item in required if not item["pass"]]
    missing = [item for item in consumers if not item["present"]]
    bad = [item for item in negatives if not item["pass"]]
    result = {
        "schema": "contain-semantics-guard/v3",
        "required": required,
        "consumers": consumers,
        "negatives": negatives,
        "failures": failures,
        "missing_consumers": missing,
        "negative_failures": bad,
        "ok": not failures and not missing and not bad,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in required:
            print(("PASS  " if item["pass"] else "FAIL  ") + f"{item['check']:<26} {item['file']}")
            if not item["pass"]:
                print(f"        {item['detail']}")
        print()
        print(f"消费/定义点：{len(consumers) - len(missing)}/{len(consumers)} 仍在")
        for item in missing:
            print(f"  MISSING  {item['file']} :: {item['needle']!r}（{item['role']}）")
        for item in negatives:
            print(("PASS  " if item["pass"] else "FAIL  ") + f"{item['check']:<26} {item['file']}")
            if not item["pass"]:
                print(f"        {item['detail']}")
        print()
        print("RESULT:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


def _fixture_files() -> dict[str, str]:
    return {
        "src/memoria/ui/static/app/i18n/zh-CN.js": (
            'typeContain: "结构包含",\ncontainNote: "由知识点区间推导，语义未验证",\n'
            'typeContainSemantic: "包含（作者确认）",\ncontainSemanticNote: "作者/人工确认的整体-部分关系",\n'
            'curateBtn: "确认为整体-部分",\n'
        ),
        "src/memoria/ui/static/app/i18n/en.js": (
            'typeContain: "Structural contain",\n'
            'containNote: "Derived from note ranges; semantic containment is NOT verified",\n'
            'typeContainSemantic: "Contain (author-confirmed)",\n'
            'containSemanticNote: "Whole-part relation asserted by the author/curation",\n'
            'curateBtn: "Confirm whole-part",\n'
        ),
        "src/memoria/ui/static/app/js/app.js": (
            'const isSemantic = type === "contain" && edge && edge.contain_kind === "semantic";\n'
            'T("cfg.edge.typeContainSemantic")\n'
            'e.type === "contain"\ncontain_kind === "semantic"\n'
            '-edge-btn-curate\ncall("curate_contain"\ncall("remove_contain_curation"\n'
        ),
        "src/memoria/services/agent/tools/kb.py": "contain_kind=structural\ncontain\n",
        "src/memoria/graph/edge_derivation.py": (
            'def derive_contain_edges():\n"contain_kind": "structural"\n'
            "def validate_contain_curation_overlay():\n"
        ),
        "src/memoria/graph/collector.py": "dedupe_graph_edges\n",
        "src/memoria/graph/edge_types.py": "DERIVE_ONLY_EDGE_TYPES = ()  # contain\n",
        "src/memoria/services/agent/plan.py": "contain\n",
        "src/memoria/ui/static/app/js/graph-engine.js": "expandLinks\n",
        "src/memoria/ui/static/app/js/graph-synthetic.js": "expandLinks\n",
        "docs/design/kg-edge-provenance.schema.json": '"contain_kind"\n',
        "docs/design/kg-ontology-v0.md": "contain_kind\ncuration overlay\n",
        "src/memoria/graph/collector.py": "dedupe_graph_edges\nmerge_contain_curation_overlays\n",
        "src/memoria/services/document.py": "def curate_contain(\nconfirmed_by 不能为空\n",
        "src/memoria/services/agent/tools/kb.py": "contain_kind=structural\ncontain\n",
        "src/memoria/presentation/api/ui.py": "def curate_contain(\n",
    }


def selftest() -> int:
    """红路径：正常夹具全绿；逐项破坏必需文本必须报红；删消费点必须报出。"""
    with tempfile.TemporaryDirectory(prefix="contain-guard-selftest-") as tmp:
        root = Path(tmp)
        for rel, text in _fixture_files().items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        required, consumers, negatives = run_checks(root)
        if (
            any(not item["pass"] for item in required)
            or any(not item["present"] for item in consumers)
            or any(not item["pass"] for item in negatives)
        ):
            print("SELFTEST FAIL: 正常夹具应当全绿")
            return 1

        red_cases = [
            ("src/memoria/ui/static/app/i18n/zh-CN.js", 'typeContain: "结构包含"', 'typeContain: "包含"'),
            ("src/memoria/ui/static/app/i18n/zh-CN.js", 'containNote: "由知识点区间推导，语义未验证"', ""),
            ("src/memoria/ui/static/app/i18n/zh-CN.js", 'typeContainSemantic: "包含（作者确认）"', ""),
            ("src/memoria/ui/static/app/i18n/en.js", 'typeContain: "Structural contain"', 'typeContain: "Contain"'),
            ("src/memoria/ui/static/app/js/app.js", 'edge.contain_kind === "semantic"', ""),
            ("src/memoria/graph/edge_derivation.py", '"contain_kind": "structural"', ""),
            ("src/memoria/services/agent/tools/kb.py", "contain_kind=structural", ""),
            ("docs/design/kg-edge-provenance.schema.json", '"contain_kind"', ""),
            ("docs/design/kg-ontology-v0.md", "contain_kind", ""),
            ("src/memoria/graph/collector.py", "merge_contain_curation_overlays", ""),
            ("src/memoria/services/document.py", "def curate_contain(", ""),
            ("src/memoria/ui/static/app/js/app.js", "-edge-btn-curate", ""),
        ]
        for rel, old, new in red_cases:
            path = root / rel
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace(old, new), encoding="utf-8")
            required_now, _, _ = run_checks(root)
            if all(item["pass"] for item in required_now):
                print(f"SELFTEST FAIL: 破坏 {rel}（{old!r}）后仍全绿")
                return 1
            path.write_text(original, encoding="utf-8")

        (root / "src/memoria/ui/static/app/js/graph-synthetic.js").write_text("nothing\n", encoding="utf-8")
        _, consumers_now, _ = run_checks(root)
        if all(item["present"] for item in consumers_now):
            print("SELFTEST FAIL: 删除消费读取点后仍全绿")
            return 1
        # 负向检查的证红：agent 工具面出现 curate_contain 必须被抓到
        tools = root / "src/memoria/services/agent/tools/kb.py"
        tools.write_text(tools.read_text(encoding="utf-8") + "\ncurate_contain\n", encoding="utf-8")
        _, _, negatives_now = run_checks(root)
        if all(item["pass"] for item in negatives_now):
            print("SELFTEST FAIL: agent 工具面出现 curate_contain 后仍全绿")
            return 1

    print("SELFTEST PASS: 正常夹具全绿；12 个口径被破坏时均报红；删消费点/agent 工具面越界被报出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
