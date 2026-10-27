# -*- coding: utf-8 -*-
"""B 方补充：KP 名称自足性 / 学习单元尺寸分布 / 索引体积（基于 b-measure-kp.json）。"""
import io
import json
import re

P = r"D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\b-measure-kp.json"
rows = json.load(io.open(P, encoding="utf-8"))["kp_excerpts"]
n = len(rows)

# 1) 名称自足性：名字是否能独立判断"这条讲什么"
def is_self_contained(name: str) -> bool:
    s = name.strip()
    if not s or len(s) <= 1:
        return False
    # 纯编号/占位/目录/习题/例题/小结类（脱离正文无法判断是否相关）
    if re.match(r"^[\(（]?\d+[\)）\.、]?\s*$", s):
        return False
    if re.match(r"^[\(（]?\d+[\)）\.、]\s*", s) and len(s) <= 12:
        return False
    if re.match(r"^【(例|习题|思考|小结|目录)", s):
        return False
    if s in ("目录", "小结", "习题", "思考题", "本章小结", "前言"):
        return False
    return True

selfc = sum(1 for r in rows if is_self_contained(r["name"]))
print("name self-contained:", selfc, "/", n, "=", round(100 * selfc / n, 1), "%")
bad = [r["name"] for r in rows if not is_self_contained(r["name"])]
print("non-self-contained sample:", bad[:15])

# 2) 学习单元尺寸分布（用 excerpt chars）；学习单元目标区间 200–1200 字（≈1–3 分钟精读）
chars = [r["chars"] for r in rows]
def pct(f):
    return round(100 * sum(1 for c in chars if f(c)) / n, 1)
print("\nchars: p50", sorted(chars)[n // 2], "p90", sorted(chars)[int(n * 0.9)])
print("  <200 chars（碎片）:", pct(lambda c: c < 200), "%")
print("  200–1200（学习单元目标区）:", pct(lambda c: 200 <= c <= 1200), "%")
print("  1200–3000（偏大）:", pct(lambda c: 1200 < c <= 3000), "%")
print("  >3000（超单元）:", pct(lambda c: c > 3000), "%")
print("  >8000（单次读都很贵）:", pct(lambda c: c > 8000), "%")

# 3) 索引体积（含 preview/description 的估算已在 b_measure2 输出）
print("\nname chars p50:", sorted(len(r["name"]) for r in rows)[n // 2])

# 4) 每个文件的 KP 数与其 md 字数的关系（粒度是否一致）
byfile = {}
for r in rows:
    byfile.setdefault(r["file"], []).append(r)
for f, rs in sorted(byfile.items()):
    print(f, "kps", len(rs), "avg_chars", round(sum(x["chars"] for x in rs) / len(rs)))
