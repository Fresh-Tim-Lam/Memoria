# -*- coding: utf-8 -*-
"""
PDF 扫描版 -> Markdown（OCR 文字 + 嵌入图片）— 多进程并行版
用法: python pdf2md.py <pdf路径> <输出目录> [起始页] [结束页] [每批页数] [进程数]
"""
import argparse
import os
import sys
import time
from multiprocessing import Pool

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEPS_DIR = os.path.join(SCRIPT_DIR, "..", "ocr_deps")
if os.path.isdir(DEPS_DIR):
    sys.path.insert(0, DEPS_DIR)

import fitz  # PyMuPDF


def _init_worker():
    global _engine
    from rapidocr_onnxruntime import RapidOCR
    # 每个 worker 一个引擎实例；intra_op_num_threads 限制线程避免超额竞争
    _engine = RapidOCR(intra_op_num_threads=2)


def _ocr_img(img_path):
    """OCR 单张图片，返回识别文本。"""
    result, _ = _engine(str(img_path))
    if not result:
        return ""
    lines = []
    for r in sorted(result, key=lambda x: (x[0][0][1], x[0][0][0])):
        lines.append(r[1])
    return "\n".join(lines)


def convert(pdf_path, out_dir, start, end, batch, workers):
    os.makedirs(out_dir, exist_ok=True)
    img_dir = os.path.join(out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    total = doc.page_count
    end = min(end, total)
    print(f"PDF 共 {total} 页，本次处理 {start}-{end}，进程数 {workers}")

    def new_md(first, last):
        p = os.path.join(out_dir, f"part_{(first-1)//batch+1:02d}_p{first}-{last}.md")
        f = open(p, "w", encoding="utf-8")
        f.write(f"# 计算机图形学（扫描版 OCR）\n\n> 来源: {os.path.basename(pdf_path)}\n")
        f.write("> 说明: 本文件为扫描版 PDF 的 OCR 识别结果，附原页图片。OCR 可能存在识别误差。\n\n")
        return f

    md = new_md(start, min(end, start + batch - 1))
    t0 = time.time()

    # 先渲染全部页面图片
    print("渲染页面图片...")
    jobs = []
    zoom = 200 / 72
    mat = fitz.Matrix(zoom, zoom)
    for i in range(start, end + 1):
        pix = doc[i - 1].get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_path = os.path.join(img_dir, f"page_{i:04d}.jpg")
        pix.save(img_path, jpg_quality=92)
        jobs.append((i, img_path))
    print(f"渲染完成，共 {len(jobs)} 页，开始并行 OCR...")

    # 并行 OCR（imap 保持顺序）
    with Pool(processes=workers, initializer=_init_worker) as pool:
        img_paths = [p for _, p in jobs]
        for idx, ((i, img_path), text) in enumerate(zip(jobs, pool.imap(_ocr_img, img_paths, chunksize=4)), 1):
            md.write(f"---\n\n## 第 {i} 页\n\n")
            md.write(f"![第 {i} 页](.memoria/images/{os.path.basename(img_path)})\n\n")
            if text.strip():
                md.write("```text\n" + text + "\n```\n\n")
            else:
                md.write("（本页未识别到文字，可能为纯图片页）\n\n")

            if idx % batch == 0 and i != end:
                md.close()
                md = new_md(i + 1, min(end, i + batch))
            if idx % 20 == 0 or i == end:
                print(f"已完成 {i}/{end} 页，耗时 {time.time()-t0:.0f}s")

    md.close()
    doc.close()
    print(f"完成！输出目录: {out_dir}，总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("start", type=int, nargs="?", default=1)
    ap.add_argument("end", type=int, nargs="?", default=10**9)
    ap.add_argument("batch", type=int, nargs="?", default=50)
    ap.add_argument("workers", type=int, nargs="?", default=8)
    args = ap.parse_args()
    convert(args.pdf, args.outdir, args.start, args.end, args.batch, args.workers)
