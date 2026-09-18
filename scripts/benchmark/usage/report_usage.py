#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 用量报告：把会话 JSONL 的 `loop/end` 用量聚合成 JSON + MD（**只读**）。

用法（`--kb` 必填）：

    python scripts/benchmark/usage/report_usage.py --kb docs/example/AAA_Vocab --label real-sample
    python scripts/benchmark/usage/report_usage.py --kb <知识库> --session <会话 id>
    python scripts/benchmark/usage/report_usage.py --kb <知识库> --out <目录>

产物（默认落 `scripts/benchmark/usage/results/`）：

- `usage-<label>_<sha>.json`：结构化数据（逐轮 / 按会话 / 汇总 + meta），供后续 A/B；
- `usage-<label>_<sha>.md`：人读报告（总览 / 按会话 / 按轮次 / **口径与限制**）。

口径与**已知限制**（尤其"老会话无 cache 字段 ⇒ 命中率为「未知」而非 0"）见
`services/agent/usage_report.py` 模块 docstring；本脚本**只读**知识库 —— 除 `--out`
目录外不写任何位置（`--out` 落在知识库内会被直接拒绝）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from memoria.services.agent.usage_report import aggregate_usage, usage_stats  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "results"
TOOL_REL = "scripts/benchmark/usage/report_usage.py"
#: MD「按轮次」默认最多列出的行数（完整数据看 JSON）。
DEFAULT_MAX_TURNS = 200


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False
    )
    return proc.stdout.strip()


def _meta(label: str, kb: str, cmd: str) -> dict:
    sha = _git("rev-parse", "--short", "HEAD") or "nogit"
    return {
        "label": label,
        "sha": sha,
        "tree_state": "dirty（含未提交改动）" if _git("status", "--porcelain") else "clean",
        "generated_at": datetime.now(UTC).isoformat(),
        "kb_path": str(Path(kb).resolve()),
        "tool": TOOL_REL,
        "cmd": cmd,
    }


def _fmt_int(value: object) -> str:
    return "未知" if value is None else f"{int(value):,}"  # type: ignore[arg-type]


def _fmt_rate(rate: float | None) -> str:
    return "未知" if rate is None else f"{rate * 100:.1f}%"


