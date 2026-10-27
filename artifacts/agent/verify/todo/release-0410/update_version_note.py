"""更新 version.md §1「说明」行为 0.4.10 发布记录（按行前缀定位，避免全角字符不匹配）。"""
import io
import sys

P = r"D:\AAA_Jupyter\Memoria\docs\conventions\version.md"
lines = io.open(P, encoding="utf-8", newline="").read().split("\n")

NEW = (
    "| 说明 | 最近已发布 = **0.4.10**（2026-10-27，tag `v0.4.10` → `19685ad7`；"
    "release commit `19685ad7`）；下一个版本待定 —— "
    "**0.5.x 专属「导出 / 导入」板块，该板块未做不得进入 0.5.x**（人裁）；"
    "0.5.0 曾发布后撤回，见 §2 0.x 约定 |"
)

hit = None
for i, line in enumerate(lines):
    if line.startswith("| 说明 | 最近已发布"):
        hit = i
        break

if hit is None:
    sys.exit("ABORT: 找不到『| 说明 | 最近已发布』行")

if "**0.4.10**" in lines[hit] and "0.5.x 专属" in lines[hit]:
    print("  SKIP（已是新内容）L%d" % (hit + 1))
else:
    print("  旧行 L%d：%s" % (hit + 1, lines[hit][:70]))
    lines[hit] = NEW
    io.open(P, "w", encoding="utf-8", newline="").write("\n".join(lines))
    print("  已替换")

txt = io.open(P, encoding="utf-8", errors="replace").read()
print()
print("复核：0.4.10=%d 处，0.4.9=%d 处" % (txt.count("0.4.10"), txt.count("0.4.9")))
for line in txt.split("\n"):
    if line.startswith("| 说明 |"):
        print("  " + line[:160])
