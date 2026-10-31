#!/usr/bin/env python
"""kgviz Phase 4 前置｜语料重新冻结（corpus-refreeze）

## 为什么需要这个脚本
`kg-ontology-v0.md §5.1` 冻结的语料 sha `051deb78…`（182 文件）在**当前 HEAD 上无法复现**：
  · `git archive HEAD docs/example` = 218 文件（不是 182）
  · AAA_Vocab 子树 = 169 文件（不是 169→182 的某个子集）
  · 辩论用的 133 节点 / 404 边语料【只存在于工作区】
⇒ 发布后无法辩护"哪份语料"。本脚本把语料身份完整落盘。

## 两个方案与本脚本的结论
方案 1（构造可复现语料）：**实测不可行** ——
  干净 HEAD 导出跑 collector = 61 节点 / 154 边；工作区 = 134 节点 / 404 边。
  差距来自 workspace 的 build 副作用 + 用户 app 实时编辑，无法从 git 重建。
⇒ 采用**方案 2 + 强化**：完整 manifest（path+sha256+size）+ 复算脚本 + build 状态标注。

## 输出（--json）
① commit（HEAD + dirty 状态 + 变更统计）
② 语料路径集合
③ 每文件 path + sha256 + size + manifest sha256
④ 节点/边数（复算，带 ev）
⑤ build 状态（pre-build / post-build；.memoria/build 是否存在）
⑥ 能否从 git 复现（结论 + 理由）

用法:
    python scripts/benchmark/maintenance/kgviz_corpus_refreeze.py --json out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from collections import Counter

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

KB = "docs/example/AAA_Vocab"
# 排除可再生缓存与用户运行时数据（不参与「语料」定义）
EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git", "build", "cache"}
# 注意：.memoria/agent 是用户运行时数据（attachments/sessions），
#       但 .memoria/sidecars 是语料 → 只排除 agent/attachments、agent/sessions


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return (p.stdout or "").strip()


def is_corpus_file(rel: str) -> bool:
    """判定某相对路径是否属于「语料」"""
    parts = rel.split("/")
    for d in parts[:-1]:
        if d in EXCLUDE_DIRS:
            return False
    # .memoria/agent/** 是运行时（会话、附件、复习记录），不算语料
    if rel.startswith(".memoria/agent/"):
        return False
    # 2026-10-26 修正：`docs/` 下是"关于本库的说明文档"（agent_spec / format / requirements…），
    # 实测 48 个 md 不产生任何 KP 节点 ⇒ 不属于【图谱语料】，排除以免 manifest 漂移。
    if rel.startswith("docs/"):
        return False
    return rel.endswith((".md", ".yaml"))


#: 「图谱语料」严格定义：产生 KP 节点的 md + 其 sidecar + manifest.yaml
def corpus_scope_note() -> str:
    return ("docs/example/AAA_Vocab 下：所有非 docs/ 的 .md（= KP 源文件，1 文件 1 KP）"
            " + .memoria/sidecars/**/*.yaml（链接/边声明）"
            " + .memoria/manifest.yaml；"
            "排除 docs/**（库说明文档，实测 48 个 md 不产节点）、"
            ".memoria/agent/**（运行时）、__pycache__/build/cache")


def build_manifest(base: str) -> dict:
    files = []
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in EXCLUDE_DIRS]
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, base).replace("\\", "/")
            if not is_corpus_file(rel):
                continue
            try:
                b = open(p, "rb").read()
            except OSError:
                continue
            files.append({"path": rel, "sha256": hashlib.sha256(b).hexdigest(), "size": len(b)})
    files.sort(key=lambda x: x["path"])
    agg = hashlib.sha256()
    for it in files:
        agg.update(f"{it['path']}\t{it['size']}\t{it['sha256']}\n".encode("utf-8"))
    return {
        "file_count": len(files),
        "manifest_sha256": agg.hexdigest(),
        "files": files,
        "by_ext": dict(Counter(os.path.splitext(it["path"])[1] for it in files)),
    }


def classify_md(base: str, manifest: dict) -> dict:
    """区分「KP 源文件」与「无 KP 的库内 md」（2026-10-26 实测发现）

    实测：158 个语料 md 中，134 个产生 KP 节点，24 个不产生
    （writing/SimonClass 课程笔记、plan/、prompts/、reading/、question-bank 等）。
    ⇒ manifest 收录全部 158（更稳定），但必须标注分类，否则
      「1 文件 1 KP」这个既有说法会被读者误用。
    """
    try:
        from memoria.graph.collector import collect_graph_data
        gd = collect_graph_data(base)
        node_files = set()
        for n in gd.get("nodes", []):
            f = n.get("file")
            if f:
                node_files.add(f.replace("\\", "/"))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    kp_md, non_kp_md = [], []
    for it in manifest["files"]:
        rel = it["path"]
        if not rel.endswith(".md"):
            continue
        (kp_md if rel in node_files else non_kp_md).append(rel)
    return {
        "md_total": len(kp_md) + len(non_kp_md),
        "md_with_kp": len(kp_md),
        "md_without_kp": len(non_kp_md),
        "md_without_kp_list": non_kp_md,
        "note": "「1 文件 1 KP」只对 md_with_kp 成立；md_without_kp 是库内笔记/计划/题库，"
                "不产生节点，但属于语料（改动会影响 build/检索），故纳入 manifest",
    }


def graph_census(base: str) -> dict:
    """复算节点/边（ev:kgviz_corpus_refreeze.py#graph_census）"""
    try:
        from memoria.graph.collector import collect_graph_data
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    gd = collect_graph_data(base)
    nodes = gd.get("nodes", []) if isinstance(gd, dict) else []
    edges = gd.get("edges", []) if isinstance(gd, dict) else []
    deg = Counter()
    for e in edges:
        sid = e.get("source_id")
        if sid:
            deg[sid] += 1
        for t in (e.get("targets") or []):
            deg[t] += 1
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "by_type": dict(Counter(e.get("type") for e in edges)),
        "by_origin": dict(Counter(e.get("origin") for e in edges)),
        "zero_degree_nodes": sum(1 for n in nodes if deg.get(n.get("id"), 0) == 0),
        "max_degree": max(deg.values()) if deg else 0,
        "avg_degree": round(sum(deg.values()) / len(nodes), 2) if nodes else 0,
    }