def _overview_md(summary: dict) -> str:
    rows = [
        ("会话数", _fmt_int(summary["sessions"])),
        ("轮次", _fmt_int(summary["turns"])),
        ("输入 tokens", _fmt_int(summary["prompt"])),
        ("输出 tokens", _fmt_int(summary["completion"])),
        ("合计 tokens", _fmt_int(summary["total"])),
        ("命中 tokens", _fmt_int(summary["cache_hit"])),
        ("未命中 tokens", _fmt_int(summary["cache_miss"])),
        ("命中率", _fmt_rate(summary["hit_rate"])),
        ("估算轮次", _fmt_int(summary["estimated_turns"])),
        ("cache 未知轮次", _fmt_int(summary["cache_unknown_turns"])),
    ]
    lines = ["| 指标 | 值 |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines)


def _sessions_md(sessions: list[dict]) -> str:
    lines = [
        "| 会话 | 轮次 | 输入 | 输出 | 合计 | 命中 | 未命中 | 命中率 | 估算轮次 | cache 未知 | 备注 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sessions:
        lines.append(
            "| `{sid}` | {turns} | {prompt} | {completion} | {total} | {hit} | {miss} | {rate}"
            " | {est} | {unknown} | {note} |".format(
                sid=row["session_id"],
                turns=_fmt_int(row["turns"]),
                prompt=_fmt_int(row["prompt"]),
                completion=_fmt_int(row["completion"]),
                total=_fmt_int(row["total"]),
                hit=_fmt_int(row["cache_hit"]),
                miss=_fmt_int(row["cache_miss"]),
                rate=_fmt_rate(row["hit_rate"]),
                est=_fmt_int(row["estimated_turns"]),
                unknown=_fmt_int(row["cache_unknown_turns"]),
                note="扫描超上限、仅统计前半段" if row.get("capped") else "",
            )
        )
    return "\n".join(lines)


def _turns_md(turns: list[dict], max_turns: int) -> str:
    shown = turns if max_turns <= 0 else turns[:max_turns]
    lines = [
        "| 会话 | seq | 输入 | 输出 | 合计 | 命中 | 未命中 | 命中率 | 估算 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in shown:
        lines.append(
            "| `{sid}` | {seq} | {prompt} | {completion} | {total} | {hit} | {miss} | {rate} | {est} |".format(
                sid=row["session_id"],
                seq=_fmt_int(row["seq"]),
                prompt=_fmt_int(row["prompt"]),
                completion=_fmt_int(row["completion"]),
                total=_fmt_int(row["total"]),
                hit=_fmt_int(row["cache_hit"]),
                miss=_fmt_int(row["cache_miss"]),
                rate=_fmt_rate(row["hit_rate"]),
                est="是" if row.get("estimated") else "否",
            )
        )
    if max_turns > 0 and len(turns) > max_turns:
        lines.append("")
        lines.append(f"> 仅列出前 {max_turns} 轮（共 {len(turns)} 轮）；完整数据见同名 JSON。")
    return "\n".join(lines)


def _markdown(report: dict, meta: dict, max_turns: int) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            f"# Agent 用量报告 — {meta['label']}",
            "",
            f"> 生成时间（UTC）：`{meta['generated_at']}` ；来源 commit：`{meta['sha']}`"
            f"（{meta['tree_state']}）",
            f"> 知识库：`{meta['kb_path']}` ；脚本：`python {meta['tool']} --kb … --label {meta['label']}`",
            "",
            "## 1. 总览",
            "",
            _overview_md(summary),
            "",
            "## 2. 按会话",
            "",
            _sessions_md(report["sessions"]) if report["sessions"] else "（无含用量的会话）",
            "",
            "## 3. 按轮次",
            "",
            _turns_md(report["turns"], max_turns) if report["turns"] else "（无轮次）",
            "",
            "## 4. 口径与限制",
            "",
            "- **一轮** = 会话文件里的一条 `loop/end` 事件（一次提问里全部模型步数之和）；"
            "字段即 `loop/end.usage`。",
            "- **命中 / 未命中** = 端点上报的 `cache_read_tokens` / `cache_miss_tokens`"
            "（DeepSeek 顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`；"
            "OpenAI 形态的 `prompt_tokens_details.cached_tokens` 只给命中量，未命中量按"
            " `prompt - 命中` 补出）。",
            "- **命中率未知 ≠ 0**：本次改动之前落盘的**老会话**没有 cache 字段，其轮次计入"
            " `cache 未知轮次`（`cache_unknown_turns`），且**不参与**命中率分母 ⇒ 命中率显示"
            "「未知」而不是 0%。",
            "- **估算**（`estimated`）：端点**完全没给** usage、由启发式估算得出；"
            "只有「没给 usage」才置真，端点给了 usage 但缺 cache 字段不算估算。",
            "- 会话文件**未记录模型名**，故逐轮行不含 `model`。",
            "- 单份会话最多扫描 2 MiB（`SCAN_MAX_BYTES`）；超限的会话在「备注」标注"
            "「扫描超上限、仅统计前半段」（`capped:true`）。",
            "- **本脚本只读知识库**：只读 `<kb>/.memoria/agent/sessions/*.jsonl`，"
            "除 `--out` 目录外不写任何位置。",
            f"- 来源：commit `{meta['sha']}`、生成于 `{meta['generated_at']}`、命令 `{meta['cmd']}`。",
            "",
        ]
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent 用量报告（会话 loop/end 用量聚合，只读）")
    parser.add_argument("--kb", required=True, help="知识库根目录（只读）")
    parser.add_argument("--label", default="usage", help="产物标签（文件名一部分，默认 usage）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出目录（默认 {DEFAULT_OUT}）")
    parser.add_argument("--session", default="", help="只统计该会话 id（默认统计全库会话）")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"MD「按轮次」最多列出多少行（默认 {DEFAULT_MAX_TURNS}；<=0 表示不限）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    kb = Path(args.kb).resolve()
    if not kb.is_dir():
        sys.stderr.write(f"[error] 知识库目录不存在：{kb}\n")
        return 2
    out = Path(args.out).resolve()
    if out == kb or kb in out.parents:
        sys.stderr.write(f"[error] 拒绝把产物写进知识库（--out 落在 KB 内）：{out}\n")
        return 2

    session_id = (args.session or "").strip() or None
    report = usage_stats(str(kb), session_id)
    cmd = " ".join(["python", TOOL_REL, "--kb", str(kb), "--label", args.label])
    meta = _meta(args.label, str(kb), cmd)
    payload = {"meta": meta, **report}

    out.mkdir(parents=True, exist_ok=True)
    stem = f"usage-{args.label}_{meta['sha']}"
    json_path = out / f"{stem}.json"
    md_path = out / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report, meta, args.max_turns), encoding="utf-8")

    summary = report["summary"]
    print(f"[ok] 会话={summary['sessions']} 轮次={summary['turns']} 合计={summary['total']} tokens"
          f" 命中率={_fmt_rate(summary['hit_rate'])} cache未知轮次={summary['cache_unknown_turns']}")
    print(f"[out] {json_path}")
    print(f"[out] {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
