# -*- coding: utf-8 -*-
"""按章节拆分 MinerU 导出的两个 Markdown，并合并图片目录。"""
import os
import re
import shutil

SRC = r"D:\AAA_Courses\计算机图形学"
OUT = os.path.join(SRC, "按章节")

OCR1 = os.path.join(SRC, "MinerU导出_1-270", "计算机图形学_202608311002_54596-1-270", "ocr")
OCR2 = os.path.join(SRC, "MinerU导出_271-555", "计算机图形学_202608311002_54596-271-555", "ocr")
MD1 = os.path.join(OCR1, "计算机图形学_202608311002_54596-1-270.md")
MD2 = os.path.join(OCR2, "计算机图形学_202608311002_54596-271-555.md")

# ---------- 1. 合并图片 ----------
os.makedirs(os.path.join(OUT, "images"), exist_ok=True)
for ocr_dir in (OCR1, OCR2):
    src_img = os.path.join(ocr_dir, "images")
    for name in os.listdir(src_img):
        if name.lower().endswith((".jpg", ".jpeg", ".png")):
            shutil.copy2(os.path.join(src_img, name), os.path.join(OUT, "images", name))

# ---------- 2. 读取并切分 ----------
with open(MD1, encoding="utf-8") as f:
    md1 = f.read().splitlines(keepends=True)
with open(MD2, encoding="utf-8") as f:
    md2 = f.read().splitlines(keepends=True)

CHAP_RE = re.compile(r"^#{1,3}\s*第\s*(\d+)\s*章")
APP_RE = re.compile(r"^#{1,2}\s*附录")

def chapter_no(line):
    m = CHAP_RE.match(line)
    return int(m.group(1)) if m else None

def chapter_name(line):
    m = re.match(r"^#{1,3}\s*第\s*\d+\s*章\s*(.*)$", line)
    return re.sub(r"\s+", "", m.group(1)) if m else ""

def write(name, lines):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"{name}\t{len(lines)} 行")

# MD1 内章节起始行（0-indexed）
starts1 = [i for i, l in enumerate(md1) if CHAP_RE.match(l)]
# MD2 内章节起始行与附录起始行
starts2 = [i for i, l in enumerate(md2) if CHAP_RE.match(l)]
app_start = next((i for i, l in enumerate(md2) if APP_RE.match(l)), len(md2))

# 前置部分（封面/前言/目录）：MD1 第一个章节之前
write("00_封面与前言.md", md1[: starts1[0]])

# 章节：MD1 内的第1~5章（完整段）
for k in range(4):  # starts1[0..3] -> 第1~4章
    num = chapter_no(md1[starts1[k]])
    seg = md1[starts1[k] : starts1[k + 1]]
    write(f"{num:02d}_第{num}章_{chapter_name(md1[starts1[k]])}.md", seg)

# 第5章：完整段
num = chapter_no(md1[starts1[4]])
write(f"{num:02d}_第{num}章_{chapter_name(md1[starts1[4]])}.md", md1[starts1[4] : starts1[5]])

# 第6章：MD1 段 + MD2 开头第6章结尾（跨文件合并）
seg6 = md1[starts1[5] :] + ["\n"] + md2[: starts2[0]]
num = chapter_no(md1[starts1[5]])
write(f"{num:02d}_第{num}章_{chapter_name(md1[starts1[5]])}.md", seg6)

# 第7~13章：MD2 内完整段
for k in range(len(starts2)):
    end = starts2[k + 1] if k + 1 < len(starts2) else app_start
    num = chapter_no(md2[starts2[k]])
    write(f"{num:02d}_第{num}章_{chapter_name(md2[starts2[k]])}.md", md2[starts2[k] : end])

# 附录 A-D + 参考文献
write("14_附录与参考文献.md", md2[app_start:])

# ---------- 3. 校验图片引用 ----------
total_ref = 0
missing = []
for name in os.listdir(OUT):
    if not name.endswith(".md"):
        continue
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        text = f.read()
    for m in re.finditer(r"!\[\]\(.memoria/images/([^)]+)\)", text):
        total_ref += 1
        if not os.path.exists(os.path.join(OUT, "images", m.group(1))):
            missing.append((name, m.group(1)))
print(f"\n图片引用总数: {total_ref}, 缺失: {len(missing)}")
for name, img in missing[:10]:
    print("  MISSING:", name, img)
print(f"输出目录: {OUT}")
