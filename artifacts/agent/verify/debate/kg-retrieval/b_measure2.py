# -*- coding: utf-8 -*-
"""B 方补充测量：KP 切片实际字符量 / 文件级 description / 三级索引体积估算。"""
import io
import json
import os
import statistics

import yaml

COURSE = r"D:\AAA_Courses\数字通信原理"
OUT = r"D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval"


def kp_excerpt_chars(kb_root):
    rows = []
    file_desc = []
    sc_root = os.path.join(kb_root, ".memoria", "sidecars")
    for dp, _, fs in os.walk(sc_root):
        for f in fs:
            if not f.endswith(".memoria.yaml"):
                continue
            p = os.path.join(dp, f)
            doc = yaml.safe_load(io.open(p, encoding="utf-8")) or {}
            rel = str(doc.get("file") or "")
            full = os.path.join(kb_root, rel)
            if not os.path.isfile(full):
                continue
            lines = io.open(full, encoding="utf-8", errors="ignore").read().splitlines()
            file_desc.append({"file": rel, "file_desc_chars": len(str(doc.get("description") or "").strip())})
            for kp in doc.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                rng = kp.get("range") or {}
                s = int(((rng.get("start") or {}).get("line_hint") or 0))
                e = int(((rng.get("end") or {}).get("line_hint") or 0))
                if not (s and e and e >= s):
                    continue
                text = "\n".join(lines[s - 1:e])
                rows.append({
                    "file": rel, "id": str(kp.get("id") or ""), "name": str(kp.get("name") or ""),
                    "start": s, "end": e, "lines": e - s + 1, "chars": len(text),
                    "desc_chars": len(str(kp.get("description") or "").strip()),
                })
    return rows, file_desc


def stats(vals):
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    return {"n": len(s), "min": s[0], "p50": statistics.median(s),
            "p90": s[int(len(s) * 0.9)], "p99": s[int(len(s) * 0.99)], "max": s[-1]}


rows, file_desc = kp_excerpt_chars(COURSE)
chars = [r["chars"] for r in rows]
lines = [r["lines"] for r in rows]
print("KP excerpts:", len(rows))
print("excerpt chars:", json.dumps(stats(chars), ensure_ascii=False))
print("excerpt lines:", json.dumps(stats(lines), ensure_ascii=False))
over20k = [r for r in rows if r["chars"] > 20000]
print("KP with excerpt > 20,000 chars (read_document cap):", len(over20k))
for r in over20k[:8]:
    print("   ", r["file"], r["id"], r["name"], "chars", r["chars"], "lines", r["lines"], "desc", r["desc_chars"])

print("\nfile-level descriptions:", len(file_desc), "non-empty:", sum(1 for f in file_desc if f["file_desc_chars"]))
print("file desc chars:", json.dumps(stats([f["file_desc_chars"] for f in file_desc if f["file_desc_chars"]]), ensure_ascii=False))
for f in file_desc:
    if f["file_desc_chars"]:
        print("   ", f["file"], f["file_desc_chars"])

# 三级索引体积估算（数字通信原理）
names = sum(len(r["name"]) for r in rows)
desc = sum(r["desc_chars"] for r in rows)
print("\n=== 索引体积估算（中文按 1 char≈0.7 token 下界 / 1 char≈1 token 上界）===")
print("L1 names-only chars:", names, "tokens:", round(names * 0.7), "-", names)
print("L2 +KP desc chars:", names + desc, "tokens:", round((names + desc) * 0.7), "-", names + desc)
print("L3 +首行 preview(每 KP 40 chars) chars:", names + desc + 40 * len(rows),
      "tokens:", round((names + desc + 40 * len(rows)) * 0.7), "-", names + desc + 40 * len(rows))
print("每轮 prompt 基线 225,553 tokens；单次工具结果上限 20,000 chars（read_document）")

# 抽样：名字像不像"学习单元"（随机 12 条跨文件）
import random
random.seed(7)
print("\n=== 抽样 KP（name / lines / chars / desc）===")
for r in random.sample(rows, min(12, len(rows))):
    print(f"  {r['file']} | {r['id']} | {r['name']} | L{r['start']}-{r['end']} ({r['lines']}行/{r['chars']}字) | desc={r['desc_chars']}")

json.dump({"kp_excerpts": rows, "file_desc": file_desc},
          io.open(os.path.join(OUT, "b-measure-kp.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\nwritten b-measure-kp.json")
