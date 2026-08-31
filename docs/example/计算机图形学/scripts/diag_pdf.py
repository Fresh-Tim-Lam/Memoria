# -*- coding: utf-8 -*-
"""诊断 PDF 页面图片对象结构：每页图片数量、尺寸、位置"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ocr_deps"))
import fitz

pdf = r"D:\AAA_Courses\计算机图形学\计算机图形学_202608311002_54596-1-270.pdf"
doc = fitz.open(pdf)

for pno in [0, 1, 2, 5, 10]:
    page = doc[pno]
    print(f"\n===== 第 {pno+1} 页 (页面大小: {page.rect.width:.1f} x {page.rect.height:.1f}) =====")
    infos = page.get_image_info(xrefs=True)
    print(f"图片对象数量: {len(infos)}")
    for info in infos:
        bbox = info["bbox"]
        xref = info.get("xref", "?")
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        print(f"  xref={xref} bbox=({bbox[0]:.0f},{bbox[1]:.0f})-({bbox[2]:.0f},{bbox[3]:.0f}) "
              f"尺寸={w:.0f}x{h:.0f}pt  占页比={w*h/(page.rect.width*page.rect.height)*100:.1f}%")

# 查看所有页面的图片统计
print("\n===== 全 PDF 图片统计 =====")
sizes = {}
for pno in range(doc.page_count):
    page = doc[pno]
    infos = page.get_image_info(xrefs=True)
    for info in infos:
        bbox = info["bbox"]
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        area_ratio = w * h / (page.rect.width * page.rect.height)
        if area_ratio > 0.5:
            key = "整页/大半页"
        elif area_ratio > 0.1:
            key = "大插图"
        else:
            key = "小插图/图标"
        sizes.setdefault(key, 0)
        sizes[key] += 1
print(f"整页图片(>50%页面积): {sizes.get('整页/大半页',0)}")
print(f"大插图(10-50%页面积): {sizes.get('大插图',0)}")
print(f"小插图/图标(<10%页面积): {sizes.get('小插图/图标',0)}")

# 检查每页图片数量分布
from collections import Counter
per_page = Counter()
for pno in range(doc.page_count):
    n = len(doc[pno].get_image_info(xrefs=True))
    per_page[n] += 1
print(f"\n每页图片数量分布: {dict(sorted(per_page.items()))}")

# 查看图片原始像素尺寸
print("\n===== 前 10 个图片对象的原始像素尺寸 =====")
seen = set()
count = 0
for pno in range(doc.page_count):
    for info in doc[pno].get_image_info(xrefs=True):
        xref = info.get("xref")
        if xref in seen:
            continue
        seen.add(xref)
        wpx, hpx = info["width"], info["height"]
        bbox = info["bbox"]
        wpt = bbox[2]-bbox[0]; hpt = bbox[3]-bbox[1]
        print(f"  xref={xref} 像素={wpx}x{hpx} 显示={wpt:.0f}x{hpt:.0f}pt")
        count += 1
        if count >= 10:
            break
    if count >= 10:
        break

doc.close()
