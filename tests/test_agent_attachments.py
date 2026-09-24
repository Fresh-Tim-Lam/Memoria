"""图像输入（2026-09-23）的契约钉子：附件落库/读回、线格式块数组、会话往返、模型门禁。

背景（人：「deepseek 的 flash 好像可以直接看图了，我们可以给对话栏接 window 文件拖拽，
这样就可以拖拽图片进去」）：

1. **日志只存引用**：`<kb>/.memoria/agent/attachments/` 落字节，会话日志只落 `rel_path`
   （**绝不落 base64**）——对齐上游"attachments 与日志分离"的核心原则。
2. **线格式**：官方口径是 Chat Completions 的 `content` 块数组（`image_url` + base64 data URL）；
   **纯文本消息必须逐字不变**（仍是 `{"role":…,"content":"…"}`），否则既有 wire 契约全线漂移。
3. **内容判定**：只认 JPEG/PNG/GIF/WebP，且**按文件签名**判定（不认文件名、也不认声明的 MIME）。
4. **模型门禁**：`deepseek-flash` 支持图像理解、`deepseek-v4-pro` 不支持；未收录一律按"不收图"（fail-closed）。
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from memoria.services.agent import attachments as att
from memoria.services.agent.llm.providers.openai_compatible import _message_to_wire
from memoria.services.agent.llm.types import ImagePart, Message, Role
from memoria.services.agent.llm.vision import supports_image_input

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# —— ① 内容判定与解码 ——


@pytest.mark.parametrize(
    ("data", "expected"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (GIF, "image/gif"), (WEBP, "image/webp")],
)
def test_sniff_media_type_by_content(data: bytes, expected: str) -> None:
    assert att.sniff_media_type(data) == expected


def test_sniff_media_type_rejects_non_images() -> None:
    assert att.sniff_media_type("# 标题\n正文".encode("utf-8")) is None
    assert att.sniff_media_type(b"") is None


def test_decode_base64_is_strict() -> None:
    assert att.decode_base64(_b64(PNG)) == PNG
    with pytest.raises(att.AttachmentError) as err:
        att.decode_base64("不是 base64!!")
    assert err.value.code == "INVALID_IMAGE_BASE64"
    with pytest.raises(att.AttachmentError):
        att.decode_base64("")


# —— ② 落库：去重 / 清洗 / 限长 ——


def test_save_image_dedupes_by_content(tmp_path: Path) -> None:
    first = att.save_image(tmp_path, "shot.png", PNG)
    second = att.save_image(tmp_path, "另一个名字.png", PNG)
    assert first["deduped"] is False and second["deduped"] is True
    assert first["rel_path"] == second["rel_path"]
    assert first["rel_path"].startswith(att.ATTACH_DIR + "/")
    files = list((tmp_path / att.ATTACH_DIR).iterdir())
    assert len(files) == 1  # 同内容只占一份盘


def test_save_image_sanitizes_and_limits(tmp_path: Path) -> None:
    saved = att.save_image(tmp_path, "../../evil name?.png", PNG)
    name = saved["rel_path"].rsplit("/", 1)[-1]
    assert ".." not in name and "?" not in name and " " not in name
    with pytest.raises(att.AttachmentError) as err:
        att.save_image(tmp_path, "big.png", PNG[:8] + b"\x00" * (att.MAX_IMAGE_BYTES + 1))
    assert err.value.code == "IMAGE_TOO_LARGE"
    with pytest.raises(att.AttachmentError) as err2:
        att.save_image(tmp_path, "note.md", "# 不是图片".encode("utf-8"))
    assert err2.value.code == "UNSUPPORTED_IMAGE_TYPE"


def test_normalize_only_accepts_the_attachment_dir() -> None:
    ok = att.normalize([{"rel_path": f"{att.ATTACH_DIR}/a.png", "media_type": "image/png", "name": "a"}])
    assert ok[0]["rel_path"].endswith("/a.png")
    for bad in (
        [{"rel_path": ".memoria/images/x.png"}],  # 别的目录：不走附件通道
        [{"rel_path": "../x.png"}],
        [{"rel_path": ""}],
        [{"rel_path": f"{att.ATTACH_DIR}/a.png", "media_type": "image/bmp"}],
        "not-a-list",
        [{"rel_path": f"{att.ATTACH_DIR}/a.png"}] * (att.MAX_IMAGES_PER_MESSAGE + 1),
    ):
        with pytest.raises(att.AttachmentError):
            att.normalize(bad)
    assert att.normalize(None) == [] and att.normalize([]) == []


def test_to_data_url_is_gated_by_content_and_scope(tmp_path: Path) -> None:
    saved = att.save_image(tmp_path, "ok.png", PNG)
    url = att.to_data_url(tmp_path, saved["rel_path"], "image/png")
    assert url.startswith("data:image/png;base64,") and _b64(PNG) in url
    (tmp_path / "note.md").write_text("# 文本", encoding="utf-8")
    assert att.to_data_url(tmp_path, "note.md") == ""  # 内容不是图片 ⇒ 不发
    assert att.to_data_url(tmp_path, "../外面.png") == ""
    assert att.to_data_url(tmp_path, "不存在.png") == ""
    # 声明与内容不一致 ⇒ 不猜（同上游 IMAGE_TYPE_MISMATCH 精神）
    assert att.to_data_url(tmp_path, saved["rel_path"], "image/jpeg") == ""


# —— ③ 线格式：纯文本逐字不变；有图才用块数组 ——


def test_text_only_wire_is_byte_identical() -> None:
    wire = _message_to_wire(Message(role=Role.USER, content="你好"))
    assert wire == {"role": "user", "content": "你好"}


def test_wire_uses_blocks_only_when_an_image_is_present() -> None:
    part = ImagePart(rel_path="a.png", media_type="image/png", data_url="data:image/png;base64,AAA")
    wire = _message_to_wire(Message(role=Role.USER, content="这是什么？", images=(part,)))
    assert wire["content"] == [
        {"type": "text", "text": "这是什么？"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
    ]
    # `data_url` 为空（文件缺失/越界）的图被跳过；只剩文本时**退回字符串**（不制造空块数组）
    wire2 = _message_to_wire(
        Message(role=Role.USER, content="只有文字", images=(ImagePart(rel_path="gone.png"),))
    )
    assert wire2["content"] == "只有文字"


def test_tool_and_assistant_messages_never_carry_blocks() -> None:
    """官方向量：`tool` 结果只收字符串 ⇒ 工具产出的图必须走"延迟 user 消息"，不能塞进 tool 消息。"""
    part = ImagePart(rel_path="a.png", media_type="image/png", data_url="data:image/png;base64,AAA")
    tool_wire = _message_to_wire(
        Message(role=Role.TOOL, content="done", tool_call_id="c1", name="read_image", images=(part,))
    )
    assert tool_wire["content"] == "done"


# —— ④ 会话往返：日志只落 rel_path，续聊时再读成 data URL ——


def test_history_and_hydration_round_trip(tmp_path: Path) -> None:
    from memoria.services.agent.session.history import _images

    saved = att.save_image(tmp_path, "pic.png", PNG)
    event = {
        "type": "user/message",
        "seq": 1,
        "data": {"text": "看图", "images": [{"rel_path": saved["rel_path"], "media_type": "image/png", "name": "pic.png"}]},
    }
    parts = _images(event)
    assert len(parts) == 1 and parts[0].rel_path == saved["rel_path"]
    assert parts[0].data_url == ""  # 回放阶段**不读盘**（日志里没有 base64）
    hydrated = att.hydrate_messages(tmp_path, [Message(role=Role.USER, content="看图", images=parts)])
    assert hydrated[0].images[0].data_url.startswith("data:image/png;base64,")
    # 不带图的消息**原样返回**（对象同一性不变，避免无谓复制）
    plain = Message(role=Role.USER, content="纯文本")
    assert att.hydrate_messages(tmp_path, [plain])[0] is plain
    # 坏形状的 images 一律跳过，不抛
    assert _images({"type": "user/message", "data": {"images": ["x", {"no": 1}]}}) == ()


# —— ⑤ 模型门禁 ——


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("deepseek-flash", True),
        ("deepseek-v4-flash", True),
        ("deepseek-v4-flash-vision-exp", True),
        ("deepseek/deepseek-flash", True),
        ("DeepSeek-Flash", True),
        ("deepseek-v4-pro", False),
        ("gpt-4o-mini", False),
        ("", False),
    ],
)
def test_supports_image_input(model: str, expected: bool) -> None:
    assert supports_image_input(model) is expected
