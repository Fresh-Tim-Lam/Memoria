#!/usr/bin/env python
"""生成 release-manifest.json（完整性清单，**不含签名**）（task-181）。

## 做什么

扫描 `Package/`，为每个文件算 sha256 + bytes，写出 `release-manifest.json`。
清单随包发布，供发布门禁与客户端校验使用。

## 不做什么

**不签名、无公私钥、无 .sig** —— 人的裁决是"只保证发布包格式"。
因此本清单**不能防止有意篡改**（攻击者可替换文件并重算哈希）。
详见 `docs/design/release-format.md` §诚实边界。

## 退出码契约（org.md B3-e）

    0 = 生成成功
    1 = 检查失败（如版本不一致）
    2 = NOT_RUN（Package 不存在）
    3 = 用法错误

## 用法

    python scripts/agent/release_manifest.py --package Package --version 0.4.10
    python scripts/agent/release_manifest.py --package Package --version 0.4.10 \\
        --asset artifacts/Memoria-v0.4.10-win64-lite.zip
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from memoria.services.verify import manifest as mf  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="生成发布完整性清单（不含签名）")
    ap.add_argument("--package", default=str(REPO / "Package"), help="Package 目录")
    ap.add_argument("--version", required=True, help="版本号（须与 VERSION 一致）")
    ap.add_argument("--asset-name", default="", help="发布资产文件名")
    ap.add_argument("--asset", default="", help="发布 zip 路径（用于算 asset 的 bytes/sha256）")
    args = ap.parse_args()

    package = Path(args.package)
    if not package.is_dir():
        print(f"[NOT_RUN] Package 目录不存在：{package}", file=sys.stderr)
        return 2

    # 版本自检：VERSION 与参数不一致 ⇒ 拒绝生成（避免生成一份"自己就矛盾"的清单）
    version_file = package / "VERSION"
    if version_file.is_file():
        file_version = version_file.read_text(encoding="utf-8-sig").strip()
        if file_version != args.version:
            print(
                f"[FAIL] VERSION({file_version!r}) 与 --version({args.version!r}) 不一致",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"[FAIL] 缺少 {version_file}", file=sys.stderr)
        return 1

    asset_path = Path(args.asset) if args.asset else None
    if asset_path is not None and not asset_path.is_file():
        print(f"[NOT_RUN] 资产不存在：{asset_path}", file=sys.stderr)
        return 2

    manifest = mf.build_manifest(
        package_root=package,
        version=args.version,
        asset_name=args.asset_name or f"Memoria-v{args.version}-win64.zip",
        asset_path=asset_path,
    )

    out = package / mf.MANIFEST_NAME
    out.write_bytes(mf.canonical_bytes(manifest))

    print(f"✓ 已生成 {out}")
    print(f"  文件数：{len(manifest['files'])}")
    print(f"  版本：{manifest['version']}")
    if asset_path is not None:
        a = manifest["asset"]
        print(f"  资产：{a['name']}（{a.get('bytes')} 字节，sha256 {str(a.get('sha256'))[:16]}…）")
    print()
    print("  提醒：本清单不含数字签名 ⇒ 只能校验格式与完整性，不能防止有意篡改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
