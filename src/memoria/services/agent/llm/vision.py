"""模型「收不收图」的能力表（本地新增；上游用 `ModelInfo.inputModalities`，本地只有一张按模型名的表）。

官方口径（2026-09-23 核对 `api-docs.deepseek.com/zh-cn/quick_start/pricing` 与 `/guides/vision`）：
- `deepseek-flash` = **支持**「图像理解」；
- `deepseek-v4-pro` = **不支持**（价格页明确写"不支持"）；
- 旧名 `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` **仍可调用**（请求由最新 Flash 服务）⇒ 也收图。

**fail-closed**：未收录的模型一律按"不收图"处理 —— 宁可在提交时给出可操作的提示，也不要把
`image_url` 块发出去等一个 400（上游同样在提交、切模型、`read_image` 三处设门禁；本地只做提交这一处）。
"""

from __future__ import annotations

#: 支持图像输入的模型名（小写比较；含官方仍接受的旧名）
IMAGE_INPUT_MODELS: frozenset[str] = frozenset(
    {
        "deepseek-flash",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
        "deepseek-v4.1-flash",
    }
)

#: 门禁错误码（与前端约定一致，见 `ui.agent_ask_start`）
CODE_NO_IMAGE_SUPPORT = "MODEL_DOES_NOT_SUPPORT_IMAGES"


def supports_image_input(model: str) -> bool:
    """该模型是否接受图片输入（未收录 ⇒ False）。"""
    name = (model or "").strip().lower()
    if not name:
        return False
    if name in IMAGE_INPUT_MODELS:
        return True
    # 端点常带厂商前缀（如 `deepseek/deepseek-flash`）⇒ 按最后一段再比一次
    return name.rsplit("/", 1)[-1] in IMAGE_INPUT_MODELS


def gate_message(model: str) -> str:
    """门禁不通过时给用户的可操作提示。"""
    return (
        f"当前模型（{model or '未配置'}）不支持图像输入：请换成 deepseek-flash 这类支持图像理解的模型，"
        "或去掉图片。"
    )
