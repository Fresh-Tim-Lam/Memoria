#!/usr/bin/env python3
"""contain 语义区分的机检（task-287 方案 A）：结构包含 ≠ 语义 contain。

背景（人，2026-11-02）：「文本上的 contain 不一定真实具有 contain 的语义，所以有必要做一些
区分，别让程序自动一视同仁处理为 contain 边。」

事实：`derive_contain_edges()` 只按知识点 **区间几何包含** 生成 `type="contain"`，
带 `derived_by="system_range"`；ontology 里 contain 的语义是"整体-部分"，于是任何只看
`type` 的消费者都会把它误读成作者断言。实测 14 个消费读取点无一处检查 `derived_by`。

方案 A（不改 schema、不改数据）：在所有面向人的文案上把 contain 标成**结构包含候选、语义未验证**，
并用本脚本把这份口径钉住，防止文案被改回去：
  1. i18n（zh/en）的边类型标签与说明；
  2. KP 边页签 badge 的 tooltip；
  3. agent 的 `upsert_edge` 提示词；
  4. 已知消费读取点清单仍在（清单本身是审计对象，删除必须同步更新本文件并说明）。

用法：
    python scripts/agent/contain_semantics_guard.py            # 机检（FAIL → exit 1）
    python scripts/agent/contain_semantics_guard.py --selftest # 红路径自测（必须能报红）
    python scripts/agent/contain_semantics_guard.py --json     # 机器可读输出

边界：只读源码；不写任何文件（--selftest 只在临时目录建夹具）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: 必须存在的口径文本（(检查名, 相对路径, 必须出现的片段)）。
REQUIRED = [
    (
        "i18n-zh-label",
        "src/memoria/ui/static/app/i18n/zh-CN.js",
        'typeContain: "结构包含"',
    ),
    (
        "i18n-zh-note",
        "src/memoria/ui/static/app/i18n/zh-CN.js",
        'containNote: "由知识点区间推导，语义未验证"',
    ),
    (
        "i18n-en-label",
        "src/memoria/ui/static/app/i18n/en.js",
        'typeContain: "Structural contain"',
    ),
    (
        "i18n-en-note",
        "src/memoria/ui/static/app/i18n/en.js",
        'containNote: "Derived from note ranges; semantic containment is NOT verified"',
    ),
    (
        "badge-tooltip",
        "src/memoria/ui/static/app/js/app.js",
        'const note = type === "contain" ? T("cfg.edge.containNote") : "";',
    ),
    (
        "agent-prompt-caveat",
        "src/memoria/services/agent/tools/kb.py",
        "结构包含候选，语义未验证",
    ),
]

#: 已知的 contain 消费读取点（研究证据 contain-evidence.json 的 14 条）。
#: 本表的作用是"删改前必须显式面对"：读取点变化时同步更新清单，不能静默消失。
CONSUMERS = [
    ("src/memoria/graph/edge_derivation.py", "derive_contain_edges", "唯一写入者：按 KP range 几何包含生成 type=contain"),
    ("src/memoria/graph/collector.py", "dedupe_graph_edges", "拼装 contain+link+sidecar 后 dedupe"),
    ("src/memoria/graph/edge_types.py", "DERIVE_ONLY_EDGE_TYPES", "contain 属派生专用（禁手标）"),
    ("src/memoria/services/agent/plan.py", "contain", "agent 边类型允许集合"),
    ("src/memoria/services/agent/tools/kb.py", "结构包含候选", "agent 工具文案（已加语义未验证）"),
    ("src/memoria/ui/static/app/js/graph-engine.js", "expandLinks", "主图渲染只读 type/source/targets/relevance"),
    ("src/memoria/ui/static/app/js/app.js", 'e.type === "contain"', "KP 边页签按 type 判断可抑制派生边"),
    ("src/memoria/ui/static/app/js/app.js", 'T("cfg.edge.containNote")', "badge tooltip 的语义口径"),
    ("src/memoria/ui/static/app/js/graph-synthetic.js", "expandLinks", "合成图同口径"),
    ("src/memoria/ui/static/app/i18n/zh-CN.js", "结构包含", "中文标签"),
    ("src/memoria/ui/static/app/i18n/zh-CN.js", "语义未验证", "中文说明"),
    ("src/memoria/ui/static/app/i18n/en.js", "Structural contain", "英文标签"),
    ("src/memoria/ui/static/app/i18n/en.js", "NOT verified", "英文说明"),
    ("docs/design/kg-edge-provenance.schema.json", "derived_by", "字段契约（schema 未规定 contain 语义）"),
]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def run_checks(root: Path) -> tuple[list[dict], list[dict]]:
    """返回 (required 结果, consumers 结果)。"""
    required: list[dict] = []
    for name, rel, needle in REQUIRED:
        text = read_text(root / rel)
        ok = text is not None and needle in text
        required.append({"check": name, "file": rel, "needle": needle, "pass": ok,
                         "detail": None if ok else f"缺少必需文本：{needle!r}"})
    consumers: list[dict] = []
    for rel, needle, role in CONSUMERS:
        text = read_text(root / rel)
        ok = text is not None and needle in text
        consumers.append({"file": rel, "needle": needle, "role": role, "present": ok})
    return required, consumers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="contain 语义区分机检（方案 A）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--selftest", action="store_true", help="红路径自测")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    required, consumers = run_checks(REPO)
    failures = [item for item in required if not item["pass"]]
    missing_consumers = [item for item in consumers if not item["present"]]
    result = {
        "schema": "contain-semantics-guard/v1",
        "required": required,
        "consumers": consumers,
        "failures": failures,
        "missing_consumers": missing_consumers,
        "ok": not failures and not missing_consumers,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in required:
            print(("PASS  " if item["pass"] else "FAIL  ") + f"{item['check']:<22} {item['file']}")
            if not item["pass"]:
                print(f"        {item['detail']}")
        print()
        print(f"消费读取点：{len(consumers) - len(missing_consumers)}/{len(consumers)} 仍在")
        for item in missing_consumers:
            print(f"  MISSING  {item['file']} :: {item['needle']!r}（{item['role']}）")
        print()
        print("RESULT:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


def selftest() -> int:
    """红路径自测：正常夹具全绿；逐项破坏后对应检查必须变红。"""
    with tempfile.TemporaryDirectory(prefix="contain-guard-selftest-") as tmp:
        root = Path(tmp)
        # 建立"全部通过"的最小夹具
        files = {
            "src/memoria/ui/static/app/i18n/zh-CN.js": 'typeContain: "结构包含",\ncontainNote: "由知识点区间推导，语义未验证",\n',
            "src/memoria/ui/static/app/i18n/en.js": 'typeContain: "Structural contain",\ncontainNote: "Derived from note ranges; semantic containment is NOT verified",\n',
            "src/memoria/ui/static/app/js/app.js": 'const note = type === "contain" ? T("cfg.edge.containNote") : "";\ne.type === "contain"\n',
            "src/memoria/services/agent/tools/kb.py": "结构包含候选，语义未验证\ncontain\n",
            "src/memoria/graph/edge_derivation.py": "def derive_contain_edges():\n",
            "src/memoria/graph/collector.py": "dedupe_graph_edges\n",
            "src/memoria/graph/edge_types.py": "DERIVE_ONLY_EDGE_TYPES = ()  # contain\n",
            "src/memoria/services/agent/plan.py": "contain\n",
            "src/memoria/ui/static/app/js/graph-engine.js": "expandLinks\n",
            "src/memoria/ui/static/app/js/graph-synthetic.js": "expandLinks\n",
            "docs/design/kg-edge-provenance.schema.json": '"derived_by"\n',
        }
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        required, consumers = run_checks(root)
        if any(not item["pass"] for item in required) or any(not item["present"] for item in consumers):
            print("SELFTEST FAIL: 正常夹具应当全绿")
            return 1

        red_cases = [
            ("src/memoria/ui/static/app/i18n/zh-CN.js", 'typeContain: "结构包含"', 'typeContain: "包含"'),
            ("src/memoria/ui/static/app/i18n/zh-CN.js", 'containNote: "由知识点区间推导，语义未验证"', ''),
            ("src/memoria/ui/static/app/i18n/en.js", 'typeContain: "Structural contain"', 'typeContain: "Contain"'),
            ("src/memoria/ui/static/app/i18n/en.js", 'containNote: "Derived from note ranges; semantic containment is NOT verified"', ''),
            ("src/memoria/ui/static/app/js/app.js", 'const note = type === "contain" ? T("cfg.edge.containNote") : "";', ''),
            ("src/memoria/services/agent/tools/kb.py", "结构包含候选，语义未验证", ""),
        ]
        for rel, old, new in red_cases:
            path = root / rel
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace(old, new), encoding="utf-8")
            required_now, _ = run_checks(root)
            if all(item["pass"] for item in required_now):
                print(f"SELFTEST FAIL: 破坏 {rel} 后仍全绿（检查无判别力）")
                return 1
            path.write_text(original, encoding="utf-8")

        # 删除一个消费读取点后必须被报出来
        (root / "src/memoria/ui/static/app/js/graph-synthetic.js").write_text("nothing\n", encoding="utf-8")
        _, consumers_now = run_checks(root)
        if all(item["present"] for item in consumers_now):
            print("SELFTEST FAIL: 删除消费读取点后仍全绿")
            return 1

    print("SELFTEST PASS: 正常夹具全绿；6 个口径被破坏时均报红；删消费点被报出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
