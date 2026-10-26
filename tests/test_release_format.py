"""发布包格式与完整性校验测试（task-181，**不含数字签名**）。

## 范围

人的裁决：「算了不管了，给厕所上锁，**保证发布包格式**就好了」
⇒ 只做格式 + 完整性（清单 + 门禁），**不做 Ed25519 / 公钥 / 签名**。

## 诚实边界（本方案的定位）

保护：格式错误 / 缺文件 / 多余文件 / zip 结构异常 / 传输损坏 / 下载不完整
**不保护：有意篡改**（攻击者可替换文件并重算清单哈希，无签名察觉不到）

⇒ 本文件里**不出现**"防篡改""安全""已签名"这类表述（见 `docs/design/release-format.md`）。
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from memoria.services.verify import manifest as mf


# ── 测试夹具 ───────────────────────────────────────────────────────────────


def _make_package(root: Path) -> None:
    """造一个结构合规的最小包。"""
    for d in ("lib", "resources", "config", "hf"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "Memoria.exe").write_bytes(b"MZ fake exe")
    (root / "VERSION").write_text("0.4.10\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"name": "Memoria", "version": "0.4.10"}), encoding="utf-8"
    )
    (root / "lib" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "resources" / "b.txt").write_text("hello\n", encoding="utf-8")
    (root / "config" / "ui-settings.json").write_text("{}\n", encoding="utf-8")


@pytest.fixture()
def pkg(tmp_path: Path) -> Path:
    root = tmp_path / "pkg"
    _make_package(root)
    return root


def _manifest(pkg: Path, asset_path: Path | None = None) -> dict:
    return mf.build_manifest(
        package_root=pkg,
        version="0.4.10",
        asset_name="a.zip",
        asset_path=asset_path,
        built_at="2026-10-26T00:00:00+00:00",
    )


def _make_zip(pkg: Path, zip_path: Path) -> Path:
    """把包目录压成 zip（条目集合 == 清单文件集合）。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in mf._iter_package_files(pkg):
            zf.write(path, mf.rel_posix(path, pkg))
    return zip_path


# ── ★ T-fmt-11【先证红】改清单里某 sha256 一位 ⇒ 回读必须红 ─────────────────


def test_T_fmt_11_tampered_manifest_hash_detected(pkg: Path) -> None:
    """**先证红**：清单里某文件 sha256 改一位 ⇒ 回读校验必须失败。

    若这条不红，说明"双向校验"根本没在工作 —— 整道门禁就是摆设。
    """
    manifest = _manifest(pkg)
    assert mf.verify_readback(package_root=pkg, manifest=manifest).ok, "正常包应通过"

    entry = next(f for f in manifest["files"] if f["path"] == "lib/a.py")
    original = entry["sha256"]
    entry["sha256"] = ("0" if original[0] != "0" else "1") + original[1:]

    result = mf.verify_readback(package_root=pkg, manifest=manifest)
    assert not result.ok, "sha256 改一位后回读必须失败"
    assert any("sha256" in f for f in result.failures), result.failures


# ── A. 结构 ────────────────────────────────────────────────────────────────


def test_T_fmt_1_missing_required_entry(pkg: Path) -> None:
    """缺必含条目 ⇒ 失败（门禁 exit 1）。"""
    manifest = _manifest(pkg)
    (pkg / "resources").rename(pkg / "resources-renamed")
    result = mf.verify_layout(package_root=pkg, manifest=manifest)
    assert not result.ok
    assert any("resources" in f for f in result.failures), result.failures


def test_layout_rejects_forbidden_entry(pkg: Path) -> None:
    """含禁止条目（logs/ 等运行时残留）⇒ 失败。"""
    (pkg / "logs").mkdir()
    (pkg / "logs" / "crash.log").write_text("boom\n", encoding="utf-8")
    manifest = _manifest(pkg)
    result = mf.verify_layout(package_root=pkg, manifest=manifest)
    assert not result.ok
    assert any("logs" in f for f in result.failures), result.failures


def test_layout_rejects_undeclared_top_level(pkg: Path) -> None:
    """顶层出现未声明的条目 ⇒ 失败。"""
    (pkg / "weird_dir").mkdir()
    manifest = _manifest(pkg)
    result = mf.verify_layout(package_root=pkg, manifest=manifest)
    assert not result.ok
    assert any("weird_dir" in f for f in result.failures), result.failures


# ── B. 双向 ────────────────────────────────────────────────────────────────


def test_T_fmt_2_extra_undeclared_file(pkg: Path) -> None:
    """包内多一个未声明文件 ⇒ 失败（防夹带）。"""
    manifest = _manifest(pkg)
    (pkg / "lib" / "smuggled.py").write_text("evil\n", encoding="utf-8")
    result = mf.verify_readback(package_root=pkg, manifest=manifest)
    assert not result.ok
    assert any("smuggled" in f for f in result.failures), result.failures


