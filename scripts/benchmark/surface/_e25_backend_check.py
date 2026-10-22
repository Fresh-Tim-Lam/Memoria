# -*- coding: utf-8 -*-
"""E25 后端证据：import_image 重构前后语义 + import_image_base64 新入口。

在临时 KB 上直接调 DocumentService（不碰用户知识库），验证：
  1. import_image(local_path) 仍然落盘 + 返回相对路径（既有调用方不破）
  2. import_image_base64 落盘、registry 语义不变（导入不写 registry，保存文档后才登记）
  3. 同一份内容重复粘贴 ⇒ MD5 去重，只有一份文件
  4. 非法 base64 / 非图片扩展名 / 超 20MB ⇒ 明确 error（不写盘）
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from memoria.services.document import DocumentService  # noqa: E402

# 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PzWvWQAAAABJRU5ErkJggg=="
)


def names(images_dir: str) -> list[str]:
    return sorted(os.listdir(images_dir)) if os.path.isdir(images_dir) else []


def main() -> int:
    ok = True
    tmp = tempfile.mkdtemp(prefix="memoria_e25_")
    kb = os.path.join(tmp, "kb")
    os.makedirs(os.path.join(kb, "docs"), exist_ok=True)
    with open(os.path.join(kb, "docs", "a.md"), "w", encoding="utf-8") as f:
        f.write("# A\n\nhello\n")
    svc = DocumentService(kb_path=kb)
    img_dir = svc.images_dir()

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + label + ("  " + detail if detail else ""))
        if not cond:
            ok = False

    # ── 1. 既有 import_image 路径（本地文件） ──
    src = os.path.join(tmp, "shot.png")
    with open(src, "wb") as f:
        f.write(PNG)
    r1 = svc.import_image(src)
    check("import_image ok", r1.get("status") == "ok" and r1.get("relPath", "").startswith(".memoria/images/"), json.dumps(r1, ensure_ascii=False))
    check("import_image deduped=false(首次)", r1.get("deduped") is False)
    r1b = svc.import_image(src)
    check("import_image 二次 ⇒ MD5 去重", r1b.get("deduped") is True and r1b.get("relPath") == r1.get("relPath"), json.dumps(r1b, ensure_ascii=False))
    check("磁盘只有 1 份", len(names(img_dir)) == 1, str(names(img_dir)))

    # ── 2. 新入口 import_image_base64（与 1 同内容 ⇒ 复用同一路径） ──
    b64 = base64.b64encode(PNG).decode("ascii")
    r2 = svc.import_image_base64("image.png", b64)
    check("base64 同内容 ⇒ 去重命中既有文件", r2.get("status") == "ok" and r2.get("deduped") is True and r2.get("relPath") == r1.get("relPath"), json.dumps(r2, ensure_ascii=False))
    check("磁盘仍只有 1 份", len(names(img_dir)) == 1, str(names(img_dir)))

    # ── 3. data URL 形式（前端读 FileReader 就是这个形状）+ 无扩展名文件名 ──
    other = PNG + b"\x00"  # 不同内容
    data_url = "data:image/png;base64," + base64.b64encode(other).decode("ascii")
    r3 = svc.import_image_base64("clipboard", data_url)
    check("data URL + 无扩展名 ⇒ 按 MIME 补 .png", r3.get("status") == "ok" and r3.get("name", "").endswith(".png") and r3.get("deduped") is False, json.dumps(r3, ensure_ascii=False))

    # ── 4. 错误口径 ──
    r4 = svc.import_image_base64("x.txt", b64)
    check("非图片扩展名 ⇒ error", r4.get("status") == "error", json.dumps(r4, ensure_ascii=False))
    r5 = svc.import_image_base64("x.png", "!!!not-base64!!!")
    check("非法 base64 ⇒ error", r5.get("status") == "error", json.dumps(r5, ensure_ascii=False))
    big = base64.b64encode(b"\x00" * (21 * 1024 * 1024)).decode("ascii")
    r6 = svc.import_image_base64("big.png", big)
    check(">20MB ⇒ error", r6.get("status") == "error" and "20" in (r6.get("message") or ""), json.dumps(r6, ensure_ascii=False))
    r7 = svc.import_image_base64("empty.png", "")
    check("空内容 ⇒ error", r7.get("status") == "error", json.dumps(r7, ensure_ascii=False))
    check("失败不写盘", len(names(img_dir)) == 2, str(names(img_dir)))

    # ── 5. registry 语义：导入不登记；保存引用该图片的文档后才登记 ──
    reg_path = os.path.join(img_dir, "registry.json")
    rel = r1["relPath"]
    svc.save_document("docs/a.md", "# A\n\n![alt](<%s>)\n" % rel)
    reg = json.load(open(reg_path, encoding="utf-8")) if os.path.exists(reg_path) else {}
    entry = os.path.basename(rel)
    check("保存文档后 registry 登记该图片", entry in (reg.get("refs") or {}), json.dumps(reg, ensure_ascii=False)[:300])
    check("registry 记录引用文档", "docs/a.md" in (reg.get("refs") or {}).get(entry, []), json.dumps(reg.get("refs", {}).get(entry), ensure_ascii=False))

    # ── 6. 未使用图片清理语义保持（引用后不再算 unused） ──
    unused = {u["name"] for u in svc.unused_images()}
    check("已引用图片不在 unused", entry not in unused, str(sorted(unused)))

    print("TMP_KB=" + kb)
    print("RESULT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
