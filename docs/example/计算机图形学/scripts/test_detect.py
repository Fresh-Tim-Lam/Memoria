# -*- coding: utf-8 -*-
"""测试: 从整页扫描图中检测插图区域（OpenCV 轮廓检测）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ocr_deps"))
import cv2
import numpy as np
import fitz

pdf = r"D:\AAA_Courses\计算机图形学\计算机图形学_202608311002_54596-271-555.pdf"
doc = fitz.open(pdf)

# 检查第 51 页（第 1 个文件 part_02 中显示有图8.5、图8.6 的第51页）和附近页
# 注意: 271-555 文件的第一页对应书页 271
for pno in [0, 3, 4, 50, 100]:
    page = doc[pno]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 自适应阈值找"非纯白/非纯文本"的块
    # 方法: 使用形态学闭运算连接文字为块, 检测插图轮廓
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    # 边缘检测
    edges = cv2.Canny(blur, 50, 150)
    # 闭运算连接
    kernel = np.ones((15, 15), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = img.shape[:2]
    print(f"\n===== 第 {pno+1} 页 (图像 {w}x{h}) =====")
    candidates = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        ratio = cw / ch if ch > 0 else 0
        # 过滤: 面积大于页面 1%，宽高比合理，非整页
        if area > 0.01 * w * h and 0.2 < ratio < 5 and cw < 0.98 * w:
            candidates.append((x, y, cw, ch, area))
    candidates.sort(key=lambda t: -t[4])
    for x, y, cw, ch, area in candidates[:8]:
        print(f"  区域: x={x} y={y} w={cw} h={ch}  占页={area/(w*h)*100:.1f}%  宽高比={cw/ch:.2f}")

doc.close()
