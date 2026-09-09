"""维护机制基准 · 受控知识库生成器（deterministic, 见 docs/design/maintenance-benchmark.md）。

用法（仓库根）：
  python scripts/benchmark/maintenance/gen_maintenance_kb.py --out artifacts/_bench_maintenance/kb --files 200
默认档：约 200 文件 / 600 KP / 混合根·两级·三级目录 / links+tags+别名；可复现（同参两次输出一致）。
默认不含图片与 embedding（--images 可选开启小图 1x1 PNG）。
"""

import argparse
import base64
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
while not os.path.isfile(os.path.join(ROOT, "src", "memoria", "__version__.py")):
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

import yaml  # noqa: E402

from memoria.storage.manifest import build_manifest_entries, save_manifest  # noqa: E402

PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
SEG = ["正文填充内容，用于基准语料稳定且具唯一性的段落文本。",
       "这里出现一个指向其它知识点的跳转锚点，供链接解析与图谱构建负载。",
       "附加说明行：保持与上下文一致的说明性句子内容。"]
PATTERNS = ["", "d1", "d2", "d1/d1a", "d2/d2a", "d3/d3a/deep", "d1"]


def rm_tree(p):
    if os.path.isdir(p):
        for n in os.listdir(p):
            q = os.path.join(p, n)
            rm_tree(q) if os.path.isdir(q) else os.remove(q)
        os.rmdir(p)


def kp_range(lines, start_line, end_line):
    return {
        "start_line": start_line,
        "start_snippet": lines[start_line - 1],
        "end_line": end_line,
        "end_snippet": lines[end_line - 1].strip(),
    }


def gen(out, files, seed, images):
    if os.path.isdir(out):
        rm_tree(out)
    os.makedirs(out)
    mirror = os.path.join(out, ".memoria", "sidecars")
    os.makedirs(mirror)
    if images:
        imgdir = os.path.join(out, ".memoria", "images")
        os.makedirs(imgdir)
        with open(os.path.join(imgdir, "dot.png"), "wb") as f:
            f.write(base64.b64decode(PNG_B64))

    # 1) 计划：文件列表（rel, dirpattern）与全库 KP id
    plan = []
    kp_ids = []
    for i in range(files):
        rel_dir = PATTERNS[i % len(PATTERNS)]
        name = "f_%05d.md" % i
        rel = "%s/%s" % (rel_dir, name) if rel_dir else name
        per = 2 + (i % 3)  # 2/3/4 个 KP/文件
        kps = []
        for j in range(per):
            kp_id = "k_%06d" % len(kp_ids)
            kp_ids.append(kp_id)
            kps.append({"id": kp_id, "rel": rel, "j": j})
        plan.append({"rel": rel, "kps": kps})

    id_by_rel = {p["rel"]: [k["id"] for k in p["kps"]] for p in plan}

    # 2) 逐文件生成正文 + sidecar
    link_count = 0
    for p in plan:
        lines = []
        rel = p["rel"]
        for k in p["kps"]:
            heading = "## KP %s" % k["id"]
            k["start_line"] = len(lines) + 1
            lines.append(heading)
            # 唯一性 token 进入末行，保证 end snippet 唯一
            tok = "%s-%d" % (k["id"], (seed + k["j"]) % 97)
            lines.append("")
            lines.append(SEG[0] + " " + tok)
            lines.append("")
            # 一部分文件放一条指向其它文件的跳转
            if (len(id_by_rel[rel]) and (len(kp_ids) - len(id_by_rel[rel])) > 0) and (k["j"] % 2 == 0):
                other_ids = [x for other, ids in id_by_rel.items() if other != rel for x in ids]
                target = other_ids[(seed + len(lines)) % len(other_ids)]
                lines.append("跳转：[[%s|%s]]。" % (target, target))
            else:
                lines.append(SEG[1] + " " + tok)
            lines.append("")
            lines.append(SEG[2] + " " + tok)
            k["end_line"] = len(lines)
        md = os.path.join(out, rel)
        os.makedirs(os.path.dirname(md), exist_ok=True)
        with open(md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        kps_side = []
        links = []
        for k in p["kps"]:
            row = {"id": k["id"], "name": "KP " + k["id"]}
            if k["j"] % 3 == 0:
                row["aliases"] = ["别名-" + k["id"]]
            row["tags"] = ["基准", "域%d" % (k["j"] % 5)]
            rng = kp_range(lines, k["start_line"], k["end_line"])
            row["range"] = {
                "start": {"snippet": rng["start_snippet"], "line_hint": rng["start_line"]},
                "end": {"snippet": rng["end_snippet"], "line_hint": rng["end_line"]},
            }
            kps_side.append(row)
        pat = re.compile(r"\[\[([^\]\\|#]+)(?:\|[^\]]*)?\]\]")
        for n, ln in enumerate(lines, start=1):
            for m in pat.finditer(ln):
                tgt = m.group(1).strip()
                links.append({
                    "anchor_text": tgt,
                    "targets": [tgt],
                    "edge_type": "reference",
                    "instances": [n],
                    "source_id": next((kk["id"] for kk in reversed(p["kps"]) if kk["start_line"] <= n), p["kps"][0]["id"]),
                })
                link_count += 1
        sc_path = os.path.join(mirror, os.path.relpath(md, out)[:-3] + ".memoria.yaml")
        os.makedirs(os.path.dirname(sc_path), exist_ok=True)
        with open(sc_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"schema_version": 1, "file": rel, "knowledge_points": kps_side, "links": links, "edges": []},
                f, allow_unicode=True, sort_keys=False,
            )
    save_manifest(out, build_manifest_entries(out))
    print("KB:", out)
    print("files=%d kps=%d links=%d" % (files, len(kp_ids), link_count))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/_bench_maintenance/kb")
    ap.add_argument("--files", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--images", action="store_true", default=False)
    a = ap.parse_args()
    gen(os.path.abspath(a.out), a.files, a.seed, a.images)


if __name__ == "__main__":
    main()
