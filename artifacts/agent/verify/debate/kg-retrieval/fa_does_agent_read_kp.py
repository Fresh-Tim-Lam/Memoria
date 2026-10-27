"""F-A 证伪探针：agent 实际读不读 KP range？（task-191 addendum ①）

## 要回答的问题（Lead 定的判据）

> F-A：若能证明 agent **实际从不读 KP range**（只读整篇），
>      则锚点缺陷降级为"用户体验问题"而非"检索问题"。

## 方法

读**真实会话日志**（不造数据）：
`D:\\AAA_Courses\\数字通信原理\\.memoria\\agent\\sessions\\session-20261027T011706Z-0cb419b6.jsonl`

统计：
  1. 所有 tool/call 的工具名分布
  2. 哪些工具**会读取 KP range**（read_kp / 按 kp_id 读）
  3. 哪些工具**只读整篇**（read_document / section）
  4. 读到的内容体量（判断"读整篇"的代价）

## 关键区分（这是本探针的核心）

- `read_document` / `section` / `snippet` **不依赖 KP range**（按文件/小节/行读）
- 只有**按 kp 定位**的调用才依赖 R4 的锚点

用法：python .../fa_does_agent_read_kp.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

SESSION = Path(
    r"D:\AAA_Courses\数字通信原理\.memoria\agent\sessions"
    r"\session-20261027T011706Z-0cb419b6.jsonl"
)

#: 依赖 KP range 锚点的工具（按 kp 定位）
ANCHOR_DEPENDENT = {"read_kp", "kp_read", "read_knowledge_point"}

#: 不依赖 KP range 的读取工具
NON_ANCHOR_READ = {"read_document", "section", "snippet", "outline", "search_kb", "grep", "glob"}


def main() -> int:
    if not SESSION.is_file():
        print(f"[SKIP] 会话文件不存在：{SESSION}")
        return 0

    events = []
    for line in SESSION.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    calls = [e for e in events if (e.get("type") or e.get("kind")) == "tool/call"]

    name_counter: Counter[str] = Counter()
    arg_counter: Counter[str] = Counter()
    anchor_dependent = 0
    non_anchor_reads = 0
    other = 0

    for c in calls:
        # 真实结构：{"type":"tool/call","data":{"id":..,"name":"search_kb","arguments":"{json}"}}
        data = c.get("data") or c.get("payload") or {}
        name = ""
        for key in ("name", "tool", "tool_name"):
            if isinstance(data.get(key), str):
                name = data[key]
                break
        name = name or "<?>"
        name_counter[name] += 1

        raw_args = data.get("arguments")
        args: dict = {}
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        for k in args:
            arg_counter[k] += 1

        if name in ANCHOR_DEPENDENT:
            anchor_dependent += 1
        elif name in NON_ANCHOR_READ:
            non_anchor_reads += 1
        else:
            other += 1

    print("=== F-A：agent 实际读不读 KP range ===")
    print(f"会话：{SESSION.name}")
    print(f"tool/call 总数：{len(calls)}")
    print()
    print("工具调用分布（全量）：")
    for name, n in name_counter.most_common():
        tag = ""
        if name in ANCHOR_DEPENDENT:
            tag = "  ← 依赖 KP 锚点"
        elif name in NON_ANCHOR_READ:
            tag = "  （不依赖 KP 锚点）"
        print(f"  {name:<24} {n:>4}{tag}")

    print()
    print(f"依赖 KP 锚点的调用：{anchor_dependent}")
    print(f"不依赖锚点的读取：{non_anchor_reads}")
    print(f"其它（写入/命令等）：{other}")
    print()
    print("出现过的参数名（看有没有按 kp_id 读的迹象）：")
    for k, n in arg_counter.most_common(12):
        print(f"  {k:<20} {n}")
    print()

    verdict = "从不读 KP" if anchor_dependent == 0 else f"读过 KP（{anchor_dependent} 次）"
    print(f"⇒ 结论：agent {verdict}")

    out = Path(__file__).resolve().parent / "fa-does-agent-read-kp.json"
    out.write_text(
        json.dumps(
            {
                "session": str(SESSION),
                "total_tool_calls": len(calls),
                "tool_distribution": dict(name_counter),
                "anchor_dependent_calls": anchor_dependent,
                "non_anchor_reads": non_anchor_reads,
                "verdict": verdict,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
