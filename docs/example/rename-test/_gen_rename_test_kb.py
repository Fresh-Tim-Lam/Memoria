"""生成 rename-test 测试知识库（docs/example/rename-test/）。可重复执行（会先清空重建）。"""

import base64
import os
import re
import sys

sys.path.insert(0, os.path.abspath("src"))
import yaml  # noqa: E402

from memoria.storage.manifest import build_manifest_entries, save_manifest  # noqa: E402

KB = os.path.abspath("docs/example/rename-test")
MIRROR = os.path.join(KB, ".memoria", "sidecars")
IMGDIR = os.path.join(KB, ".memoria", "images")
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def rm_tree(path):
    if os.path.isdir(path):
        for name in os.listdir(path):
            p = os.path.join(path, name)
            rm_tree(p) if os.path.isdir(p) else os.remove(p)
        os.rmdir(path)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def write_md(rel, lines):
    path = os.path.join(KB, rel)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_sidecar(rel, kps, links):
    data = {"schema_version": 1, "file": rel, "knowledge_points": [], "links": [], "edges": []}
    for kp in kps:
        row = {"id": kp["id"], "name": kp["name"]}
        if kp.get("aliases"):
            row["aliases"] = kp["aliases"]
        if kp.get("tags"):
            row["tags"] = kp["tags"]
        row["range"] = {
            "start": {"snippet": kp["start_snippet"], "line_hint": kp["start_line"]},
            "end": {"snippet": kp["end_snippet"], "line_hint": kp["end_line"]},
        }
        data["knowledge_points"].append(row)
    for ln in links:
        data["links"].append(
            {
                "anchor_text": ln["anchor_text"],
                "targets": ln["targets"],
                "edge_type": "reference",
                "instances": [ln["line"]],
                "source_id": ln["source_id"],
            }
        )
    # sidecar 镜像命名：<md 所在目录>/<文件stem>.memoria.yaml（与运行时 sidecar_path_for 一致）
    rel_dir, base = os.path.split(rel)
    stem = os.path.splitext(base)[0]
    path = os.path.join(MIRROR, rel_dir, stem + ".memoria.yaml")
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def kp_range(lines, start_line, heading, end_line):
    return {
        "start_line": start_line,
        "start_snippet": heading,
        "end_line": end_line,
        "end_snippet": lines[end_line - 1].strip(),
    }


def find_wikilinks(lines):
    """扫描 [[key]]/[[key|label]]（跳过 [[\\ 字样式命令）。返回 [{key, line}]。"""
    out = []
    pat = re.compile(r"\[\[([^\]\\|#]+)(?:\|[^\]]*)?\]\]")
    for i, line in enumerate(lines, start=1):
        for m in pat.finditer(line):
            key = m.group(1).strip()
            if key:
                out.append({"key": key, "line": i})
    return out


def links_for(lines, kp_id, scope_start=1, scope_end=None):
    scope_end = scope_end or len(lines)
    res = []
    for w in find_wikilinks(lines):
        if scope_start <= w["line"] <= scope_end:
            res.append(
                {
                    "anchor_text": w["key"],
                    "targets": [w["key"]],
                    "line": w["line"],
                    "source_id": kp_id,
                }
            )
    return res


# ── 重建 ──
if os.path.isdir(KB):
    rm_tree(KB)
ensure_dir(KB)
ensure_dir(MIRROR)
ensure_dir(IMGDIR)
with open(os.path.join(IMGDIR, "dot.png"), "wb") as f:
    f.write(base64.b64decode(PNG_B64))

