"""聊天图片附件的落库与读回（本地新增；对应上游的 `ctx.attachments` 内容寻址服务）。

**本地取舍（口径写进 `docs/design/dsh-agent-port.md §6.27`）**：上游把图片字节存进独立的内容寻址仓库、
消息只带不透明 `attachmentId`；本地没有那套服务，改为落进**知识库** `<kb>/.memoria/agent/attachments/`、
消息只带**库内相对路径**（`rel_path`）。核心原则不变 —— **日志只存引用、不存 base64**；引用形态换成
"随库走的相对路径"：换机/备份都在，既有 `/files/<rel_path>` 静态路由可直接显示，而且**不进**
`.memoria/images/**` 的图片注册表（不会被图片管理器与"未使用图片清理"误伤）。

官方口径（2026-09-23 核对 api-docs.deepseek.com/guides/vision）：
- 支持的格式只有 **JPEG / PNG / GIF / WebP**，且**按文件内容判定**（不认文件名、也不认声明的 MIME）；
- 图片以 base64 `data:` URL 内联进 `image_url` 内容块，计入 **48 MiB** 请求体上限。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from pathlib import Path
from typing import Any

#: 附件目录（库内相对路径，正斜杠）——在既定的"随库走、非事实源"区 `.memoria/agent/**` 下
ATTACH_DIR = ".memoria/agent/attachments"
#: 允许的媒体类型（与官方四种一致）
MEDIA_TYPES: tuple[str, ...] = ("image/jpeg", "image/png", "image/gif", "image/webp")
#: 单图上限（对齐上游 `DEFAULT_MAX_IMAGE_BYTES`）
MAX_IMAGE_BYTES = 5 * 1024 * 1024
#: 每条消息最多几张（对齐上游 `DEFAULT_MAX_IMAGES_PER_MESSAGE`）
MAX_IMAGES_PER_MESSAGE = 20

_EXT_BY_MEDIA = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
#: 文件名清洗：只留 ASCII 字母数字、点、横线、下划线与中日韩汉字（其余折成 `-`）
_SAFE_NAME = re.compile(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+")


class AttachmentError(Exception):
    """附件相关的**可展示**错误；`code` 与前端约定一致（见 `ui.agent_attach_image`）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sniff_media_type(data: bytes) -> str | None:
    """按**内容**判定图片类型；不认识返回 `None`（官方口径：不认文件名/MIME）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_base64(data: str) -> bytes:
    """严格 base64 解码（对齐上游 `INVALID_IMAGE_BASE64` 的严格口径）。"""
    text = (data or "").strip()
    if not text:
        raise AttachmentError("INVALID_IMAGE_BASE64", "图片数据为空")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttachmentError("INVALID_IMAGE_BASE64", f"图片数据不是合法的 base64：{exc}") from exc


def safe_name(name: str) -> str:
    """清洗文件名：去目录成分与控制字符、截断 40 字符（对齐上游"显示名清洗"的意图）。"""
    raw = os.path.basename((name or "").replace("\\", "/")).strip()
    cleaned = _SAFE_NAME.sub("-", raw).strip("-. ")
    return (cleaned or "image")[:40]


def save_image(kb_path: str | Path, name: str, data: bytes) -> dict[str, Any]:
    """落库：`<kb>/.memoria/agent/attachments/<sha8>-<原名干><ext>`。

    **按内容去重**：摘要相同 ⇒ 直接复用既有文件（`deduped=True`），不重复占盘、不改动已存在的文件。
    """
    if not data:
        raise AttachmentError("INVALID_IMAGE_BASE64", "图片数据为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise AttachmentError(
            "IMAGE_TOO_LARGE", f"单张图片不能超过 {MAX_IMAGE_BYTES // (1024 * 1024)} MiB"
        )
    media_type = sniff_media_type(data)
    if media_type is None:
        raise AttachmentError(
            "UNSUPPORTED_IMAGE_TYPE", "只支持 JPEG / PNG / GIF / WebP 四种图片（按文件内容判定）"
        )
    digest = hashlib.sha256(data).hexdigest()[:8]
    stem = Path(safe_name(name)).stem or "image"
    folder = Path(kb_path) / ATTACH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    # **按内容去重**：先看附件目录里有没有同摘要的文件（名字里带摘要前缀）；有就**原样复用**，
    # 不再按"摘要 + 本次文件名"另存一份 —— 否则同一张图换个文件名就会被存两份（2026-09-23 修）。
    existing = sorted(folder.glob(f"{digest}-*"))
    if existing:
        file_name = existing[0].name
        deduped = True
    else:
        file_name = f"{digest}-{stem}{_EXT_BY_MEDIA[media_type]}"
        deduped = False
    rel_path = f"{ATTACH_DIR}/{file_name}"
    path = folder / file_name
    if not deduped:
        path.write_bytes(data)
    return {
        "rel_path": f"{ATTACH_DIR}/{file_name}",
        "media_type": media_type,
        "name": (name or file_name),
        "bytes": len(data),
        "deduped": deduped,
    }


def _kb_relative(rel_path: str) -> str:
    """库内相对路径的**唯一**准入判据：非空、非绝对、无 `..` 段。"""
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return ""
    return rel


def is_attachment_path(rel_path: str) -> bool:
    """是否落在**附件目录**里 —— `normalize()` 的准入判据（聊天附件只认自己那一格）。"""
    rel = _kb_relative(rel_path)
    return bool(rel) and rel.startswith(ATTACH_DIR + "/")


def to_data_url(kb_path: str | Path, rel_path: str, media_type: str = "") -> str:
    """读回成 `data:` URL（发给模型用）。

    两个调用方、同一道安全闸：
    - **聊天附件**（`turn_images` / `hydrate_messages`）：路径已在 `normalize()` 里限定在附件目录；
    - **`read_image` 工具**：允许任意**库内**图片（`.memoria/images/x.png` 等），这正是该工具的语义。

    安全闸 = ① 必须在库内（非绝对、无 `..`）；② **内容必须嗅探成图片**（`sniff_media_type`）——
    所以即使传进来一个文本文件，也只会被跳过，绝不会把非图片内容 base64 出去。
    越界、缺失、内容不是图片一律返回 `""` ⇒ 调用方跳过该图（宁可不发，也不发坏块）。
    """
    rel = _kb_relative(rel_path)
    if not rel:
        return ""
    path = Path(kb_path) / rel
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    sniffed = sniff_media_type(data)
    if sniffed is None:
        return ""
    media = media_type if media_type in MEDIA_TYPES else sniffed
    if media != sniffed:
        return ""  # 声明与内容不一致（同上游 IMAGE_TYPE_MISMATCH 的精神）：不猜，直接跳过
    return f"data:{media};base64,{base64.b64encode(data).decode('ascii')}"


def normalize(items: Any) -> list[dict[str, str]]:
    """把 RPC 传来的附件清单规范化成 `[{rel_path, media_type, name}]`；坏形状抛 `AttachmentError`。

    只做**形状与准入**校验（是否真在附件目录、数量上限）；字节是否合法由 `save_image` 负责。
    """
    if items in (None, "", []):
        return []
    if not isinstance(items, (list, tuple)):
        raise AttachmentError("BAD_FIELD", "附件列表必须是数组")
    if len(items) > MAX_IMAGES_PER_MESSAGE:
        raise AttachmentError(
            "TOO_MANY_IMAGES", f"一条消息最多 {MAX_IMAGES_PER_MESSAGE} 张图片"
        )
    out: list[dict[str, str]] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise AttachmentError("BAD_FIELD", "附件项必须是对象")
        rel = str(raw.get("rel_path") or "").strip()
        if not rel or not is_attachment_path(rel):
            raise AttachmentError("BAD_FIELD", f"附件路径必须落在 {ATTACH_DIR}/ 下：{rel or '(空)'}")
        media = str(raw.get("media_type") or "").strip()
        if media and media not in MEDIA_TYPES:
            raise AttachmentError("BAD_FIELD", f"不支持的图片类型：{media}")
        out.append({"rel_path": rel, "media_type": media, "name": str(raw.get("name") or "")})
    return out


def turn_images(kb_path: str | Path, items: Any) -> tuple[Any, ...]:
    """把本轮附件清单转成带 `data_url` 的 `ImagePart` 元组（供 `loop.run(..., images=…)`）。

    空清单 ⇒ 空元组（`Message.images` 保持 `()`，wire 层也就不会改成块数组）。
    """
    from memoria.services.agent.llm.types import ImagePart

    parts = []
    for item in normalize(items):
        parts.append(
            ImagePart(
                rel_path=item["rel_path"],
                media_type=item["media_type"],
                name=item["name"],
                data_url=to_data_url(kb_path, item["rel_path"], item["media_type"]),
            )
        )
    return tuple(parts)


def hydrate_messages(kb_path: str | Path, messages: Any) -> list[Any]:
    """把回放出来的历史消息里**带图**的那些补上 `data_url`（续聊时图片要重新读，日志里只有路径）。

    只有真的带 `images` 的消息才会被复制成新对象；其余**原样返回**（对象同一性不变）。
    """
    from dataclasses import replace

    from memoria.services.agent.llm.types import ImagePart

    out: list[Any] = []
    for message in (messages or ()):
        parts = getattr(message, "images", ()) or ()
        if not parts:
            out.append(message)
            continue
        out.append(
            replace(
                message,
                images=tuple(
                    ImagePart(
                        rel_path=part.rel_path,
                        media_type=part.media_type,
                        name=part.name,
                        data_url=part.data_url or to_data_url(kb_path, part.rel_path, part.media_type),
                    )
                    for part in parts
                ),
            )
        )
    return out
