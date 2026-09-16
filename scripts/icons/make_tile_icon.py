#!/usr/bin/env python3
"""把透明底的 logo 图形合成为"圆角外框 + 渐变底"的应用图标。

为什么需要它：原始图形由**两种颜色**构成（深海军蓝 + 薄荷青），两色亮度相差极大——
深色系统上看不清深蓝，浅色系统上看不清薄荷。给它加一层**自带对比**的底：
底色渐变两端就是这两个颜色（浅薄荷 → 深海军蓝），于是
  · 深蓝块落在浅端 → 对比高
  · 薄荷形落在深端 → 对比高
并且图标自带不透明外框，与桌面底色无关（白底/黑底都清晰，另有细描边兜住浅色桌面的边缘）。

用法：
    python scripts/icons/make_tile_icon.py                 # 默认：_Memoria-mark.png → Memoria.png
    python scripts/icons/make_tile_icon.py --help          # 可调尺寸/圆角/比例/渐变色

随后跑图标流水线生成 ico：
    python scripts/icons/build_icons.py --force

依赖：Pillow。
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = REPO_ROOT / "resources" / "icons"

# 设计参数（可用命令行覆盖）
SIZE = 1024              # 输出画布边长
MARGIN_RATIO = 0.03      # 外框到画布的留白（保留圆角轮廓感）
RADIUS_RATIO = 0.115     # 圆角半径 / 画布边长
MARK_WIDTH_RATIO = 0.80  # 图形宽度 / 外框宽度（可见图形按裁边后计算）
# 视觉配重：图形整体相对外框的平移（占外框边长比例，正数=向右，负数=向左）。
#   这里取向右一点：图形左侧是实心深蓝块、质量偏左，向右移后整体观感更居中。
#   · BALANCE：按 alpha 质量质心纠偏的比例（0=不用，1=完全按质心居中）。
#     注意质心≠观感（此图形质心偏左、视觉外扩在右），默认关闭，需要时再用 --balance 开。
OFFSET_X_RATIO = 0.058
OFFSET_Y_RATIO = 0.0
BALANCE = 0.0
GRAD_FROM = "#0A3A66"    # 渐变起点（深海军蓝）
GRAD_TO = "#BFEDE4"      # 渐变终点（浅薄荷）
# 渐变变化快慢：1=线性匀速；>1=中段变化更快、过渡带更窄（更接近硬分界）
GRAD_SHARPNESS = 1.6
# 是否使用渐变底；当前改用纯色底（--gradient 可切回渐变）
USE_GRADIENT = False
SOLID_COLOR = "#808080"   # 中性灰：亮度 0.216 ≈ 两色亮度的几何均值，两边对比同时约 3:1
# 图形内部颜色对调：深蓝↔薄荷；FLATTEN_MARK=True 时两色**平涂**（干净、易手绘取色）
INVERT_MARK = True
FLATTEN_MARK = True
# 渐变分界是否跟随图形的平移一起偏移（图形不在正中时，分界留在正中会显得底与图形错位）
GRAD_SHIFT_WITH_MARK = True
OUTLINE = "#062B4E"      # 外框描边色（保证白底上轮廓清晰）
OUTLINE_ALPHA = 72       # 描边透明度 0-255
# 渐变方向：水平（纯左右，不带对角）。from=深 → 左深右浅，与图形明暗相反 → 对比成立。
# 想要对角就把 P0/P1 的 y 拉开（如 (0.0, 0.85) → (1.0, 0.15)）。
GRAD_P0 = (0.0, 0.5)
GRAD_P1 = (1.0, 0.5)


def hex_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def lum(r: int, g: int, b: int) -> float:
    """相对亮度（WCAG），用于判断两色孰深孰浅、以及校验对比度。"""
    def f(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def make_gradient(w: int, h: int, c0: tuple[int, int, int], c1: tuple[int, int, int],
                  shift: tuple[float, float] = (0.0, 0.0), sharpness: float = 1.0):
    """线性渐变（水平或斜向，取决于 GRAD_P0/GRAD_P1）。

    shift：控制点的整体平移（归一化 0..1），用于让**渐变分界**跟着图形一起偏移
    —— 图形不在外框正中时，分界若还在正中就会显得"底和图形错位"。
    sharpness：颜色变化的快慢。1=线性匀速；>1=中段变化更快、过渡带更窄（接近硬分界）；
               <1=过渡更柔和。
    """
    from PIL import Image

    n = 256
    g = Image.new("RGB", (n, n))
    px = g.load()
    x0, y0 = GRAD_P0[0] + shift[0], GRAD_P0[1] + shift[1]
    x1, y1 = GRAD_P1[0] + shift[0], GRAD_P1[1] + shift[1]
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy
    for y in range(n):
        for x in range(n):
            u = ((x / (n - 1) - x0) * dx + (y / (n - 1) - y0) * dy) / denom
            u = 0.5 + (u - 0.5) * sharpness          # 变化快慢
            u = 0.0 if u < 0 else (1.0 if u > 1 else u)
            px[x, y] = tuple(round(c0[i] + (c1[i] - c0[i]) * u) for i in range(3))
    return g.resize((w, h), Image.BICUBIC)


def alpha_centroid(img):
    """alpha 加权质心（相对图像几何中心，单位：像素，正数=偏右/偏下）。"""
    from PIL import Image

    n = 256
    small = img.convert("RGBA").resize((n, n), Image.BOX)   # BOX 降采样≈面积加权，质心不失真
    a = small.getchannel("A")
    data = list(a.getdata())
    tot = sum(data)
    if not tot:
        return 0.0, 0.0
    sx = sy = 0
    for i, v in enumerate(data):
        if v:
            sx += (i % n) * v
            sy += (i // n) * v
    return (sx / tot - (n - 1) / 2) * img.width / n, (sy / tot - (n - 1) / 2) * img.height / n


def invert_mark_colors(img, c_deep, c_light, flatten=True):
    """深浅对调：把图形整体映射到 深↔浅 两个目标色。

    flatten=True（默认）：**两色平涂** —— 每个像素直接取两个纯色之一（按亮度分簇），
      得到干净、易手绘/取色的图（边缘平滑交给 alpha，不受影响）。
    flatten=False：按亮度在两点之间连续插值，保留原图那种细微混色手感。
    """
    lo, hi = 255, 0
    a = img.getchannel("A")
    lum_im = img.convert("L")
    for v, av in zip(lum_im.getdata(), a.getdata()):
        if av > 32:
            lo = min(lo, v)
            hi = max(hi, v)
    if hi <= lo:
        return img
    table = []
    if flatten:
        mid = (lo + hi) / 2
        for v in range(256):
            table.append(c_light if v <= mid else c_deep)   # 深的一半→浅色，浅的一半→深色
    else:
        for v in range(256):
            u = 1.0 - min(1.0, max(0.0, (v - lo) / (hi - lo)))
            table.append(tuple(round(c_deep[i] + (c_light[i] - c_deep[i]) * u) for i in range(3)))
    out = img.copy()
    px, src = out.load(), lum_im.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, al = px[x, y]
            if al == 0:
                continue
            # 平涂时同时把 alpha 二值化：原图有大片半透明像素（a≈128），
            # 它们与底色合成后会重新变成"中间色"，破坏"纯色"。
            # 1024 源图干净，小尺寸 ico 由流水线重采样补回平滑边缘。
            a_new = (255 if al >= 128 else 0) if flatten else al
            px[x, y] = table[src[x, y]] + (a_new,)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="合成圆角渐变底的应用图标")
    ap.add_argument("--mark", default=str(ICON_DIR / "_Memoria-mark.png"),
                    help="透明底的 logo 源图（默认 resources/icons/_Memoria-mark.png）")
    ap.add_argument("--out", default=str(ICON_DIR / "Memoria.png"),
                    help="输出路径（默认 resources/icons/Memoria.png）")
    ap.add_argument("--size", type=int, default=SIZE)
    ap.add_argument("--mark-ratio", type=float, default=MARK_WIDTH_RATIO)
    ap.add_argument("--balance", type=float, default=BALANCE,
                    help="视觉配重比例：0=纯几何居中，1=按质心居中（默认 0.5）")
    ap.add_argument("--dx", type=int, default=None, help="直接指定横向平移（像素，覆盖配重计算）")
    ap.add_argument("--dy", type=int, default=None, help="直接指定纵向平移（像素）")
    ap.add_argument("--invert-mark", action=argparse.BooleanOptionalAction, default=INVERT_MARK,
                    help="图形内部深浅对调（深↔浅），默认开")
    ap.add_argument("--flatten", action=argparse.BooleanOptionalAction, default=FLATTEN_MARK,
                    help="图形两色平涂（默认开；--no-flatten 保留原图细微混色）")
    ap.add_argument("--grad-shift", action=argparse.BooleanOptionalAction,
                    default=GRAD_SHIFT_WITH_MARK,
                    help="渐变分界跟随图形偏移，默认开")
    ap.add_argument("--sharpness", type=float, default=GRAD_SHARPNESS,
                    help="渐变变化快慢：1=线性，>1 过渡带更窄（默认 1.6）")
    ap.add_argument("--gradient", action=argparse.BooleanOptionalAction, default=USE_GRADIENT,
                    help="是否用渐变底（--no-gradient = 纯色底）")
    ap.add_argument("--solid", default=SOLID_COLOR,
                    help="纯色底颜色（默认取 --from 的颜色）")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已存在的输出文件（默认拒绝，防止覆盖手绘成品）")
    ap.add_argument("--radius-ratio", type=float, default=RADIUS_RATIO)
    ap.add_argument("--margin-ratio", type=float, default=MARGIN_RATIO)
    ap.add_argument("--from", dest="c_from", default=GRAD_FROM)
    ap.add_argument("--to", dest="c_to", default=GRAD_TO)
    ap.add_argument("--outline", default=OUTLINE, help="外框描边色")
    ap.add_argument("--outline-alpha", type=int, default=OUTLINE_ALPHA, help="描边透明度 0-255")
    args = ap.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise SystemExit("需要 Pillow：pip install Pillow")

    mark_src = Path(args.mark)
    if not mark_src.is_file():
        raise SystemExit(f"找不到 logo 源图：{mark_src}")

    size = args.size
    mark = Image.open(mark_src).convert("RGBA")
    # 裁掉透明外框：可见图形才真正占满 mark_ratio（否则源图的透明留白会白吃尺寸）
    bbox = mark.getbbox()
    if bbox:
        mark = mark.crop(bbox)

    # 图形内部深浅对调：深的那一色 → 渐变浅端色，浅的那一色 → 渐变深端色
    c_a, c_b = hex_rgb(args.c_from), hex_rgb(args.c_to)
    c_deep, c_light = (c_a, c_b) if lum(*c_a) <= lum(*c_b) else (c_b, c_a)
    if args.invert_mark:
        mark = invert_mark_colors(mark, c_deep, c_light, flatten=args.flatten)

    # ── 图形：等比缩放到外框宽度的 mark_ratio + 视觉配重（先算位置，渐变要跟着偏移）──
    inner = size - 2 * round(size * args.margin_ratio)
    target_w = round(inner * args.mark_ratio)
    target_h = round(mark.height * target_w / mark.width)
    if target_h > inner * 0.9:                      # 过高时以高度为约束
        target_h = round(inner * 0.9)
        target_w = round(mark.width * target_h / mark.height)
    mark_r = mark.resize((target_w, target_h), Image.LANCZOS)

    cdx, cdy = alpha_centroid(mark)
    scale = target_w / mark.width
    bias_x = round(inner * OFFSET_X_RATIO)
    bias_y = round(inner * OFFSET_Y_RATIO)
    dx = args.dx if args.dx is not None else round(bias_x - args.balance * cdx * scale)
    dy = args.dy if args.dy is not None else round(bias_y - args.balance * cdy * scale)

    # 渐变分界跟随图形偏移（--no-grad-shift 可关掉）
    grad_shift = (dx / size, dy / size) if args.grad_shift else (0.0, 0.0)

    # ── 外框：圆角矩形 + 渐变 + 描边 ──
    margin = round(size * args.margin_ratio)
    box = (margin, margin, size - margin, size - margin)
    radius = round(size * args.radius_ratio)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    if args.gradient:
        tile = make_gradient(size, size, hex_rgb(args.c_from), hex_rgb(args.c_to),
                             shift=grad_shift, sharpness=args.sharpness).convert("RGBA")
    else:
        solid = args.solid or args.c_from
        tile = Image.new("RGBA", (size, size), hex_rgb(solid) + (255,))
    tile.putalpha(mask)
    ImageDraw.Draw(tile).rounded_rectangle(
        box, radius=radius,
        outline=hex_rgb(args.outline) + (args.outline_alpha,),
        width=max(2, round(size * 0.012)),
    )

    tile.alpha_composite(
        mark_r,
        ((size - target_w) // 2 + dx, (size - target_h) // 2 + dy),
    )

    out = Path(args.out)
    # ★ 防误覆盖：手绘的成品图若放在默认输出路径（resources/icons/Memoria.png），
    #   误跑本脚本会把它覆盖掉；因此存在即拒绝，需显式 --force。
    if out.exists() and not args.force:
        raise SystemExit(
            f"输出已存在：{out}\n"
            "本脚本是「用 logo 合成图标」的工具，会整体覆盖该文件。\n"
            "  · 若那张图是你手绘的成品 → 换 --out 到别处，或先备份；\n"
            "  · 确实要覆盖 → 加 --force。"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    tile.save(out)
    try:
        shown = out.relative_to(REPO_ROOT)
    except ValueError:
        shown = out          # --out 指到仓库外时也能正常打印
    print(f"已生成 {shown}  {size}×{size}  "
          f"图形 {target_w}×{target_h}  渐变 {args.c_from} → {args.c_to}")
    print(f"  平移 {dx:+d},{dy:+d}px（几何居中 + 既定偏置 {bias_x:+d},{bias_y:+d}"
          f" + 质心纠偏 balance={args.balance}）；"
          f"参考：图形质量质心 dx={cdx:+.1f}px（源图尺度）")
    if not args.gradient:
        base = hex_rgb(args.solid or args.c_from)

        def _c(a, b):
            la, lb = lum(*a), lum(*b)
            return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

        r_light, r_dark = _c(c_light, base), _c(c_deep, base)
        warn = "  ← 有一色偏低：平底很难让两色图形同时立住" if min(r_light, r_dark) < 2.5 else ""
        print(f"  纯色底 #{base[0]:02x}{base[1]:02x}{base[2]:02x}："
              f"浅色图形 {r_light:.2f}:1 / 深色图形 {r_dark:.2f}:1{warn}")
    print("接着跑： python scripts/icons/build_icons.py --force")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