# 1) 根文档 guide.md（KP 在标题行，范围=全文件）
g = [
    "## 重命名测试 · 入口",
    "",
    "本库用于验证 Memoria 的文件/文件夹重命名自维护。根目录文档，可跳转到任意层级：",
    "",
    "- 链接 A：[[kp-note-a|笔记A]]",
    "- 链接 B：[[kp-note-b|笔记B]]",
    "- 深链：[[kp-note-c|深层笔记C]]",
    "- 纯文件引用：[[plain|纯文件参考]]",
    "- 图：![点图](.memoria/images/dot.png \"width=60\")",
    "- 文件（md 相对路径，自根目录指向 alpha 内文档）：[A 文档](alpha/note-a.md)",
    "",
    "> 说明：`alpha/` 文件夹重命名后，上述 md 相对路径链接按当前实现不自动改写（已知边界）。",
]
write_md("guide.md", g)
write_sidecar(
    "guide.md",
    [
        {
            "id": "kp-guide",
            "name": "重命名测试 · 入口",
            "tags": ["测试", "入口"],
            **kp_range(g, 1, "## 重命名测试 · 入口", len(g)),
        }
    ],
    links_for(g, "kp-guide"),
)

# 2) alpha/note-a.md（两级目录 · 单 KP · 别名）
a = [
    "## 笔记A 核心",
    "",
    "alpha/note-a 的核心知识：验证重命名文件后其 sidecar 镜像与跳转目标跟随。",
    "",
    "引用：[[kp-note-b|笔记B主题]]。",
]
write_md("alpha/note-a.md", a)
write_sidecar(
    "alpha/note-a.md",
    [
        {
            "id": "kp-note-a",
            "name": "笔记A 核心",
            "aliases": ["笔记甲"],
            "tags": ["测试", "A"],
            **kp_range(a, 1, "## 笔记A 核心", len(a)),
        }
    ],
    links_for(a, "kp-note-a"),
)

# 3) alpha/note-b.md（同目录多文件 · 单文件多 KP）
b = [
    "## 笔记B 主题",
    "",
    "alpha/note-b 的主题段落：验证一个文档含多个知识点。",
    "",
    "回链：[[kp-note-a|笔记A核心]]。",
    "",
    "## 笔记B 扩展",
    "",
    "同文件的第二个 KP，验证多 KP 文件的 range 绑定。",
]
write_md("alpha/note-b.md", b)
write_sidecar(
    "alpha/note-b.md",
    [
        {"id": "kp-note-b", "name": "笔记B 主题", "tags": ["测试", "B"], **kp_range(b, 1, "## 笔记B 主题", 5)},
        {"id": "kp-note-b2", "name": "笔记B 扩展", "tags": ["测试", "B2"], **kp_range(b, 7, "## 笔记B 扩展", len(b))},
    ],
    links_for(b, "kp-note-b", 1, 5),
)

# 4) beta/deep/note-c.md（三级目录）
c = [
    "## 深层笔记C",
    "",
    "beta/deep 下的深层文档：验证三级目录结构的文件夹重命名。",
    "",
    "回链 A：[[kp-note-a|笔记A核心]]；回链 B：[[kp-note-b|笔记B主题]]。",
    "",
    "图：![点图](.memoria/images/dot.png \"width=60\")",
]
write_md("beta/deep/note-c.md", c)
write_sidecar(
    "beta/deep/note-c.md",
    [
        {"id": "kp-note-c", "name": "深层笔记C", "tags": ["测试", "深层"], **kp_range(c, 1, "## 深层笔记C", len(c))}
    ],
    links_for(c, "kp-note-c"),
)

# 5) beta/plain.md（纯文件 · 无 sidecar · stem=plain 供文件重命名引用改写测试）
write_md(
    "beta/plain.md",
    [
        "# 纯文件说明",
        "",
        "该文件没有知识点与 sidecar（文件树显示 📝 无侧车标记）。",
        "其它文档通过 [[plain]] 引用它——文件重命名时应把该引用改写为新 stem。",
    ],
)

# 6) 空目录（验证空目录/无 md 目录的文件夹重命名）
ensure_dir(os.path.join(KB, "empty-dir"))

# 7) manifest 基线（保证打开即一致）
save_manifest(KB, build_manifest_entries(KB))

print("KB generated at:", KB)
