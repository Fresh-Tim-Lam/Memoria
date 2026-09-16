#!/usr/bin/env python3
"""图标清理/换色工具：把杂色吸附到调色板、清碎点，可按明暗整体对调。

用途（针对手绘图标）：
    · 手绘时笔刷软边/残影会产生大量过渡色 → 全部吸附到最近的主色，颜色变"纯"；
    · 旧版合成留下的**灰边**（低饱和像素）→ 用邻居颜色补上（不是吸附，否则浅色区外侧会刷出深色光晕）；
    · --despeckle 把孤立的小碎块并进周围颜色；
    · --invert 把调色板顺序整体反转（按明度排好序时即"最亮↔最暗、次亮↔次暗"）——试试反向配色。

用法：
    python scripts/icons/recolor_icon.py --in Memoria.png --out Memoria-clean.png
    python scripts/icons/recolor_icon.py --in Memoria.png --out Memoria-inverted.png --invert

注意：
    · 调色板是 N 色（默认 4 色，见 PALETTE）；**只放真被画上去的颜色**，
      过渡色/灰边交给脚本处理 —— 少放一个色就会把那块实心区域并掉
    · 默认**保留 alpha**（不动边缘平滑与半透明描边），只改 RGB；想要硬边用 --binarize-alpha 128
    · --invert 只换"落到像素上的颜色"，不换"判最近色的调色板"（后者反转等于没换）
    · 默认拒绝覆盖已存在的输出，需 --force
依赖：Pillow
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = REPO_ROOT / "resources" / "icons"

# 当前主色（手绘版实测值），**按明度从亮到暗排列**：--invert 会把该顺序整体反转，
# 于是"最亮↔最暗、次亮↔次暗"成对交换。想换配对方式就改这里的顺序，或用 --palette 覆盖。
PALETTE = ("#bfede4", "#98bdb5", "#136ebf", "#0f5696")


def hex_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def nearest(rgb: tuple[int, int, int], palette) -> int:
    best, bi = None, 0
    for i, c in enumerate(palette):
        d = sum((rgb[k] - c[k]) ** 2 for k in range(3))
        if best is None or d < best:
            best, bi = d, i
    return bi


def main() -> int:
    ap = argparse.ArgumentParser(description="图标清理 / 换色")
    ap.add_argument("--in", dest="src", default=str(ICON_DIR / "Memoria.png"))
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--palette", default=",".join(PALETTE),
                    help="主色（逗号分隔，默认 %s）" % ",".join(PALETTE))
    ap.add_argument("--invert", action="store_true", help="按调色板顺序整体反转（最亮↔最暗）")
    ap.add_argument("--despeckle", type=int, default=30,
                    help="小于该面积的碎块并入周围颜色（0=不做，默认 30）")
    ap.add_argument("--gray-tol", type=int, default=24, metavar="S",
                    help="饱和度 ≤ S 视为灰残影，用邻居颜色补上（-1=不处理，默认 24）")
    ap.add_argument("--binarize-alpha", type=int, default=0, metavar="T",
                    help="alpha ≥ T 视为不透明、否则透明（默认 0=保留原 alpha）")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("需要 Pillow：pip install Pillow")

    src, dst = Path(args.src), Path(args.dst)
    if not src.is_file():
        raise SystemExit(f"找不到输入：{src}")
    if dst.exists() and not args.force:
        raise SystemExit(f"输出已存在：{dst}（加 --force 覆盖）")

    pal = [hex_rgb(x.strip()) for x in args.palette.split(",") if x.strip()]
    if len(pal) < 2:
        raise SystemExit("--palette 至少两个颜色")
    # 吸附永远按"原序"判最近色；--invert 只改**落到像素上的**颜色。
    # （若直接反转调色板再吸附，结果图与不反转完全相同 —— 最近色判定与调色板顺序无关。）
    paint = list(reversed(pal)) if args.invert else pal

    im = Image.open(src).convert("RGBA")
    W, H = im.size
    px = im.load()

    # 1) 分类：透明 → 跳过；低饱和（灰残影）→ 待补；其余 → 最近主色
    #    灰残影不能"吸附到最近主色"：夹在浅色区外侧的灰会变成深色，刷出一圈深色光晕。
    EMPTY, PENDING = 250, 251
    lab = bytearray(W * H)
    hist = [0] * len(pal)
    for y in range(H):
        row = y * W
        for x in range(W):
            r, g, b, a = px[x, y]
            if a == 0:
                lab[row + x] = EMPTY
            elif args.gray_tol >= 0 and max(r, g, b) - min(r, g, b) <= args.gray_tol:
                lab[row + x] = PENDING
            else:
                i = nearest((r, g, b), pal)
                lab[row + x] = i
                hist[i] += 1

    # 2) 灰残影补色：从所有"已确定"像素同时出发做 BFS，取最近邻的颜色（8 邻域）
    filled = 0
    if args.gray_tol >= 0:
        q = deque(i for i, v in enumerate(lab) if v != PENDING and v != EMPTY)
        while q:
            i = q.popleft()
            y, x = divmod(i, W)
            v = lab[i]
            for ny in (y - 1, y, y + 1):
                if not 0 <= ny < H:
                    continue
                nr = ny * W
                for nx in (x - 1, x, x + 1):
                    if 0 <= nx < W and lab[nr + nx] == PENDING:
                        lab[nr + nx] = v
                        q.append(nr + nx)
                        filled += 1
        print(f"  灰残影补色：{filled} px")

    # 3) 落盘像素：主色替换 +（可选）alpha 二值化
    na_cache = {}
    for y in range(H):
        row = y * W
        for x in range(W):
            v = lab[row + x]
            if v == EMPTY:
                continue
            if v == PENDING:  # 孤立灰（四周也没有确定色）→ 退回"最近主色"
                v = nearest(px[x, y][:3], pal)
            a = px[x, y][3]
            if args.binarize_alpha:
                na = na_cache.get(a)
                if na is None:
                    na = na_cache[a] = 255 if a >= args.binarize_alpha else 0
            else:
                na = a
            px[x, y] = paint[v] + (na,)

    # 4) 碎点清理：把面积过小的同色连通块并入"邻居里最多的另一种色"
    if args.despeckle > 0:
        seen = bytearray(W * H)
        merged = 0
        for y0 in range(H):
            for x0 in range(W):
                i0 = y0 * W + x0
                if seen[i0] or px[x0, y0][3] == 0:
                    continue
                color = px[x0, y0][:3]
                q = deque([(x0, y0)])
                seen[i0] = 1
                cells = []
                while q:
                    x, y = q.popleft()
                    cells.append((x, y))
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < W and 0 <= ny < H:
                            i = ny * W + nx
                            if not seen[i] and px[nx, ny][3] > 0 and px[nx, ny][:3] == color:
                                seen[i] = 1
                                q.append((nx, ny))
                if len(cells) >= args.despeckle:
                    continue
                # 统计边界外邻居的主色
                votes = {}
                for x, y in cells:
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < W and 0 <= ny < H:
                            nb = px[nx, ny]
                            if nb[3] > 0 and nb[:3] != color:
                                votes[nb[:3]] = votes.get(nb[:3], 0) + 1
                if not votes:
                    continue
                keep = max(votes.items(), key=lambda kv: kv[1])[0]
                for x, y in cells:
                    px[x, y] = keep + (px[x, y][3],)
                merged += len(cells)
        print(f"  碎点合并：{merged} px")

    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst)
    try:
        shown = dst.relative_to(REPO_ROOT)
    except ValueError:
        shown = dst
    print(f"已生成 {shown}  调色板 {len(pal)} 色  像素占比 {hist}")
    if args.invert:
        for a, b in zip(pal, paint):
            print(f"    #%02x%02x%02x → #%02x%02x%02x" % (a + b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
