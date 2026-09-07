#!/usr/bin/env python3
"""生成官方展示样例库 examples/ 的 sidecar（links 与 KP range 行号自动校准）。

背景：examples/ 正文链接使用 `[[kp-id|显示文本]]` 形式。图谱链接审计
(src/memoria/graph/link_audit.py) 以「正文 target_id == sidecar links[].anchor_text」
且使用「body 行号（去 frontmatter）」作为坐标。本脚本与审计共用
strip_frontmatter / scan_wikilinks，保证坐标与锚文本完全一致。

用法（仓库根）：
    python scripts/gen_example_showcase_sidecars.py
然后校验：
    python -m memoria.cli.main validate examples
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from memoria.services.link_resolver import scan_wikilinks  # noqa: E402
from memoria.storage.markdown import strip_frontmatter  # noqa: E402

KB = ROOT / "examples"
SIDECAR_DIR = KB / ".memoria" / "sidecars"
SNIPPET_MAX = 80

# 语义为「扩展/细化」的目标 id：指向它们的链接生成 edge_type: extend，
# 其余一律 reference（图谱三类边：contain 由标题层级自动生成，不入侧车）。
EXTEND_TARGETS = frozenset(
    {
        "random-forest",
        "gbdt",
        "kmeans",
        "hierarchical",
        "rnn",
        "transformer",
        "rl-policy",
    }
)


def body_lines(md_path: Path) -> list[str]:
    body, _ = strip_frontmatter(md_path.read_text(encoding="utf-8"))
    return body.splitlines()


def find_snippet_line(lines: list[str], snippet: str, *, from_line: int = 1) -> int:
    """在 body 行中定位 snippet（行内子串包含，同 locator 语义），1-based。"""
    needle = (snippet or "").strip()[:SNIPPET_MAX]
    if not needle:
        raise ValueError("空 snippet")
    for i, line in enumerate(lines, start=1):
        if i < from_line:
            continue
        if needle in line.strip():
            return i
    raise ValueError(f"snippet 未找到: {snippet!r}")


def load_sidecars() -> dict[str, dict]:
    """载入现有 sidecar（保留 KP 的 name/tags/aliases 定义）。"""
    out: dict[str, dict] = {}
    for f in SIDECAR_DIR.glob("*.memoria.yaml"):
        out[f.stem.removesuffix(".memoria")] = yaml.safe_load(
            f.read_text(encoding="utf-8")
        ) or {}
    return out


def global_kp_ids(existing: dict[str, dict]) -> set[str]:
    ids: set[str] = set()
    for sc in existing.values():
        for kp in sc.get("knowledge_points") or []:
            if isinstance(kp, dict) and kp.get("id"):
                ids.add(str(kp["id"]))
    return ids


def main() -> None:
    existing = load_sidecars()
    known_ids = global_kp_ids(existing)

    md_files = sorted(KB.glob("*.md"))
    for md in md_files:
        stem = md.stem
        lines = body_lines(md)
        old = existing.get(stem, {})
        kps: list[dict] = []
        for kp in old.get("knowledge_points") or []:
            if not isinstance(kp, dict) or not kp.get("id"):
                continue
            rng = kp.get("range") or {}
            start = rng.get("start") or {}
            end = rng.get("end") or {}
            s_snippet = (start.get("snippet") or "").strip()
            e_snippet = (end.get("snippet") or "").strip()
            s_line = find_snippet_line(lines, s_snippet)
            e_line = find_snippet_line(lines, e_snippet, from_line=s_line)
            kps.append(
                {
                    "id": kp["id"],
                    **({"name": kp["name"]} if kp.get("name") else {}),
                    **({"aliases": kp["aliases"]} if kp.get("aliases") else {}),
                    **({"tags": kp["tags"]} if kp.get("tags") else {}),
                    "range": {
                        "start": {"snippet": s_snippet[:SNIPPET_MAX], "line_hint": s_line},
                        "end": {"snippet": e_snippet[:SNIPPET_MAX], "line_hint": e_line},
                    },
                }
            )

        # KP 区间（闭区间，body 行）—— 定位每个 wikilink 所属源 KP
        ranges: list[tuple[str, int, int]] = []
        for kp in kps:
            rng = kp["range"]
            ranges.append(
                (str(kp["id"]), int(rng["start"]["line_hint"]), int(rng["end"]["line_hint"]))
            )

        # name/alias -> id 解析（正文 `[[名字]]` 形式；id 形式直接命中）
        def resolve(raw: str) -> list[str]:
            raw = raw.strip()
            if raw in known_ids:
                return [raw]
            hits = []
            for sc in existing.values():
                for kp in sc.get("knowledge_points") or []:
                    if not isinstance(kp, dict):
                        continue
                    names = [kp.get("name") or "", *[a for a in (kp.get("aliases") or []) if a]]
                    if raw in names:
                        hits.append(str(kp["id"]))
            return hits

        links_by_key: dict[tuple, dict] = {}
        for wl in scan_wikilinks("\n".join(lines)):
            tid = (wl.get("target_id") or "").strip()
            if not tid or tid.startswith("\\"):
                continue  # 样式命令（[[\…]]）跳过
            line = 1 + "\n".join(lines)[: wl["start"]].count("\n")
            src = next((kid for kid, s, e in ranges if s <= line <= e), None)
            if src is None:
                continue  # 不在任何 KP 区间（如 README）
            targets = resolve(tid)
            if not targets:
                continue  # 悬空虚链（broken 演示，置于 README 等无 KP 页面）不建边
            key = (tid, tuple(targets))
            entry = links_by_key.setdefault(
                key,
                {
                    "anchor_text": tid,
                    "targets": list(targets),
                    "edge_type": "extend" if targets and targets[0] in EXTEND_TARGETS else "reference",
                    "instances": [],
                },
            )
            entry["instances"].append({"line": line})

        links = []
        for entry in links_by_key.values():
            inst = sorted(set(i["line"] for i in entry["instances"]))
            entry["instances"] = [{"line": n} for n in inst]
            # source_id：首个实例行所在 KP（便于阅读，审计不依赖它）
            first = entry["instances"][0]["line"]
            src = next((kid for kid, s, e in ranges if s <= first <= e), None)
            if src is not None:
                entry["source_id"] = src
            links.append(entry)
        links.sort(key=lambda l: l["instances"][0]["line"])

        out = {"schema_version": 1, "file": md.name, "knowledge_points": kps, "links": links}
        SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
        dest = SIDECAR_DIR / f"{stem}.memoria.yaml"
        dest.write_text(
            yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=88),
            encoding="utf-8",
        )
        print(f"[gen] {md.name}: {len(kps)} KP, {len(links)} links")


if __name__ == "__main__":
    main()