def test_declared_file_missing_from_package(pkg: Path) -> None:
    """清单声明了但包里没有 ⇒ 失败。"""
    manifest = _manifest(pkg)
    (pkg / "lib" / "a.py").unlink()
    result = mf.verify_readback(package_root=pkg, manifest=manifest)
    assert not result.ok
    assert any("不存在" in f for f in result.failures), result.failures


def test_size_mismatch_detected(pkg: Path) -> None:
    """字节数不符 ⇒ 失败（即使 sha256 被同步改对，大小也该抓）。"""
    manifest = _manifest(pkg)
    entry = next(f for f in manifest["files"] if f["path"] == "lib/a.py")
    entry["bytes"] = entry["bytes"] + 100
    result = mf.verify_readback(package_root=pkg, manifest=manifest)
    assert not result.ok
    assert any("大小" in f for f in result.failures), result.failures


# ── C. 版本一致性 ──────────────────────────────────────────────────────────


def test_T_fmt_3_version_mismatch(pkg: Path) -> None:
    """VERSION / manifest.version / 期望版本 三者不等 ⇒ 失败。"""
    manifest = _manifest(pkg)
    (pkg / "VERSION").write_text("0.4.9\n", encoding="utf-8")
    result = mf.verify_versions(package_root=pkg, manifest=manifest, expected_version="0.4.10")
    assert not result.ok
    assert any("VERSION" in f for f in result.failures), result.failures


def test_version_expected_mismatch(pkg: Path) -> None:
    """期望版本（release 标题）不符 ⇒ 失败。"""
    manifest = _manifest(pkg)
    result = mf.verify_versions(package_root=pkg, manifest=manifest, expected_version="9.9.9")
    assert not result.ok


def test_version_tolerates_utf8_bom(pkg: Path) -> None:
    """VERSION 带 UTF-8 BOM ⇒ 不得误报不一致。

    Windows 的 `Set-Content -Encoding UTF8` 会写 BOM；用 `utf-8` 读会把 `\\ufeff`
    留在串首 ⇒ 假报"版本不一致"（实测踩到）。
    """
    manifest = _manifest(pkg)
    (pkg / "VERSION").write_bytes("\ufeff0.4.10\n".encode("utf-8"))
    result = mf.verify_versions(package_root=pkg, manifest=manifest, expected_version="0.4.10")
    assert result.ok, result.failures


# ── D. zip 卫生 ────────────────────────────────────────────────────────────


