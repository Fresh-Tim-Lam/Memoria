# -*- coding: utf-8 -*-
"""E25 文档图片资产「字节入口」单测（剪贴板粘贴图片，复用既有 `.memoria/images/` 链）。

被测对象：
- `DocumentService._import_image_bytes(name, data)`  核心（落盘 / MD5 去重 / 重名追加）
- `DocumentService.import_image(local_path)`         既有本地文件入口（只读文件后调核心）
- `DocumentService.import_image_base64(name, data)`  新增剪贴板入口（base64 / data URL）
- `UIAPI.import_image_base64(name, data)`            RPC 包装（与 import_image 同错误口径）

覆盖：
① 正常导入：文件落 `.memoria/images/`、返回库根相对路径、文档保存后 registry 登记；
② 重复导入同图（base64 与本地文件两条入口混用）⇒ MD5 去重：只有一份文件、返回同一路径；
③ 超 20MB ⇒ 明确 error（解码前拒绝、不写盘）；恰好上限 ⇒ 允许（解码后再核对字节数）；
④ 非法 base64 / 非图片扩展名 ⇒ 明确 error；
⑤ `import_image(local_path)` 既有行为回归（返回值、相对路径口径、去重语义不变）；
⑥ UIAPI RPC 契约（成功字段 / 错误 `{"status":"error","message":...}`）；
⑦ 未使用图片清理语义不变：导入未引用 ⇒ 出现在 unused；被文档引用后 ⇒ 不再算 unused。

运行：`python -m pytest tests/test_image_import_bytes.py -q`
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.document import DocumentService

# 1x1 PNG（真实图片字节：扩展名白名单 + MD5 去重都按字节判断，内容本身不校验图片结构）
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PzWvWQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG).decode("ascii")


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    (kb / "docs").mkdir(parents=True)
    (kb / "docs" / "a.md").write_text("# A\n\nhello\n", encoding="utf-8")
    return kb


def _svc(kb: Path) -> DocumentService:
    """不传 `kb_path=` 构造：避免打开库时的索引 / manifest 后台动作，单测只测图片链。"""
    svc = DocumentService()
    svc.kb_path = str(kb)
    return svc


def _image_names(svc: DocumentService) -> list[str]:
    """`.memoria/images/` 下的图片文件（registry.json 不是图片）。"""
    target = Path(svc.images_dir())
    if not target.is_dir():
        return []
    return sorted(
        p.name for p in target.iterdir() if p.is_file() and p.name != DocumentService._REGISTRY_FILE
    )


def _registry(svc: DocumentService) -> dict:
    path = Path(svc.images_dir()) / DocumentService._REGISTRY_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ── ① 正常导入：落盘 + 相对路径 + registry（保存引用后才登记） ────────────────


def test_base64_import_writes_file_and_returns_relpath(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)

    res = svc.import_image_base64("clip.png", PNG_B64)

    assert res["status"] == "ok"
    assert res["relPath"] == ".memoria/images/clip.png"
    assert res["name"] == "clip.png"
    assert res["deduped"] is False
    assert (Path(svc.images_dir()) / "clip.png").read_bytes() == PNG
    assert ".memoria/images/" in res["relPath"]  # 库根相对路径（含正斜杠）

    # registry 记录的是「图片 → 引用文档」：导入时尚未产生引用，保存引用该图片的文档后才登记。
    # 这与重构前 `import_image` 的语义完全一致（重构未改变 registry 写入时机）。
    save = svc.save_document("docs/a.md", "# A\n\n![clip](<%s>)\n" % res["relPath"])
    assert save["status"] == "ok"

    reg = _registry(svc)
    assert "clip.png" in reg.get("refs", {})
    assert "docs/a.md" in reg["refs"]["clip.png"]


def test_data_url_without_extension_gets_mime_extension(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)

    res = svc.import_image_base64(
        "clipboard",
        "data:image/png;base64," + base64.b64encode(PNG + b"\x00").decode("ascii"),
    )

    assert res["status"] == "ok"
    assert res["name"] == "clipboard.png"
    assert res["relPath"] == ".memoria/images/clipboard.png"
    assert res["deduped"] is False


# ── ② MD5 内容去重（两条入口共用同一条核心） ─────────────────────────────────


def test_duplicate_import_dedupes_to_single_file_and_same_path(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)

    local = tmp_path / "shot.png"
    local.write_bytes(PNG)

    r1 = svc.import_image(str(local))                        # 本地文件入口（首次落盘）
    r2 = svc.import_image_base64("pasted.png", PNG_B64)      # 剪贴板裸 base64
    r3 = svc.import_image_base64("pasted.png", "data:image/png;base64," + PNG_B64)  # data URL
    r4 = svc.import_image(str(local))                        # 本地文件再次导入

    assert [r["status"] for r in (r1, r2, r3, r4)] == ["ok"] * 4
    assert r1["relPath"] == ".memoria/images/shot.png"
    assert r2["relPath"] == r1["relPath"]
    assert r3["relPath"] == r1["relPath"]
    assert r4["relPath"] == r1["relPath"]
    assert [r["deduped"] for r in (r1, r2, r3, r4)] == [False, True, True, True]
    assert _image_names(svc) == ["shot.png"]  # 磁盘只有一份


# ── ③ 体积上限（解码前拦截；恰好上限仍可用） ─────────────────────────────────


def test_oversized_payload_rejected_before_write(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)
    limit = DocumentService._IMAGE_PASTE_MAX_BYTES

    big_b64 = base64.b64encode(b"\x00" * (limit + 1)).decode("ascii")
    res = svc.import_image_base64("big.png", big_b64)

    assert res["status"] == "error"
    assert "20MB" in res["message"]  # 明确错误，不静默截断
    assert _image_names(svc) == []   # 不写盘


def test_size_boundary_exact_limit_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """上限边界：恰好 ≤ 上限应通过（防止 base64 长度估算把 20MB 整图误拒）。"""
    kb = _make_kb(tmp_path)
    svc = _svc(kb)
    monkeypatch.setattr(DocumentService, "_IMAGE_PASTE_MAX_BYTES", 1024)

    exact = (PNG + b"\x00" * 1024)[:1024]
    ok = svc.import_image_base64("exact.png", base64.b64encode(exact).decode("ascii"))
    assert ok["status"] == "ok"
    assert (Path(svc.images_dir()) / "exact.png").stat().st_size == 1024

    over = svc.import_image_base64("over.png", base64.b64encode(b"\x00" * 1025).decode("ascii"))
    assert over["status"] == "error"
    assert _image_names(svc) == ["exact.png"]


# ── ④ 非法输入 ⇒ 明确 error ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "data", "needle"),
    [
        ("clip.png", "!!!not-base64!!!", "base64"),
        ("clip.png", "data:image/png;base64,@@@@", "base64"),
        ("clip.txt", PNG_B64, "格式"),
        ("clip", PNG_B64, "格式"),          # 无扩展名且非 data URL
        ("", "", "base64"),
    ],
)
def test_invalid_payload_rejected(
    tmp_path: Path, name: str, data: str, needle: str
) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)

    res = svc.import_image_base64(name, data)

    assert res["status"] == "error"
    assert res.get("message")
    assert needle in res["message"]
    assert _image_names(svc) == []


# ── ⑤ 既有 import_image(local_path) 回归 ─────────────────────────────────────


def test_import_image_local_path_regression(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)
    src = tmp_path / "屏幕截图 1.png"  # 中文 + 空格：既有链路支持，重构不得破坏
    src.write_bytes(PNG)

    r1 = svc.import_image(str(src))
    assert r1["status"] == "ok"
    assert r1["relPath"] == ".memoria/images/屏幕截图 1.png"
    assert r1["name"] == "屏幕截图 1.png"
    assert r1["deduped"] is False

    r2 = svc.import_image(str(src))
    assert r2["status"] == "ok"
    assert r2["relPath"] == r1["relPath"]
    assert r2["deduped"] is True
    assert _image_names(svc) == ["屏幕截图 1.png"]

    not_image = tmp_path / "note.txt"
    not_image.write_text("x", encoding="utf-8")
    assert svc.import_image(str(not_image))["status"] == "error"

    missing = svc.import_image(str(tmp_path / "nope.png"))
    assert missing["status"] == "error"
    assert "源文件不存在" in missing["message"]


# ── ⑥ RPC 契约（与 import_image 同风格） ─────────────────────────────────────


def test_ui_rpc_contract(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    api = UIAPI()                 # 不传 kb_path：不触发打开库的副作用
    api._svc.kb_path = str(kb)    # 直接给服务层指定临时库

    ok = api.import_image_base64("clip.png", PNG_B64)
    assert ok["status"] == "ok"
    assert {"status", "relPath", "name", "deduped"} <= set(ok)
    assert ok["relPath"] == ".memoria/images/clip.png"

    dup = api.import_image_base64("clip.png", PNG_B64)
    assert dup["status"] == "ok" and dup["deduped"] is True and dup["relPath"] == ok["relPath"]

    bad = api.import_image_base64("clip.png", "not base64!!")
    assert bad["status"] == "error"
    assert set(bad) == {"status", "message"}  # 前端按 message 显式报错


# ── ⑦ 未使用图片清理语义不变 ─────────────────────────────────────────────────


def test_unused_image_cleanup_semantics_unchanged(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    svc = _svc(kb)

    res = svc.import_image_base64("clip.png", PNG_B64)
    assert res["status"] == "ok"

    # 导入但未引用 ⇒ 出现在 unused（可被图片管理器清理）
    assert "clip.png" in {u["name"] for u in svc.unused_images()}

    # 文档引用并保存 ⇒ registry 登记 ⇒ 不再算 unused（不会被误删）
    svc.save_document("docs/a.md", "# A\n\n![clip](<%s>)\n" % res["relPath"])
    assert "clip.png" not in {u["name"] for u in svc.unused_images()}
    assert os.path.isfile(os.path.join(svc.images_dir(), "clip.png"))
