#!/usr/bin/env python
"""发布包格式门禁：保证**发出去的包一定符合格式**（task-181，不含数字签名）。

## 人的要求

> 「算了不管了，给厕所上锁，**保证发布包格式**就好了」

⇒ 正确实现：**发布门禁发现包不合格式，就发不出去** —— 不是"发出去后再检查"。

## 检查项（A–E，任一不满足 ⇒ exit 1，硬失败，不降级 WARN）

| 项 | 内容 |
|---|---|
| A 结构 | 顶层恰为 required ∪ optional；必含齐全；禁止条目不得存在 |
| B 双向 | 清单每个文件都在且 sha256/bytes 一致；包内每个文件都被声明（无夹带） |
| C 一致 | `VERSION` == `manifest.version` == `--expect-version`（release 标题版本） |
| D zip 卫生 | 无同名重复条目 / 无路径穿越 / 条目集合==清单 / 无 EOCD 尾随数据 |
| E | 任一不过 ⇒ exit 1 |

## ⚠️ 诚实边界

本门禁保护：格式错误 / 缺文件 / 多余文件 / zip 结构异常 / 传输损坏 / 下载不完整。
**不保护有意篡改** —— 攻击者可替换文件并重算清单哈希，本方案察觉不到（无签名）。
⇒ 对外表述只能是「**已校验包结构与完整性（不含数字签名）**」。

## 退出码契约（org.md B3-e）

    0 = 全部检查已执行且通过
    1 = 执行了但有检查失败
    2 = NOT_RUN（前置条件缺失，如 Package 不存在 —— **不等于通过**）
    3 = 用法错误

## 用法

    python scripts/agent/release_format_gate.py --package Package --expect-version 0.4.10
    python scripts/agent/release_format_gate.py --zip artifacts/Memoria-v0.4.10-win64.zip
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from memoria.services.verify import manifest as mf  # noqa: E402


def run_checks(
    *,
    package: Path | None = None,
    zip_path: Path | None = None,
    manifest_path: Path | None = None,
    expect_version: str = "",
) -> mf.CheckResult:
    """执行 A–D 检查并汇总。"""
    result = mf.CheckResult.pass_()

    # 清单来源：显式路径 > Package/ 下的 > zip 同目录的
    if manifest_path is None:
        if package is not None:
            manifest_path = package / mf.MANIFEST_NAME
        elif zip_path is not None:
            manifest_path = zip_path.parent / mf.MANIFEST_NAME
    if manifest_path is None or not manifest_path.is_file():
        return mf.CheckResult.fail(
            f"缺少 {mf.MANIFEST_NAME}（发布前必须先跑 release_manifest.py 生成清单；"
            f"或显式给 --manifest <路径>）"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return mf.CheckResult.fail(f"{mf.MANIFEST_NAME} 无法解析：{exc}")

    if package is not None:
        result.extend(mf.verify_layout(package_root=package, manifest=manifest))
        result.extend(mf.verify_readback(package_root=package, manifest=manifest))
        result.extend(
            mf.verify_versions(
                package_root=package, manifest=manifest, expected_version=expect_version
            )
        )

    if zip_path is not None:
        result.extend(mf.verify_zip(zip_path=zip_path, manifest=manifest))
        result.extend(mf._verify_zip_content_hashes(zip_path=zip_path, manifest=manifest))
        # 发布门禁**必须**钉住确切的那一份资产字节（发出去的正是这个文件）。
        # 若清单未登记 asset.sha256（只做内容校验的场景），则跳过而非失败。
        asset = manifest.get("asset") or {}
        if asset.get("sha256"):
            actual = mf.sha256_file(zip_path)
            if actual != asset["sha256"]:
                result.ok = False
                result.failures.append(
                    f"zip 资产 sha256 不符：清单={asset['sha256']} 实际={actual}"
                    "（该 zip 不是清单登记的那一份；若只是重新打包请重跑 release_manifest.py）"
                )
        if asset.get("bytes") and asset["bytes"] != zip_path.stat().st_size:
            result.ok = False
            result.failures.append(
                f"zip 资产大小不符：清单={asset['bytes']} 实际={zip_path.stat().st_size}"
            )

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="发布包格式门禁（task-181）")
    ap.add_argument("--package", default="", help="Package 目录（校验目录形态）")
    ap.add_argument("--zip", default="", help="发布 zip（校验 zip 形态）")
    ap.add_argument("--manifest", default="", help="显式清单路径（默认 Package/release-manifest.json）")
    ap.add_argument("--expect-version", default="", help="期望版本（release 标题版本）")
    args = ap.parse_args()

    package = Path(args.package) if args.package else None
    zip_path = Path(args.zip) if args.zip else None
    manifest_path = Path(args.manifest) if args.manifest else None

    if not package and not zip_path:
        print("[用法错误] 至少给 --package 或 --zip 之一", file=sys.stderr)
        return 3

    if package is not None and not package.is_dir():
        print(f"[NOT_RUN] Package 目录不存在：{package}", file=sys.stderr)
        return 2
    if zip_path is not None and not zip_path.is_file():
        print(f"[NOT_RUN] zip 不存在：{zip_path}", file=sys.stderr)
        return 2

    result = run_checks(
        package=package,
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
    if package is not None:
        print(f"  目录：{package}")
    if zip_path is not None:
        print(f"  zip：{zip_path}")
    if args.expect_version:
        print(f"  版本：{args.expect_version}（VERSION / manifest / 期望 三方一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
