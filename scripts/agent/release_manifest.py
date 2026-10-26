#!/usr/bin/env python
"""从**发布 zip** 生成 release-manifest.json（完整性清单，**不含签名**）（task-181/185）。

## 设计纠正（2026-10-27，人的要求）

> 「我本地需要在 Package 真实测试，真实的 key 你能发布的时候去掉吗」

- `Package/` 是人的**本地测试构建**目录，里面有真实 API key 是**故意的、必要的**；
- 发布物是 **zip**，不是 `Package/` 目录；
- ⇒ 清单必须**从 zip 条目生成**，门禁必须**校验 zip**（不校验 `Package/`）。

## 做什么

读 zip 里每个条目的解压后内容，算 sha256 + bytes，写出清单（规范化字节，可复现/可 diff）。
清单本身不放进 zip（自引用）；资产字段钉住**这一个 zip** 的 bytes/sha256。

## 不做（诚实边界）

**不签名、无公私钥、无 .sig** —— 人的裁决是"只保证发布包格式"。
清单不能防止「有意篡改 + 重算哈希」（无签名察觉不到）。

## 退出码契约（org.md B3-e）

    0 = 生成成功
    1 = 检查失败（如 zip 无 VERSION / VERSION 与 --version 不一致）
    2 = NOT_RUN（zip 不存在）
    3 = 用法错误

## 用法

    python scripts/agent/release_manifest.py \
        --zip artifacts/Memoria-v0.4.10-win64.zip --version 0.4.10
    # 输出默认写到 artifacts/Memoria-v0.4.10-win64.manifest.json
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from memoria.services.verify import manifest as mf  # noqa: E402

def _force_utf8_stdio():
    """Windows 旧代码页（cp1252/cp936）下 print 非 ASCII 会 UnicodeEncodeError ⇒ 假红。
    统一把 stdout/stderr 设为 UTF-8（errors=replace），保证门禁不会因为控制台编码崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdio()



def _read_zip_version(zip_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return zf.read("VERSION").decode("utf-8-sig").strip()
    except (KeyError, zipfile.BadZipFile, OSError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="从发布 zip 生成完整性清单（不含签名）")
    ap.add_argument("--zip", required=True, help="发布 zip 路径（清单的唯一来源）")
    ap.add_argument("--version", required=True, help="版本号（须与 zip 内 VERSION 一致）")
    ap.add_argument("--out", default="", help="清单输出路径（默认 <zip 同目录>/<zip 名>.manifest.json）")
    args = ap.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.is_file():
        print(f"[NOT_RUN] zip 不存在：{zip_path}", file=sys.stderr)
        return 2

    zip_version = _read_zip_version(zip_path)
    if zip_version is None:
        print(f"[FAIL] zip 内缺少可读的 VERSION 文件：{zip_path}", file=sys.stderr)
        return 1
    if zip_version != args.version:
        print(
            f"[FAIL] zip 内 VERSION({zip_version!r}) 与 --version({args.version!r}) 不一致",
            file=sys.stderr,
        )
        return 1

    try:
        manifest = mf.build_manifest_from_zip(
            zip_path=zip_path,
            version=args.version,
            asset_name=zip_path.name,
            asset_path=zip_path,
        )
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"[FAIL] 无法读取 zip 生成清单：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else zip_path.with_name(zip_path.stem + ".manifest.json")
    out.write_bytes(mf.canonical_bytes(manifest))

    print(f"[OK] 已生成 {out}")
    print(f"  文件数：{len(manifest['files'])}（来源：zip 条目，不是 Package/ 目录）")
    print(f"  版本：{manifest['version']}")
    a = manifest["asset"]
    print(f"  资产：{a['name']}（{a.get('bytes')} 字节，sha256 {str(a.get('sha256'))[:16]}…）")
    print()
    print("  提醒：本清单不含数字签名 ⇒ 只能校验格式与完整性，不能防止有意篡改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
