#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_link_fixture.py —— 为 A6 判别力自证造**含 resolved + broken wikilink 的临时 KB 副本**

纪律：**绝不污染 `tests/probe-kb` 或用户库**；一律复制到 `artifacts/_link_fixture_kb/`。

背景（task-32）：原生 probe-kb 里所有 wikilink 都指向不存在的页面（全 broken），
  没法验证「resolved 链接必须有 href」这条断言 ⇒ 必须造出 resolved 场景。
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "artifacts" / "_link_fixture_kb"

DOC = """# 链接夹具（A6 自证用）

## 已解析 wiki（目标**存在** ⇒ 必须有 href）

- [[03-block-boundaries]] 已存在（原 probe-kb 的文件主干）
- [[05-images]] 也存在
- [[README]] 也存在

## 未解析 wiki（目标**不存在** ⇒ 不应有 href，只要求 data-link-target）

- [[不存在的页面甲]]
- [[不存在的页面乙]]

## 普通 markdown 链接（必须有 href）

- [站内相对链接](./05-images.md)
- [外部链接](https://example.com/x)

## 残留检查

本段不含任何未解析的 wikilink 原始文本。
"""



def make(src_kb: Path, dest: Path = FIXTURE_DIR) -> dict:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, dest)

    (dest / "link-fixture.md").write_text(DOC, encoding="utf-8")
    # !! 不新增目标文档：wikilink 解析用的是 `get_link_targets()` 返回的
    #    resolved_targets（KP ids ∪ 文件主干），它是**启动时缓存的快照**，
    #    新加文件不会立刻进快照（实测 total 仍是原来的 11 项）。
    #    ⇒ 引用**已存在**的文件主干最稳（03-block-boundaries / 05-images / README）。

    return {
        "kb": str(dest),
        "file": "link-fixture.md",
        "resolvedTargets": ["03-block-boundaries", "05-images", "README"],
        "brokenTargets": ["不存在的页面甲", "不存在的页面乙"],
    }


if __name__ == "__main__":
    import json

    info = make(REPO_ROOT / "tests" / "probe-kb")
    print("[link-fixture] %s" % info["kb"])
    print("__LINKFIXTURE__" + json.dumps(info, ensure_ascii=False))
