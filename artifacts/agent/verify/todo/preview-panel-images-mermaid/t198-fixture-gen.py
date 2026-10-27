# -*- coding: utf-8 -*-
"""task-198 夹具：B1 图片编辑滚动 / B2 小窗 mermaid / B3 关闭小窗滚动。"""
from __future__ import annotations

import base64
import shutil
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixture" / "kb"


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "docs").mkdir(parents=True)
    (OUT / ".memoria" / "images").mkdir(parents=True)
    (OUT / ".memoria" / "images" / "pic.png").write_bytes(_png(480, 280, (38, 120, 190)))

    # B1：图前/图后各有大量文字；图位于中段，便于滚动到中段编辑图片。
    lines: list[str] = ["# 图片编辑滚动复现", ""]
    for i in range(1, 61):
        lines += [f"## 图前章节 {i}", "", f"图前段落 {i}：" + ("这是用于撑高预览的内容。" * 6), ""]
    lines += ["![示例图](.memoria/images/pic.png)", ""]
    for i in range(1, 61):
        lines += [f"## 图后章节 {i}", "", f"图后段落 {i}：" + ("这是用于撑高预览的内容。" * 6), ""]
    (OUT / "docs" / "long-image.md").write_text("\n".join(lines), encoding="utf-8")

    # B2/B3：源文件里有一个跳转入口；目标文件区域含 mermaid。
    src: list[str] = ["# 跳转源文件", ""]
    for i in range(1, 40):
        src += [f"源文件铺垫 {i}：" + ("用于把入口放在可滚动位置。" * 4), ""]
    src += ["[[link-target]]", ""]
    for i in range(1, 20):
        src += [f"源文件尾部 {i}：" + ("继续撑高。" * 4), ""]
    (OUT / "docs" / "link-source.md").write_text("\n".join(src), encoding="utf-8")
    target = [
        "# 跳转目标",
        "",
        "目标文件开头的说明。",
        "",
        "```mermaid",
        "graph TD",
        "  A[入口] --> B{小窗里能出图吗}",
        "  B -->|能| C[通过]",
        "  B -->|不能| D[复现]",
        "```",
        "",
        "mermaid 之后还有文字。",
    ]
    (OUT / "docs" / "link-target.md").write_text("\n".join(target), encoding="utf-8")
    (OUT / "README.md").write_text("# task-198 fixture\n", encoding="utf-8")
    print(f"fixture -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
