#!/usr/bin/env python
"""从 `Package/` 构建**发布 zip**（剥离私有配置）+ 生成 zip 清单（task-185）。

## 为什么需要这个脚本（2026-10-27 事故的直接修复）

- `Package/` 是人的**本地测试构建**目录 ⟶ 里面可以有真实 API key / 本机设置（**故意保留**）；
- 发布物是 **zip** ⟶ 打包时必须把私有文件**剥离**，而不是要求人删掉自己的测试配置；
- 生成清单 / 发布门禁的对象都是 **zip**，不是 `Package/`。

## 打包规则（白名单式剥离）

```
顶层排除：logs/  cache/  __pycache__/  .git/
顶层文件排除：.gitkeep  frameless-ok.txt  window-diag.txt  release-manifest.json
config/ 只允许：config/README.txt（agent.json / ui-settings.json 等一律不进 zip）
lite 变体：再排除 hf/
```

## 双保险

打包后立刻对 **zip** 执行：结构校验（顶层 + config 白名单）→ 双向哈希（清单来自 zip）→
敏感内容扫描（`sk-…` / `"api_key": "<值>"` / 私有配置条目）。任一项失败 ⇒ exit 1，**删掉半成品 zip**。

## 退出码

    0 = zip 已生成并通过自检（清单同目录生成）
    1 = 自检失败（已删除 zip）
    2 = NOT_RUN（Package/ 不存在 / VERSION 读不到）
    3 = 用法错误

## 用法

    python packaging/make_release_zip.py --variant full --version 0.4.10 \
        --out artifacts/Memoria-v0.4.10-win64.zip
    python packaging/make_release_zip.py --variant lite --version 0.4.10 \
        --out artifacts/Memoria-v0.4.10-win64-lite.zip
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from memoria.services.verify import manifest as mf  # noqa: E402

#: 顶层目录 / 文件黑名单（无论变体都不进 zip）。
EXCLUDE_TOP_DIRS = frozenset({"logs", "cache", "__pycache__", ".git"})
EXCLUDE_TOP_FILES = frozenset(
    {".gitkeep", "frameless-ok.txt", "window-diag.txt", mf.MANIFEST_NAME}
)
#: `config/` 下唯一允许进 zip 的文件。
CONFIG_ALLOWED = "config/README.txt"
#: 固定 zip 内时间戳：同一份内容重复打包 ⇒ 字节稳定（便于复现与重传核对）。
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def select_entries(package: Path, *, variant: str) -> list[tuple[Path, str]]:
    """返回 [(磁盘文件, zip 内路径)]，已按规则剥离私有/运行时文件。"""
    entries: list[tuple[Path, str]] = []
    for path in sorted(package.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(package)
        parts = rel.parts
        if parts and parts[0] in EXCLUDE_TOP_DIRS:
            continue
        if len(parts) == 1 and parts[0] in EXCLUDE_TOP_FILES:
            continue
        if parts and parts[0] == "config" and rel.as_posix() != CONFIG_ALLOWED:
            continue  # 私有配置一律不进 zip
        if variant == "lite" and parts and parts[0] == "hf":
            continue
        entries.append((path, rel.as_posix()))
    return entries


def build_zip(package: Path, out: Path, *, variant: str) -> int:
    entries = select_entries(package, variant=variant)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for disk_path, arcname in entries:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, disk_path.read_bytes())
    return len(entries)


def _read_package_version(package: Path) -> str | None:
    vf = package / "VERSION"
    try:
        return vf.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None


def self_check(zip_path: Path, manifest: dict) -> mf.CheckResult:
    result = mf.CheckResult.pass_()
    result.extend(mf.verify_zip_layout(zip_path=zip_path, manifest=manifest))
    result.extend(mf.verify_zip(zip_path=zip_path, manifest=manifest))
    result.extend(mf._verify_zip_content_hashes(zip_path=zip_path, manifest=manifest))
    result.extend(mf.scan_zip_sensitive(zip_path=zip_path))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="构建发布 zip（剥离私有配置）+ 生成 zip 清单")
    ap.add_argument("--package", default=str(REPO / "Package"), help="Package 目录（本地测试构建）")
    ap.add_argument("--variant", required=True, choices=["full", "lite"])
    ap.add_argument("--version", default="", help="版本号（默认读 Package/VERSION）")
    ap.add_argument("--out", required=True, help="输出 zip 路径")
    ap.add_argument("--no-manifest", action="store_true", help="只打 zip，不生成清单")
    args = ap.parse_args()

    package = Path(args.package)
    if not package.is_dir():
        print(f"[NOT_RUN] Package 目录不存在：{package}", file=sys.stderr)
        return 2
    version = args.version or _read_package_version(package) or ""
    if not version:
        print(f"[NOT_RUN] 读不到 {package / 'VERSION'}", file=sys.stderr)
        return 2

    out = Path(args.out)
    try:
        count = build_zip(package, out, variant=args.variant)
    except OSError as exc:
        print(f"[FAIL] 打包失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    manifest = mf.build_manifest_from_zip(
        zip_path=out, version=version, asset_name=out.name, asset_path=out
    )
    result = self_check(out, manifest)
    if not result.ok:
        out.unlink(missing_ok=True)  # 半成品不得留下
        print(f"== 打包自检 FAIL（{len(result.failures)} 项）== zip 已删除", file=sys.stderr)
        for item in result.failures:
            print(f"  ✗ {item}", file=sys.stderr)
        return 1

    if not args.no_manifest:
        manifest_path = out.with_name(out.stem + ".manifest.json")
        manifest_path.write_bytes(mf.canonical_bytes(manifest))
        print(f"✓ 清单：{manifest_path}（{len(manifest['files'])} 条目，来源 zip）")
    print(f"✓ 发布 zip：{out}")
    print(f"  变体：{args.variant}  版本：{version}  条目：{count}")
    print(f"  资产 sha256：{manifest['asset'].get('sha256')}")
    print("  已校验包结构与完整性（不含数字签名）；私有 config 未随包。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
