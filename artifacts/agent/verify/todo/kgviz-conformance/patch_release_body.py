"""给 0.4.10 发版 body 补披露：U-KGV-5 三项真人判读验收未做（目标第 4 项）。
幂等：已存在锚点则跳过。
"""
import io
import sys

P = r"D:\AAA_Jupyter\Memoria\artifacts\release-body-v0.4.10.md"
src = io.open(P, encoding="utf-8", newline="").read()


def add(anchor, insert, marker, label):
    global src
    if marker in src:
        print("  SKIP（已存在）", label)
        return
    if anchor not in src:
        sys.exit("ABORT: 未命中锚点 " + label)
    src = src.replace(anchor, anchor + insert, 1)
    print("  OK", label)


# ── EN ──────────────────────────────────────────────────────────────
add(
    "- KG node-size decision U-KGV-2 is still open:",
    "\n- **Three KG acceptance checks are human-gated and were not run in this release**:"
    " node-size ends distinguishable (T-size-1), label readability around 80% (T-label),"
    " and the 3D depth-misreading check (T-depth). The automated ones (T-size-2/3/4,"
    " T-census, T-stable) are in the test suite; these three need a person and are tracked"
    " as U-KGV-5 instead of being marked done.",
    "T-size-1",
    "EN U-KGV-5",
)

# ── ZH ──────────────────────────────────────────────────────────────
add(
    "- KG 节点大小有一个未决项 U-KGV-2：",
    "\n- **KG 有三项验收需要真人判读，本轮未做**：节点大小两端可辨（T-size-1）、"
    "标签可读性约 80%（T-label）、3D 深度误读检查（T-depth）。"
    "可机检的（T-size-2/3/4、T-census、T-stable）都已在测试里；"
    "这三项需要人参与，登记为 U-KGV-5，而不是标记为已完成。",
    "T-size-1、标签可读性",
    "ZH U-KGV-5",
)

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("  写入完成，%d 字节" % len(src))
print()
print("复核：")
for kw in ("T-size-1", "T-label", "T-depth", "U-KGV-5"):
    print("  %-10s 出现 %d 次" % (kw, src.count(kw)))
