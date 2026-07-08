"""语义检索前的文本归一化（算法化，非手工别名表）。"""

from __future__ import annotations

import re

_LATEX_CMD = re.compile(r"\\([a-zA-Z]+)")
_MATH_DELIM = re.compile(r"\$+")


def normalize_math_for_semantic(text: str) -> str:
    """将 LaTeX 数学标记转为可读 token，供 Embedding 编码。

    例如 ``$\\varepsilon$`` → ``varepsilon``，便于与英文查询 ``epsilon`` 在向量空间对齐。
    不做希腊字母手工映射；跨符号/跨语言主要依赖语义模型。
    """
    s = (text or "").strip()
    if not s:
        return ""
    s = _MATH_DELIM.sub(" ", s)
    s = _LATEX_CMD.sub(r" \1 ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()
