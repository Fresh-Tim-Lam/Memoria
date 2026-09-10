"""知识库 Agent 工具包分发（``<kb>/.memoria/agent/``）。

把随包内置资源（智能体指令 / 编撰规范 / 调度脚本 / README）复制到用户知识库的
隐藏目录 ``.memoria/agent/``，供 Trae 智能体读取与运行。

设计见 ``docs/design/kb-agent.md`` §2 / §7：
- 幂等：内容一致的已存在文件进入 ``skipped``；
- **永不覆盖** ``review/**``（复习状态属用户数据）；
- ``.memoria/`` 已被知识库扫描与「构建」跳过，故不影响内容/图谱/校验。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

KIT_VERSION = "1.0.0"
SPEC_VERSION = "1.0.0"
KIT_FILE = ".kit.json"
REVIEW_DIRNAME = "review"

# 内置资源名（resources/agent-prompts/）→ 知识库落点文件名（.memoria/agent/）
FILE_MAP: tuple[tuple[str, str], ...] = (
    ("kb-agent-readme.md", "README.md"),
    ("kb-agent.zh-CN.md", "prompt.zh-CN.md"),
    ("kb-spec.zh-CN.md", "kb-spec.zh-CN.md"),
    ("fsrs.py", "fsrs.py"),
)

# 来自 docs/reference 的随包文档 → 知识库落点（开发态读仓库，发布态读 resources/docs）。
# preview-formats.md 的目标读者含 Agent，需让 KB 内智能体可读（渲染写法权威）。
REFERENCE_DOCS: tuple[tuple[str, str], ...] = (
    ("preview-formats.md", "preview-formats.md"),
)


def agent_dir(kb_path: str) -> Path:
    """知识库的 agent 目录：``<kb>/.memoria/agent``。"""
    return Path(kb_path) / ".memoria" / "agent"


def _reference_doc_path(name: str) -> Path | None:
    """docs/reference 白名单文档定位（与 ``get_reference_doc`` 同源）。"""
    from memoria.app.runtime import is_frozen, repo_root, resources_dir

    if is_frozen():
        path = resources_dir() / "docs" / name
    else:
        path = repo_root() / "docs" / "reference" / name
    return path if path.is_file() else None


def _atomic_write(path: Path, data: bytes) -> None:
    """同目录临时文件 + fsync + os.replace（沿用仓库既有原子写约定）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _kit_payload() -> bytes:
    """``.kit.json``：**不含时间戳**，保证重复安装时内容一致（幂等）。"""
    payload = {
        "schema_version": 1,
        "agent_kit": KIT_VERSION,
        "spec": SPEC_VERSION,
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def install_kb_agent(kb_path: str | None) -> dict:
    """把内置工具包写入 ``<kb>/.memoria/agent/``；幂等且不触碰 ``review/**``。

    返回 ``{status, agent_dir, written[], skipped[], kit_version, spec_version, prompt}``。
    """
    if not kb_path or not os.path.isdir(kb_path):
        return {"status": "error", "message": "未打开知识库"}

    from memoria.app.runtime import resources_dir

    src_dir = resources_dir() / "agent-prompts"
    sources: list[tuple[str, Path]] = []  # (落点文件名, 源路径)
    missing: list[str] = []
    for src_name, dst_name in FILE_MAP:
        path = src_dir / src_name
        if path.is_file():
            sources.append((dst_name, path))
        else:
            missing.append(f"agent-prompts/{src_name}")
    for src_name, dst_name in REFERENCE_DOCS:
        path = _reference_doc_path(src_name)
        if path is None:
            missing.append(f"docs/reference/{src_name}")
        else:
            sources.append((dst_name, path))
    if missing:
        return {"status": "error", "message": "内置资源缺失: " + ", ".join(missing)}

    dest = agent_dir(kb_path)
    try:
        (dest / REVIEW_DIRNAME).mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        skipped: list[str] = []
        for dst_name, src_path in sources:
            data = src_path.read_bytes()
            target = dest / dst_name
            if target.is_file() and target.read_bytes() == data:
                skipped.append(dst_name)
                continue
            _atomic_write(target, data)
            written.append(dst_name)

        # 版本清单：内容一致则不重写（保持幂等）
        kit_path = dest / KIT_FILE
        kit_data = _kit_payload()
        if not (kit_path.is_file() and kit_path.read_bytes() == kit_data):
            _atomic_write(kit_path, kit_data)

        prompt = (dest / "prompt.zh-CN.md").read_text(encoding="utf-8")
    except OSError as e:
        return {"status": "error", "message": f"写入失败: {e}"}

    return {
        "status": "ok",
        "agent_dir": str(dest),
        "written": written,
        "skipped": skipped,
        "kit_version": KIT_VERSION,
        "spec_version": SPEC_VERSION,
        "prompt": prompt,
    }
