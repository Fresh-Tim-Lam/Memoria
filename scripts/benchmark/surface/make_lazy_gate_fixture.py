# -*- coding: utf-8 -*-
"""生成「惰性路径交互门禁」的大文档 fixture（确定性、可复跑）。

为什么需要它：
  `run_interaction.py` 的 12 个交互剧本都跑在 <200 块的小文档上 ⇒ 永远走全量渲染，
  惰性物化 / 工作集淘汰 / 公式 pending 三个特性**没有固定回归**（W4.1）。
  本脚本生成一个**仓库内稳定 fixture**（≥1000 块，含公式/表格/mermaid/代码），
  供 `run_lazy_gate.py` 一条命令复跑；不依赖 `artifacts/**`（那是可再生缓存）。

产物（入库）：
  `scripts/benchmark/surface/fixtures/lazy-gate-kb/docs/lazy-gate-1600.md`

约定：
  · 每个 section 都有一行 `LAZYGATE-MARK-<NNNN>` 标记段落 ⇒ 门禁可把「视口文本」
    与「源文件行号」对上，证明看到的是该位置的真实内容（不是幽灵/残留块）。
  · 内容全部合成，不含用户数据；生成顺序固定 ⇒ 同参数必得同样字节。
"""

from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "fixtures" / "lazy-gate-kb" / "docs" / "lazy-gate-1600.md"

HEADER = """# 惰性门禁大文档（合成 fixture）

> 本文件由 `scripts/benchmark/surface/make_lazy_gate_fixture.py` 确定性生成，**请勿手改**。
> 用途：W4.1 惰性路径交互门禁（≥1000 块；含行内/块级公式、表格、mermaid、代码、列表、引用）。
> 每节首段含 `LAZYGATE-MARK-<NNNN>`：门禁用它把「视口里看到的文本」与「源文件行号」对齐。

"""

# 一段足够长、但不重复的正文（含行内公式）；每个 section 换数字与字母，保证不是同一块内容。
PARA = (
    "本节讨论第 {n} 组样本的物化与淘汰行为：设输入序列为 $x_{{{n}}} = "
    "\\sum_{{k=1}}^{{{k}}}\\alpha_k y_k$，在窗口宽度为 {w} 的视口内，"
    "只有落入工作集的块会被真正排版；其余块保持占位（高度由实测行高 {lh} 推算，"
    "不硬编码像素）。实验标记 `TOKEN-{n:04d}-A` 用于确认文本没有串位；"
    "英文段落 the quick brown fox jumps over the lazy dog, sample {n}, width {w}."
)

TABLE = """| 序号 | 参数 | 取值 | 说明 |
|---:|---|---:|---|
| {n} | `keepScreens` | 4 | 视口上下各保留屏数 |
| {n} | `batchMax` | 60 | 单批淘汰上限 |
| {n} | `recentMs` | 1500 | LRU 近期窗口 |
| {n} | `viewport` | {w}×{h} | 门禁窗口 |
"""

CODE = """```python
def materialize_range(blocks, start, end):
    \"\"\"第 {n} 组：只物化 [start, end) 内的占位块。\"\"\"
    made = []
    for i in range(start, end):
        if blocks[i].is_placeholder:
            made.append(blocks[i].materialize())
    return made
```
"""

MATH = """$$
\\begin{{aligned}}
S_{{{n}}} &= \\sum_{{i=1}}^{{N}} w_i \\cdot f(x_i) \\\\
       &= \\frac{{1}}{{{n}}} \\sum_{{j=1}}^{{{n}}} \\left( a_j + b_j \\right)^2
\\end{{aligned}}
\\tag{{{n}.1}}
$$
"""

MERMAID = """```mermaid
graph TD
    A[{n} 起点] --> B{{视口内?}}
    B -->|是| C[物化]
    B -->|否| D[保持占位]
    C --> E[进入工作集]
    D --> F[IO 预取 2 屏]
    F --> C
```
"""


def build(sections: int) -> str:
    out = [HEADER]
    for n in range(1, sections + 1):
        w = 1264 + (n % 3) * 16
        h = 821
        k = 3 + (n % 4)
        out.append("## 第 %d 节 · 惰性门禁样章 %04d\n" % (n, n))
        out.append("")
        out.append(
            "LAZYGATE-MARK-%04d 区域标记：本节用于验证大文档的惰性物化与工作集淘汰；"
            "标记行号是门禁的文本-位置对齐锚点。\n" % n
        )
        out.append("")
        out.append(PARA.format(n=n, k=k, w=w, lh="22.4") + "\n")
        out.append("")
        if n % 2 == 0:
            out.append(MATH.format(n=n))
            out.append("")
        if n % 3 == 0:
            out.append(TABLE.format(n=n, w=w, h=h))
            out.append("")
        if n % 5 == 0:
            out.append(MERMAID.format(n=n))
            out.append("")
        if n % 4 == 0:
            out.append(CODE.format(n=n))
            out.append("")
        out.append("### %d.%d 观察项\n" % (n, 1 + (n % 3)))
        out.append("")
        out.append(
            "- 观察项 A：占位块高度必须由实测行高推算，禁止硬编码。\n"
            "- 观察项 B：滚动停止 50ms 内，视口内占位块数应回到 0。\n"
            "- 观察项 C：远处块允许被淘汰；被编辑/选中的块必须保留。\n"
            "- 观察项 D：滚回原位时绝对行号漂移 ≤5 行。\n"
        )
        out.append("")
        out.append("> 引用 %04d：工作集淘汰是“缺页换出”，不是渲染裁剪；占位必须保高。\n" % n)
        out.append("")
        out.append("---\n")
        out.append("")
    out.append("<!-- LAZYGATE-END sections=%d -->\n" % sections)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成惰性门禁大文档 fixture")
    ap.add_argument("--sections", type=int, default=160, help="章节数（默认 160 ≈ 1600+ 块）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 markdown 路径")
    args = ap.parse_args()

    text = build(args.sections)
    out = Path(args.out)
    if not out.is_absolute():
        out = (HERE / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    # 粗算：markdown 行数（真正的 AST 块数由门禁在浏览器里用 parser 实测并写进 JSON）
    print("[fixture] wrote %s (%d bytes, %d lines, %d sections)" % (
        out, len(text.encode("utf-8")), text.count("\n") + 1, args.sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
