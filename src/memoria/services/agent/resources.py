"""聊天拖入**文档资源**（PDF / Word / TXT / Markdown）的落库与解析（2026-10-13）。

对齐图片附件（`attachments.py`）的同款取舍：
- 落点 = 知识库 `<kb>/.memoria/agent/attachments/resources/`（图片附件的**子目录**，图片/文档分开）；
- 消息只带**库内相对路径**（`rel_path`），日志不落 base64；
- **按内容去重**（同摘要直接复用）；
- 已在 KB 根目录下的文件**不复制**，直接引用原 `rel_path`（见 `reference_kb_file`）。

解析**按读时**做（不预先抽文本）：`extract_text` 读文件、pdf/docx→`markitdown`（转 Markdown、保留表格/标题）、txt/md→原样。
依赖**惰性导入**（只在真解析时 import），未装库时返回可展示的 `PARSER_MISSING`，不影响应用启动。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from pathlib import Path
from typing import Any

#: 资源子目录（库内相对路径，正斜杠）——图片附件的子目录，同处 `.memoria/agent/**` 非事实源区
RESOURCE_DIR = ".memoria/agent/attachments/resources"
#: 扩展名（小写）→ kind；「等等」后续在此追加
EXT_BY_KIND: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
}
#: 单文件上限（文档比图片大，放宽到 20 MiB）
MAX_RESOURCE_BYTES = 20 * 1024 * 1024
#: 单条消息最多引用几个资源（对齐图片的 20 上限，宽松）
MAX_RESOURCES_PER_MESSAGE = 20

#: 文件名清洗：只留 ASCII 字母数字、点、横线、下划线与中日韩汉字（其余折成 `-`）
_SAFE_NAME = re.compile(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+")


class ResourceError(Exception):
    """资源相关的**可展示**错误；`code` 与前端约定一致。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def decode_base64(data: str) -> bytes:
    """严格 base64 解码（同 `attachments.decode_base64` 口径）。"""
    text = (data or "").strip()
    if not text:
        raise ResourceError("INVALID_RESOURCE_DATA", "资源数据为空")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ResourceError("INVALID_RESOURCE_DATA", f"资源数据不是合法的 base64：{exc}") from exc


def safe_name(name: str) -> str:
    """清洗文件名（同 `attachments.safe_name` 口径）：去目录成分、截断 40 字符。"""
    raw = os.path.basename((name or "").replace("\\", "/")).strip()
    cleaned = _SAFE_NAME.sub("-", raw).strip("-. ")
    return (cleaned or "resource")[:40]


def _kb_relative(rel_path: str) -> str:
    """库内相对路径的**唯一**准入判据：非空、非绝对、无 `..` 段。"""
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return ""
    return rel


def is_resource_path(rel_path: str) -> bool:
    """是否落在**资源子目录**里。"""
    rel = _kb_relative(rel_path)
    return bool(rel) and rel.startswith(RESOURCE_DIR + "/")


def save_resource(kb_path: str | Path, name: str, data: bytes) -> dict[str, Any]:
    """落库：`<kb>/.memoria/agent/attachments/resources/<sha8>-<原名干><ext>`。按内容去重。"""
    if not data:
        raise ResourceError("INVALID_RESOURCE_DATA", "资源数据为空")
    if len(data) > MAX_RESOURCE_BYTES:
        raise ResourceError("RESOURCE_TOO_LARGE", f"资源文件不能超过 {MAX_RESOURCE_BYTES // (1024 * 1024)} MiB")
    ext = Path(safe_name(name)).suffix.lower()
    kind = EXT_BY_KIND.get(ext)
    if kind is None:
        raise ResourceError("UNSUPPORTED_RESOURCE_TYPE", "只支持 PDF / Word(.docx) / TXT / Markdown")
    digest = hashlib.sha256(data).hexdigest()[:8]
    stem = Path(safe_name(name)).stem or "resource"
    folder = Path(kb_path) / RESOURCE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob(f"{digest}-*"))
    if existing:
        file_name = existing[0].name
        deduped = True
    else:
        file_name = f"{digest}-{stem}{ext}"
        deduped = False
    rel_path = f"{RESOURCE_DIR}/{file_name}"
    if not deduped:
        (folder / file_name).write_bytes(data)
    return {"rel_path": rel_path, "name": name or file_name, "kind": kind, "bytes": len(data), "deduped": deduped}


def reference_kb_file(kb_path: str | Path, rel_path: str) -> dict[str, Any]:
    """引用 KB 内**已有**文件（不复制）：校验路径在库内、是受支持的资源类型。"""
    rel = _kb_relative(rel_path)
    if not rel:
        raise ResourceError("BAD_PATH", "资源路径非法")
    path = Path(kb_path) / rel
    if not path.is_file():
        raise ResourceError("NOT_FOUND", f"库内文件不存在：{rel}")
    kind = EXT_BY_KIND.get(path.suffix.lower())
    if kind is None:
        raise ResourceError("UNSUPPORTED_RESOURCE_TYPE", "只支持 PDF / Word(.docx) / TXT / Markdown")
    return {"status": "ok", "rel_path": rel, "name": path.name, "kind": kind, "in_kb": True, "deduped": False}


def _extract_via_markitdown(path: Path) -> str:
    """pdf/docx → markitdown 转 Markdown（保留表格/标题/列表结构）。惰性导入；读本地文件用 `convert_local`。"""
    try:
        from markitdown import MarkItDown
    except ImportError:
        raise ResourceError("PARSER_MISSING", "文档解析依赖 markitdown 未安装（pip install 'markitdown[pdf, docx]'）") from None
    try:
        md = MarkItDown()
        result = md.convert_local(str(path))
        text = getattr(result, "markdown", None) or getattr(result, "text_content", None) or ""
    except Exception as exc:
        raise ResourceError("PARSE_FAILED", f"解析失败：{exc}") from exc
    return text.strip()


def extract_text(kb_path: str | Path, rel_path: str) -> str:
    """读资源并解析成 Markdown：pdf/docx→markitdown（保留表格/标题）、txt/md→原样。资源子目录与 KB 内文件都能读。"""
    rel = _kb_relative(rel_path)
    if not rel:
        raise ResourceError("BAD_PATH", "资源路径非法")
    path = Path(kb_path) / rel
    if not path.is_file():
        raise ResourceError("NOT_FOUND", f"资源不存在：{rel}")
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return path.read_bytes().decode("utf-8", errors="replace")
    if ext in (".pdf", ".docx"):
        return _extract_via_markitdown(path)
    raise ResourceError("UNSUPPORTED_RESOURCE_TYPE", f"不支持的资源类型：{ext or '(无扩展名)'}")