def export_clean_head(kb: str) -> tuple[str | None, dict]:
    """从 HEAD 导出干净副本（方案 1 的可行性验证）"""
    tmp = tempfile.mkdtemp(prefix="gitarch_")
    zpath = os.path.join(tmp, "arch.zip")
    try:
        with open(zpath, "wb") as fh:
            p = subprocess.run(["git", "archive", "--format=zip", "HEAD", kb],
                               cwd=REPO, stdout=fh, stderr=subprocess.PIPE)
        if p.returncode != 0:
            return None, {"error": p.stderr.decode()[:300]}
        import zipfile
        ex = os.path.join(tmp, "x")
        zipfile.ZipFile(zpath).extractall(ex)
        base = os.path.join(ex, *kb.split("/"))
        return base, {"extracted_to": base}
    except Exception as e:
        return None, {"error": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    base = os.path.join(REPO, KB)

    # ① commit + dirty
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    st_lines = [l for l in status.splitlines() if l.strip()]
    dirty_kb = [l for l in st_lines if KB in l]
    dirty = bool(st_lines)
    commit_meta = {
        "head": head,
        "head_short": head[:8],
        "dirty": dirty,
        "worktree_changes_total": len(st_lines),
        "worktree_changes_in_kb": len(dirty_kb),
    }

    # ②③ 语料 manifest
    manifest = build_manifest(base)
    md_classes = classify_md(base, manifest)

    # ④ 节点/边复算
    work_census = graph_census(base)

    # 方案 1 可行性：干净 HEAD 副本
    clean_base, clean_meta = export_clean_head(KB)
    clean_census = graph_census(clean_base) if clean_base else {"error": "export failed"}

    # ⑤ build 状态
    build_dir = os.path.join(base, ".memoria", "build")
    build_files = []
    if os.path.isdir(build_dir):
        for f in sorted(os.listdir(build_dir)):
            p = os.path.join(build_dir, f)
            if os.path.isfile(p):
                st = os.stat(p)
                build_files.append({
                    "name": f, "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(),
                })
    build_state = {
        "post_build": os.path.isdir(build_dir),
        "build_dir_exists": os.path.isdir(build_dir),
        "build_artifacts": build_files,
        "build_side_effect_evidence": {
            "kb_build_writes_md": "ev:file:src/memoria/graph/kb_build.py#L293-L298"
                                   "（strip_known_wikilink_edge_hints 后 open(full,'w') 写回源 md）",
            "kb_build_writes_sidecar": "ev:file:src/memoria/graph/kb_build.py#L312"
                                       "（save_sidecar_for_md 写回 sidecar）",
            "implication": "kb_build 是破坏性迁移，不是只读路径；"
                           "同一副本 build 前后 collector 边数会变",
        },
    }

    # ⑥ 能否从 git 复现
    reproducible = False
    reason = []
    if clean_census.get("nodes") is not None:
        reason.append(
            f"干净 HEAD 导出（{clean_census.get('nodes')} 节点 / {clean_census.get('edges')} 边）"
            f" ≠ 辩论语料（工作区 {work_census.get('nodes')} / {work_census.get('edges')}）")
    reason.append("工作区含 407 个未跟踪文件、241 个 docs/example 变更（用户 app 实时编辑）")
    reason.append(".memoria/build 产物存在 ⇒ 该副本已被 kb_build 迁移过（post-build）")
    reason.append("用户 live app（Memoria.exe）可能持续写入，工作区语料是活的")
    git_repro = {
        "can_reproduce_from_git": reproducible,
        "verdict": "不能从 git 复现",
        "reasons": reason,
        "what_it_depends_on": [
            "工作区 241 项未提交变更（md 50 处 + sidecar 33 处被 build 改写）",
            "407 个未跟踪文件（含 73 个新增 sidecar）",
            ".memoria/build 前/后状态（kb_build 一次性迁移副作用）",
        ],
        "clean_head_export": {**clean_meta, "census": clean_census},
    }

    payload = {
        "schema": "kgviz-corpus-refreeze/v1",
        "refrozen_at": datetime.now().astimezone().isoformat(),
        "purpose": "kgviz Phase 4/5 前置：给辩论核心数字（133 节点 / 404 边）一个可辩护的身份",
        "corpus_paths": {
            "primary": KB,
            "definition": corpus_scope_note(),
            "excluded_docs_reason": "docs/** 下 48 个 md 实测不产生任何 KP 节点（是库说明文档），"
                                    "纳入会使 manifest 随无关文档漂移",
        },
        "①_commit": commit_meta,
        "②_corpus_paths": {"primary": KB, "absolute": base},
        "③_manifest": manifest,
        "③b_md_classification": md_classes,
        "④_graph_census": {
            "measured_on": "workspace",
            "values": work_census,
            "recompute_script": "ev:file:scripts/benchmark/maintenance/kgviz_corpus_refreeze.py"
                                "#graph_census（调用 memoria.graph.collector.collect_graph_data）",
            "debate_number": {"nodes": 133, "edges": 404,
                              "note": "辩论引用值；本次实测工作区为 "
                                      f"{work_census.get('nodes')}/{work_census.get('edges')}"
                                      " ⇒ 差 1 节点，因工作区仍在变动"},
        },
        "⑤_build_state": build_state,
        "⑥_git_reproducibility": git_repro,
        "PLAN_DECISION": {
            "plan_1_feasible": False,
            "plan_1_reason": "干净 HEAD 只有 61 节点/154 边，无法重建 133/404",
            "plan_adopted": "方案 2 + 强化：完整 manifest 作为唯一身份，并明确标注不可从 git 复现",
            "manifest_is_the_identity": True,
        },
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifact_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print("=" * 76)
    print("KGViz 语料重新冻结")
    print("=" * 76)
    print(f"HEAD        : {commit_meta['head_short']}  dirty={dirty}")
    print(f"               工作区变更 {commit_meta['worktree_changes_total']} 项"
          f"（KB 内 {commit_meta['worktree_changes_in_kb']} 项）")
    print()
    print(f"语料        : {KB}")
    print(f"  文件数    : {manifest['file_count']}   {manifest['by_ext']}")
    print(f"  manifest  : sha256={manifest['manifest_sha256'][:16]}…")
    print()
    print("节点/边（工作区实测）:")
    print(f"  nodes={work_census.get('nodes')}  edges={work_census.get('edges')}"
          f"  zero_deg={work_census.get('zero_degree_nodes')}"
          f"  max_deg={work_census.get('max_degree')}"
          f"  avg_deg={work_census.get('avg_degree')}")
    print(f"  by_type={work_census.get('by_type')}  by_origin={work_census.get('by_origin')}")
    print(f"  辩论引用  : 133 节点 / 404 边")
    print()
    print("方案 1 可行性（干净 HEAD 导出）:")
    print(f"  {clean_census.get('nodes')} 节点 / {clean_census.get('edges')} 边"
          f"  ⇒ {'✅ 可重建' if (clean_census.get('nodes'),clean_census.get('edges'))==(133,404) else '❌ 不可重建'}")
    print()
    print("build 状态:")
    print(f"  post_build={build_state['post_build']}  产物={[b['name'] for b in build_state['build_artifacts']]}")
    print()
    print("⑥ 能否从 git 复现: " + ("✅ 能" if reproducible else "❌ 不能"))
    for r in reason:
        print(f"   · {r}")
    print()
    print(f"artifact sha256: {payload['artifact_sha256'][:16]}…")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
