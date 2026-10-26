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
    """造一个结构合规的最小包（**config/ 只放 README**：私有配置绝不进 zip）。"""
    for d in ("lib", "resources", "config", "hf"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "Memoria.exe").write_bytes(b"MZ fake exe")
    (root / "VERSION").write_text("0.4.10\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"name": "Memoria", "version": "0.4.10"}), encoding="utf-8"
    )
    (root / "lib" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "resources" / "b.txt").write_text("hello\n", encoding="utf-8")
    (root / "config" / "README.txt").write_text("config lives in LOCALAPPDATA\n", encoding="utf-8")


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


# ── 2026-10-27 设计纠正（task-185）：清单/门禁对象是 **zip**，不是 Package/ ──
#
# 人的要求：「我本地需要在 Package 真实测试，真实的 key 你能发布的时候去掉吗」
# ⇒ Package/ 可以有真实 key（故意的）；zip 必须干净；清单从 zip 条目生成；门禁只扫 zip。


def _load_gate_module():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "agent" / "release_format_gate.py"
    spec = importlib.util.spec_from_file_location("_test_release_format_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zip_from(pkg: Path, out: Path, *, extra: dict[str, bytes] | None = None,
              drop: set[str] | None = None, skip_hf: bool = False) -> Path:
    drop = drop or set()
    extra = extra or {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in mf._iter_package_files(pkg):
            rel = mf.rel_posix(path, pkg)
            if rel in drop or rel in extra or (skip_hf and rel.startswith("hf/")):
                continue
            zf.write(path, rel)
        for name, data in extra.items():
            zf.writestr(name, data)
    return out


def test_manifest_from_zip_lists_exact_entries(pkg: Path, tmp_path: Path) -> None:
    """清单必须从 zip 条目生成：条目集合与哈希都和 zip 一致。"""
    z = _zip_from(pkg, tmp_path / "a.zip")
    manifest = mf.build_manifest_from_zip(
        zip_path=z, version="0.4.10", asset_name="a.zip", asset_path=z
    )
    with zipfile.ZipFile(z) as zf:
        names = {i.filename for i in zf.infolist() if not i.is_dir()}
    assert {f["path"] for f in manifest["files"]} == names
    assert manifest["version"] == "0.4.10"
    assert manifest["asset"]["sha256"] == mf.sha256_file(z)
    assert isinstance(manifest["layout"]["forbidden_entries"], list)


def test_zip_layout_rejects_private_config(pkg: Path, tmp_path: Path) -> None:
    """zip 的 config/ 只允许 README.txt：含 agent.json ⇒ A 结构失败。"""
    z = _zip_from(pkg, tmp_path / "leak.zip", extra={"config/agent.json": b'{"api_key":"x"}'})
    manifest = mf.build_manifest_from_zip(zip_path=z, version="0.4.10")
    result = mf.verify_zip_layout(zip_path=z, manifest=manifest)
    assert not result.ok
    assert any("config" in f for f in result.failures), result.failures


def test_scan_zip_sensitive_detects_sk_key(pkg: Path, tmp_path: Path) -> None:
    """zip 内任意文件含 `sk-…` 形态 ⇒ 构建/发布必须失败。"""
    z = _zip_from(pkg, tmp_path / "key.zip", extra={"resources/b.txt": b"key=sk-FAKEabcdefghijklmnop1234\n"})
    result = mf.scan_zip_sensitive(zip_path=z)
    assert not result.ok
    assert any("API key" in f for f in result.failures), result.failures


def test_scan_zip_sensitive_detects_api_key_assignment(pkg: Path, tmp_path: Path) -> None:
    """JSON 里出现 `"api_key": "<长值>"` ⇒ 失败（不打印内容）。"""
    z = _zip_from(
        pkg, tmp_path / "json.zip",
        extra={"lib/agent.json": b'{"base_url":"https://x","api_key":"abcdef1234567890"}'},
    )
    result = mf.scan_zip_sensitive(zip_path=z)
    assert not result.ok
    assert any("API key" in f for f in result.failures), result.failures


def test_scan_zip_sensitive_allows_plain_setting_name(pkg: Path, tmp_path: Path) -> None:
    """应用代码里引用配置键名 `api_key`（无赋值/无 sk-）不得误报。

    为什么不能无差别扫字面量 `api_key`：应用自身设置代码大量引用这个键名
    （`src/memoria/services/agent/llm/config.py` 等），无差别扫会误报所有版本。
    """
    z = _zip_from(
        pkg, tmp_path / "code.zip",
        extra={"lib/settings.py": b"def get(self):\n    return self._data['api_key']\n"},
    )
    result = mf.scan_zip_sensitive(zip_path=z)
    assert result.ok, result.failures


def test_gate_accepts_clean_full_and_lite_zips(pkg: Path, tmp_path: Path) -> None:
    """full（含 hf）与 lite（无 hf）两种干净 zip 都应通过门禁。"""
    gate = _load_gate_module()
    full = _zip_from(pkg, tmp_path / "Memoria-v0.4.10-win64.zip")
    lite = _zip_from(pkg, tmp_path / "Memoria-v0.4.10-win64-lite.zip", skip_hf=True)
    for z in (full, lite):
        manifest = mf.build_manifest_from_zip(
            zip_path=z, version="0.4.10", asset_name=z.name, asset_path=z
        )
        mpath = z.with_name(z.stem + ".manifest.json")
        mpath.write_bytes(mf.canonical_bytes(manifest))
        result = gate.run_checks(zip_path=z, manifest_path=mpath, expect_version="0.4.10")
        assert result.ok, (z.name, result.failures)


def test_gate_rejects_key_injected_zip(pkg: Path, tmp_path: Path) -> None:
    """**证红**：人为把含真 key 的 config/agent.json 塞进 zip ⇒ 门禁必须 FAIL。"""
    gate = _load_gate_module()
    z = _zip_from(
        pkg, tmp_path / "Memoria-v0.4.10-win64.zip",
        extra={"config/agent.json": b'{"api_key":"sk-FAKEabcdefghijklmnop1234"}'},
    )
    manifest = mf.build_manifest_from_zip(
        zip_path=z, version="0.4.10", asset_name=z.name, asset_path=z
    )
    mpath = z.with_name(z.stem + ".manifest.json")
    mpath.write_bytes(mf.canonical_bytes(manifest))
    result = gate.run_checks(zip_path=z, manifest_path=mpath, expect_version="0.4.10")
    assert not result.ok
    assert any("config" in f or "API key" in f for f in result.failures), result.failures


def test_packer_strips_private_config_but_package_keeps_it(tmp_path: Path) -> None:
    """**证红/证绿两条**（task-185 ⑤）：

    · Package/config 里放真 key，正常打包 ⇒ zip 内无它、扫描通过（人的本地测试不被破坏）；
    · 人为把它塞进 zip ⇒ 门禁 FAIL。
    """
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    pkg = tmp_path / "Package"
    _make_package(pkg)
    (pkg / "config" / "agent.json").write_text(
        json.dumps({"api_key": "sk-FAKEabcdefghijklmnop1234"}), encoding="utf-8"
    )
    out = tmp_path / "artifacts" / "Memoria-v0.4.10-win64-lite.zip"
    proc = subprocess.run(
        [sys.executable, str(repo / "packaging" / "make_release_zip.py"),
         "--package", str(pkg), "--variant", "lite", "--version", "0.4.10",
         "--out", str(out)],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "config/agent.json" not in names, "私有配置不得进 zip"
    assert "config/ui-settings.json" not in names
    assert (pkg / "config" / "agent.json").is_file(), "打包不得删除人的本地测试 key"

    gate = _load_gate_module()
    manifest = json.loads(out.with_name(out.stem + ".manifest.json").read_text(encoding="utf-8"))
    assert gate.run_checks(
        zip_path=out, manifest_path=out.with_name(out.stem + ".manifest.json"),
        expect_version="0.4.10",
    ).ok
    assert mf.scan_zip_sensitive(zip_path=out).ok

    # 人为把私有文件塞进 zip ⇒ 必红
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(out) as src, zipfile.ZipFile(bad, "w") as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info.filename))
        dst.writestr("config/agent.json", (pkg / "config" / "agent.json").read_bytes())
    bad_manifest = mf.build_manifest_from_zip(
        zip_path=bad, version="0.4.10", asset_name=bad.name, asset_path=bad
    )
    bad_mpath = bad.with_name(bad.stem + ".manifest.json")
    bad_mpath.write_bytes(mf.canonical_bytes(bad_manifest))
    result = gate.run_checks(zip_path=bad, manifest_path=bad_mpath, expect_version="0.4.10")
    assert not result.ok
    assert any("config" in f or "API key" in f for f in result.failures), result.failures