def test_T_fmt_4_rezip_same_content_passes(pkg: Path, tmp_path: Path) -> None:
    """**只重新压缩（内容不变）⇒ 校验通过** —— 证明校验不绑死打包字节。

    这是关键区分：校验的是**内容**，不是**打包方式**。
    用不同压缩级别打包同一份内容，字节必然不同，但内容校验必须都通过。

    调用 `verify_package(..., check_asset_bytes=False)` —— 即"只校验内容、容忍重新打包"。
    （发布门禁会传 `True`，因为它必须钉住**即将发布的那一份确切资产**。）
    """
    manifest = _manifest(pkg)

    z_stored = tmp_path / "stored.zip"
    z_deflate = tmp_path / "deflate.zip"
    for path in mf._iter_package_files(pkg):
        rel = mf.rel_posix(path, pkg)
        with zipfile.ZipFile(z_stored, "a", zipfile.ZIP_STORED) as zf:
            zf.write(path, rel)
        with zipfile.ZipFile(z_deflate, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.write(path, rel)

    assert z_stored.read_bytes() != z_deflate.read_bytes(), "前提：两种压缩方式字节应不同"

    for z in (z_stored, z_deflate):
        result = mf.verify_package(z, manifest, check_asset_bytes=False)
        assert result.ok, f"{z.name} 内容相同应通过：{result.failures}"


def test_T_fmt_5_zip_content_byte_changed(pkg: Path, tmp_path: Path) -> None:
    """zip 内某文件改 1 字节 ⇒ 校验失败（内容哈希）。"""
    manifest = _manifest(pkg)
    z = _make_zip(pkg, tmp_path / "a.zip")

    # 用一个"内容不同但同名"的 zip 替换
    bad_pkg = tmp_path / "bad"
    _make_package(bad_pkg)
    (bad_pkg / "lib" / "a.py").write_text("print(2)\n", encoding="utf-8")
    bad_zip = _make_zip(bad_pkg, tmp_path / "bad.zip")

    result = mf._verify_zip_content_hashes(zip_path=bad_zip, manifest=manifest)
    assert not result.ok, "内容改了必须失败"
    assert any("sha256" in f for f in result.failures), result.failures


def test_T_fmt_6_zip_extra_file(pkg: Path, tmp_path: Path) -> None:
    """zip 里多塞一个未声明文件 ⇒ 校验失败（集合双向）。"""
    manifest = _manifest(pkg)
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for path in mf._iter_package_files(pkg):
            zf.write(path, mf.rel_posix(path, pkg))
        zf.writestr("lib/extra.py", "evil\n")

    result = mf.verify_zip(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("未在清单声明" in f for f in result.failures), result.failures


def test_T_fmt_7_zip_missing_file(pkg: Path, tmp_path: Path) -> None:
    """zip 里删一个文件 ⇒ 校验失败。"""
    manifest = _manifest(pkg)
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for path in mf._iter_package_files(pkg):
            if path.name == "a.py":
                continue
            zf.write(path, mf.rel_posix(path, pkg))

    result = mf.verify_zip(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("缺少清单声明的条目" in f for f in result.failures), result.failures


def test_T_fmt_8_zip_duplicate_entry(pkg: Path, tmp_path: Path) -> None:
    """同名重复条目 ⇒ 校验失败（zip 允许，但各解压器行为不一致）。"""
    manifest = _manifest(pkg)
    z = tmp_path / "dup.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for path in mf._iter_package_files(pkg):
            zf.write(path, mf.rel_posix(path, pkg))
    # 用 append 模式再写一次同名条目（形成重复）
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("lib/a.py", "print('dup')\n")

    result = mf.verify_zip(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("重复条目" in f for f in result.failures), result.failures


def test_T_fmt_9_zip_path_traversal(pkg: Path, tmp_path: Path) -> None:
    """路径穿越条目 `../evil` ⇒ 校验失败。"""
    manifest = _manifest(pkg)
    z = tmp_path / "trav.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for path in mf._iter_package_files(pkg):
            zf.write(path, mf.rel_posix(path, pkg))
        zf.writestr("../evil.txt", "pwned\n")

    result = mf.verify_zip(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("不安全路径" in f for f in result.failures), result.failures


def test_zip_absolute_path_rejected(pkg: Path, tmp_path: Path) -> None:
    """绝对路径条目 ⇒ 校验失败。"""
    manifest = _manifest(pkg)
    z = tmp_path / "abs.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for path in mf._iter_package_files(pkg):
            zf.write(path, mf.rel_posix(path, pkg))
        zf.writestr("/etc/passwd", "x\n")

    result = mf.verify_zip(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("不安全路径" in f for f in result.failures), result.failures


def test_T_fmt_10_zip_trailing_data(pkg: Path, tmp_path: Path) -> None:
    """EOCD 后追加尾随数据 ⇒ 校验失败。"""
    manifest = _manifest(pkg)
    z = _make_zip(pkg, tmp_path / "a.zip")
    # 在 zip 末尾追加垃圾数据
    z.write_bytes(z.read_bytes() + b"\x00TRAILING-JUNK" * 8)

    result = mf.verify_zip(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("尾随数据" in f for f in result.failures), result.failures


# ── 客户端统一入口 verify_package ──────────────────────────────────────────


def test_verify_package_accepts_good_directory(pkg: Path) -> None:
    manifest = _manifest(pkg)
    result = mf.verify_package(pkg, manifest, expected_version="0.4.10")
    assert result.ok, result.failures


def test_verify_package_rejects_bad_directory(pkg: Path) -> None:
    manifest = _manifest(pkg)
    (pkg / "lib" / "extra.py").write_text("x\n", encoding="utf-8")
    result = mf.verify_package(pkg, manifest)
    assert not result.ok


def test_verify_package_accepts_good_zip(pkg: Path, tmp_path: Path) -> None:
    z = _make_zip(pkg, tmp_path / "good.zip")
    manifest = _manifest(pkg, asset_path=z)
    result = mf.verify_package(z, manifest)
    assert result.ok, result.failures


def test_verify_package_detects_asset_sha_mismatch(pkg: Path, tmp_path: Path) -> None:
    """zip 被追加内容 ⇒ asset sha256 不符 ⇒ 失败。"""
    z = _make_zip(pkg, tmp_path / "good.zip")
    manifest = _manifest(pkg, asset_path=z)
    z.write_bytes(z.read_bytes() + b"JUNK")

    result = mf.verify_package(z, manifest)
    assert not result.ok
    assert any("资产" in f or "尾随" in f for f in result.failures), result.failures


def test_verify_package_missing_path(tmp_path: Path) -> None:
    result = mf.verify_package(tmp_path / "nope", {})
    assert not result.ok


# ── 规范化字节：可复现 / 可 diff（不是签名用途）────────────────────────────


def test_canonical_bytes_reproducible_across_key_order() -> None:
    """键序不同 ⇒ 规范化后字节相同（便于 review 时 diff）。"""
    a = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}
    b = {"nested": {"y": 25, "z": 26}, "a": 1, "b": 2}
    assert mf.canonical_bytes(a) == mf.canonical_bytes(b)
    assert b" " not in mf.canonical_bytes(a), "不得含空格"
    assert b"\r" not in mf.canonical_bytes(a), "不得含 CR（跨平台）"
    assert mf.canonical_bytes(a).endswith(b"\n"), "以单个 LF 结尾"


def test_canonical_bytes_survives_crlf_source() -> None:
    obj = {"k": "值"}
    crlf = json.dumps(obj, ensure_ascii=False).replace("\n", "\r\n")
    assert mf.canonical_bytes(json.loads(crlf)) == mf.canonical_bytes(obj)
