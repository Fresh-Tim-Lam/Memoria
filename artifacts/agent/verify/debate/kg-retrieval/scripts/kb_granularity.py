"""Phase 1 / C 线：真实教材知识库的 KP 粒度与标题结构实测（只读）。

对象（只读，不修改任何文件）：
  D:\\AAA_Courses\\数字通信原理  （58 md / 5.27MB，12 sidecar，ACCOUNT 同一库）

产出：
  · 每个 md 的字符数/行数、sidecar KP 数
  · 每个 KP 的覆盖字符数（start_line→end_line）与估算 token；p50/p90/max
  · 最粗的 KP 排行榜（>5k token 的"巨型 KP"）
  · 标题层级分布（# ## ### ####），判断"KP vs 小节"粒度
  · 用户真实提问（19 条）与 KP/章节的粗略对应（人工可复核）

用法：
  python artifacts/agent/verify/debate/kg-retrieval/scripts/kb_granularity.py --json out.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

KB = r"D:\AAA_Courses\数字通信原理"
SIDECAR_DIR = os.path.join(KB, ".memoria", "sidecars")
CHARS_PER_TOKEN = 3.5


def read_text(path: str) -> str:
    return io.open(path, encoding="utf-8", errors="replace").read()


def find_md_for_sidecar(sidecar_path: str, sidecar_text: str) -> str | None:
    """sidecar 里通常有 source/file 字段；退化为同名约定查找。"""
    m = re.search(r"^(?:source|file|md|target):\s*[\"']?([^\n\"']+)", sidecar_text, re.M)
    if m:
        cand = m.group(1).strip()
        for probe in (os.path.join(KB, cand), os.path.join(KB, "教材", cand), os.path.join(KB, "教材", os.path.basename(cand))):
            if os.path.isfile(probe):
                return probe
    # 同名：x.memoria.yaml -> 在 KB 下递归找同 stem 的 md
    stem = os.path.basename(sidecar_path).replace(".memoria.yaml", "")
    for root, _dirs, files in os.walk(KB):
        if ".memoria" in root:
            continue
        for f in files:
            if f.lower() == stem.lower() + ".md":
                return os.path.join(root, f)
    return None


def parse_kps(sidecar_text: str) -> list[dict]:
    """极简 YAML 行解析：- id: / name: / range: {start_line,end_line} / snippet。"""
    rows: list[dict] = []
    cur: dict = {}
    in_kp = False
    for raw in sidecar_text.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s{0,4}- id:\s*", line):
            if cur:
                rows.append(cur)
            cur = {"id": re.sub(r"^\s{0,4}- id:\s*", "", line).strip().strip("\"'")}
            in_kp = True
        elif in_kp and re.match(r"^\s+name:\s*", line):
            cur["name"] = re.sub(r"^\s+name:\s*", "", line).strip().strip("\"'")
        elif in_kp and re.match(r"^\s+range:\s*", line):
            body = re.sub(r"^\s+range:\s*", "", line).strip()
            m = re.match(r"\{?\s*start_line:\s*(\d+)\s*,\s*end_line:\s*(\d+)", body)
            if m:
                cur["start_line"] = int(m.group(1))
                cur["end_line"] = int(m.group(2))
        elif in_kp and re.match(r"^\s+start_line:\s*", line):
            cur.setdefault("_pending", {})["start_line"] = int(re.sub(r"^\s+start_line:\s*", "", line).strip())
        elif in_kp and re.match(r"^\s+end_line:\s*", line):
            cur.setdefault("_pending", {})["end_line"] = int(re.sub(r"^\s+end_line:\s*", "", line).strip())
        elif in_kp and re.match(r"^\s+(start|end):\s*$", line):
            # 真实 sidecar 形态：range.start.line_hint / range.end.line_hint
            cur["_block"] = re.sub(r"^\s+(start|end):\s*$", r"\1", line)
        elif in_kp and re.match(r"^\s+line_hint:\s*", line):
            hint = int(re.sub(r"^\s+line_hint:\s*", "", line).strip())
            side = short = cur.get("_block")
            if side == "start":
                cur["start_line"] = hint
            elif side == "end":
                cur["end_line"] = hint
        elif in_kp and re.match(r"^\s+description:\s*", line):
            cur["description"] = re.sub(r"^\s+description:\s*", "", line).strip()
        elif in_kp and line.strip() and not line.startswith((" ", "\t")):
            in_kp = False
    if cur:
        rows.append(cur)
    for row in rows:
        pend = row.pop("_pending", {})
        row.setdefault("start_line", pend.get("start_line"))
        row.setdefault("end_line", pend.get("end_line"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    md_files: list[str] = []
    for root, _dirs, files in os.walk(KB):
        if ".memoria" in root:
            continue
        for f in files:
            if f.endswith(".md"):
                md_files.append(os.path.join(root, f))
    md_files.sort()

    md_stats: list[dict] = []
    all_kps: list[dict] = []
    heading_counts: dict[str, int] = {}
    for md_path in md_files:
        text = read_text(md_path)
        lines = text.splitlines()
        rel = os.path.relpath(md_path, KB).replace("\\", "/")
        hs = {"h1": 0, "h2": 0, "h3": 0, "h4": 0}
        for line in lines:
            m = re.match(r"^(#{1,4})\s", line)
            if m:
                hs["h%d" % len(m.group(1))] += 1
        for k, v in hs.items():
            heading_counts[k] = heading_counts.get(k, 0) + v
        md_stats.append({"file": rel, "chars": len(text), "lines": len(lines), "headings": hs})

    sidecar_paths: list[str] = []
    if os.path.isdir(SIDECAR_DIR):
        for root, _dirs, files in os.walk(SIDECAR_DIR):
            for f in files:
                if f.endswith(".memoria.yaml"):
                    sidecar_paths.append(os.path.join(root, f))
    sidecar_rows: list[dict] = []
    for sp in sorted(sidecar_paths):
        st = read_text(sp)
        md_path = find_md_for_sidecar(sp, st)
        kps = parse_kps(st)
        if not md_path:
            sidecar_rows.append({"sidecar": os.path.basename(sp), "md": None, "kp_count": len(kps)})
            continue
        body_lines = read_text(md_path).splitlines()
        rel_md = os.path.relpath(md_path, KB).replace("\\", "/")
        for kp in kps:
            start = kp.get("start_line") or 1
            end = kp.get("end_line") or start
            chunk = "\n".join(body_lines[max(start - 1, 0) : end])
            kp["file"] = rel_md
            kp["chars"] = len(chunk)
            kp["tokens"] = round(len(chunk) / CHARS_PER_TOKEN, 1)
            all_kps.append(kp)
        sidecar_rows.append({"sidecar": os.path.basename(sp), "md": rel_md, "kp_count": len(kps)})

    all_kps.sort(key=lambda x: -(x.get("chars") or 0))
    sizes = sorted(k.get("chars") or 0 for k in all_kps)
    tokens = sorted(k.get("tokens") or 0 for k in all_kps)

    def pct(vals: list[float], p: float) -> float:
        if not vals:
            return 0
        i = min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))
        return round(vals[i], 1)

    report = {
        "kb": KB,
        "md_count": len(md_stats),
        "md_total_chars": sum(m["chars"] for m in md_stats),
        "md_total_tokens": round(sum(m["chars"] for m in md_stats) / CHARS_PER_TOKEN, 1),
        "sidecars": len(sidecar_rows),
        "sidecar_rows": sidecar_rows,
        "kp_count": len(all_kps),
        "heading_counts": heading_counts,
        "kp_chars": {
            "p50": pct(sizes, 50),
            "p90": pct(sizes, 90),
            "p99": pct(sizes, 99),
            "max": max(sizes, default=0),
            "mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        },
        "kp_tokens": {
            "p50": pct(tokens, 50),
            "p90": pct(tokens, 90),
            "p99": pct(tokens, 99),
            "max": max(tokens, default=0),
            "mean": round(sum(tokens) / len(tokens), 1) if tokens else 0,
        },
        "coarse_kps": [
            {"id": k.get("id"), "name": k.get("name"), "file": k.get("file"), "chars": k.get("chars"), "tokens": k.get("tokens")}
            for k in all_kps[:15]
        ],
        "fine_kps": [
            {"id": k.get("id"), "name": k.get("name"), "file": k.get("file"), "chars": k.get("chars"), "tokens": k.get("tokens")}
            for k in all_kps[-10:]
        ],
        "chapter3": next((m for m in md_stats if "03_第3章" in m["file"]), None),
        "chapter3_kps": [
            {"id": k.get("id"), "name": k.get("name"), "chars": k.get("chars"), "tokens": k.get("tokens")}
            for k in all_kps
            if "03_第3章" in (k.get("file") or "")
        ],
        "largest_files": sorted(md_stats, key=lambda m: -m["chars"])[:8],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
