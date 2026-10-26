#!/usr/bin/env python
"""发布包格式门禁：保证**发出去的 zip** 符合格式（task-181/185，不含数字签名）。

## 人的要求（2026-10-27 设计纠正）

> 「我本地需要在 Package 真实测试，真实的 key 你能发布的时候去掉吗」

- 发布物是 **zip**，不是 `Package/` 目录；`Package/` 是人的本地测试构建（可以有真实 key）。
- ⇒ 门禁**只校验 zip**，**绝不扫描 `Package/`**（扫它必然误报人的测试 key）。

## 检查项（A–E，任一不满足 ⇒ exit 1，硬失败，不降级 WARN）

| 项 | 内容 |
|---|---|
| A 结构 | zip 顶层恰为 required ∪ optional；必含齐全；禁止条目不得存在；`config/` 只允许 README.txt |
| B 双向 | 清单每个条目在 zip 中都存在且 sha256/bytes 一致；zip 里每个条目都被清单声明（无夹带） |
| C 一致 | zip 内 `VERSION` == `manifest.version` == `--expect-version`（release 标题版本） |
| D zip 卫生 | 无同名重复条目 / 无路径穿越 / 条目集合==清单 / 无 EOCD 尾随数据 |
| E 敏感内容 | zip 内出现私有配置（config/agent.json、config/ui-settings.json）或 `sk-…` key 形态 ⇒ 失败（只报路径，不打印内容） |

## ⚠️ 诚实边界

本门禁保护：格式错误 / 缺文件 / 多余文件 / zip 结构异常 / 传输损坏 / 下载不完整 /
**不小心把人的私有配置或 key 打进发布包**。
**不保护有意篡改** —— 攻击者可替换文件并重算哈希；无签名察觉不到。
⇒ 对外表述只能是「**已校验包结构与完整性（不含数字签名）**」。

## 退出码契约（org.md B3-e）

    0 = 全部检查已执行且通过
    1 = 执行了但有检查失败
    2 = NOT_RUN（前置条件缺失，如 zip/manifest 不存在 —— **不等于通过**）
    3 = 用法错误

## 用法

    python scripts/agent/release_format_gate.py \
        --zip artifacts/Memoria-v0.4.10-win64.zip --expect-version 0.4.10
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from memoria.services.verify import manifest as mf  # noqa: E402

DEFAULT_MANIFEST_SUFFIX = ".manifest.json"


def default_manifest_path(zip_path: Path) -> Path:
    """约定：清单与 zip 同目录，名字为 `<zip 名去掉 .zip>.manifest.json`。"""
    return zip_path.with_name(zip_path.stem + DEFAULT_MANIFEST_SUFFIX)


def _zip_version(zip_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return zf.read("VERSION").decode("utf-8-sig").strip()
    except (KeyError, zipfile.BadZipFile, OSError):
        return None


def run_checks(
    *,
    zip_path: Path,
    manifest_path: Path | None = None,
    expect_version: str = "",
) -> mf.CheckResult:
    """对**一个发布 zip** 执行 A–E 检查并汇总。"""
    result = mf.CheckResult.pass_()

    if not zip_path.is_file():
        return mf.CheckResult.fail(f"发布 zip 不存在：{zip_path}")

    if manifest_path is None:
        manifest_path = default_manifest_path(zip_path)
    if not manifest_path.is_file():
        return mf.CheckResult.fail(
            f"缺少清单 {manifest_path}（发布前先跑 release_manifest.py --zip {zip_path.name}）"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return mf.CheckResult.fail(f"清单无法解析：{exc}")

    # A 结构（顶层 + config 白名单）
    result.extend(mf.verify_zip_layout(zip_path=zip_path, manifest=manifest))
    # B 双向 + D zip 卫生
    result.extend(mf.verify_zip(zip_path=zip_path, manifest=manifest))
    # B 内容哈希
    result.extend(mf._verify_zip_content_hashes(zip_path=zip_path, manifest=manifest))
    # E 敏感内容（只扫 zip）
    result.extend(mf.scan_zip_sensitive(zip_path=zip_path))

    # C 版本一致：zip VERSION / manifest.version / 期望版本
    zip_v = _zip_version(zip_path)
    manifest_v = manifest.get("version")
    if zip_v is None:
        result.ok = False
        result.failures.append("zip 中缺少可读的 VERSION 文件")
    elif zip_v != manifest_v:
        result.ok = False
        result.failures.append(f"zip VERSION({zip_v!r}) 与 manifest.version({manifest_v!r}) 不一致")
    if expect_version and manifest_v != expect_version:
        result.ok = False
        result.failures.append(
            f"manifest.version({manifest_v!r}) 与期望版本({expect_version!r}) 不一致"
        )

    # 资产钉住：清单登记的 zip bytes/sha256 必须与这一个 zip 一致
    asset = manifest.get("asset") or {}
    if asset.get("bytes") and asset["bytes"] != zip_path.stat().st_size:
        result.ok = False
        result.failures.append(
            f"资产大小不符：清单={asset['bytes']} 实际={zip_path.stat().st_size}"
            "（若重新打包请重跑 release_manifest.py）"
        )
    if asset.get("sha256"):
        actual = mf.sha256_file(zip_path)
        if actual != asset["sha256"]:
            result.ok = False
            result.failures.append(
                f"资产 sha256 不符：清单={asset['sha256']} 实际={actual}"
                "（该 zip 不是清单登记的那一份；若只是重新打包请重跑 release_manifest.py）"
            )

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="发布包格式门禁（校验 zip，不含签名）")
    ap.add_argument("--zip", required=True, help="要校验的发布 zip（门禁对象）")
    ap.add_argument("--manifest", default="", help="清单路径（默认 <zip 名>.manifest.json）")
    ap.add_argument("--expect-version", default="", help="期望版本（release 标题版本）")
    args = ap.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.is_file():
        print(f"[NOT_RUN] zip 不存在：{zip_path}", file=sys.stderr)
        return 2
    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(zip_path)

    result = run_checks(
        zip_path=zip_path,
        manifest_path=manifest_path,
        expect_version=args.expect_version,
    )

    if not result.ok:
        print(f"== 发布包格式校验 FAIL（{len(result.failures)} 项）==", file=sys.stderr)
        for item in result.failures:
            print(f"  ✗ {item}", file=sys.stderr)
        return 1

    print("== 发布包格式校验 PASS ==")
    print("  已校验包结构与完整性（不含数字签名）")
    print(f"  zip：{zip_path}")
    print(f"  清单：{manifest_path}")
    if args.expect_version:
        print(f"  版本：{args.expect_version}（zip VERSION / manifest / 期望 三方一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
