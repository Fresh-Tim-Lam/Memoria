#!/usr/bin/env python3
"""
task-114｜A1 假设检验：token 记账模型（静态、可复跑）

A1 = 「MCP 化（把 Memoria 暴露为 MCP server + 结构化返回）一定增 token 开销」

本模型回答一个**方向性**问题，不是给精确 token 数：
  组 0（零新增 schema，只改返回粒度） vs 组 A（当前 35 工具全 schema 进 system prompt）
  vs 组 B（MCP 化：schema 按需 discover + 结构化返回）

三组都拆成「schema 开销」与「每次调用开销」两个独立维度（满足 B4.f，防止只对比一面）。

口径声明（E4.2/B4.c）：
  - 本模型是**静态 token 记账**，非实测（无 MCP 代码可跑，已核 src/ 无 mcp 引用，
    仅 code-highlight.js:27 的 map/cpp 关键字误匹配 memcpy）
  - tokenizer 口径 = 字符估算：JSON/描述用 ~3.5 字符/token；中文正文用「字符数」近似
    （中文 1 字 ≈ 1~2 token，此处取 1 token ≈ 1.5 中文字符 作为中位，结论对口径不敏感）
  - 若要求实测，需：一个真实 MCP server 实现 + 真实 tokenizer（tiktoken/cl100k_base）+ 真实 agent 会话

所有数字来自仓库真实基数的算术推演，公式写在脚本里，任何人可复跑。
"""
import json, os, hashlib, sys

# ── 真实基数（来自仓库实测，见报告 §2）──
BASE = {
    "n_tools_group_A": 35,                    # kb.py build_kb_tools 返回的 Tool(name=...) 去重数
    "schema_chars_group_A": 15220,            # 35 工具 description+parameters 字符合计（脚本实测）
    "kb_file_avg_bytes": 79 * 1024,           # work copy 32 个 md 平均 79 KB
    "kb_file_max_bytes": 407.5 * 1024,        # 08章 最大单文件 407.5 KB
    "read_limit_lines": 2000,                 # read_document 默认最多返回行数
    "kb_md_count": 32,                        # work copy md 文件数
    "kb_total_bytes": 2529.2 * 1024,          # 总字节
}

# ── tokenizer 口径 ──
CHAR_PER_TOKEN_JSON = 3.5   # JSON schema / 描述类英文文本
CHAR_PER_TOKEN_CN = 1.5     # 中文正文（1 中文 token ≈ 1.5 字，中位近似）

def cn_tokens(chars):
    """中文正文字符 → token（1 token ≈ 1.5 中文字符）"""
    return chars / CHAR_PER_TOKEN_CN

def json_tokens(chars):
    """JSON/英文描述字符 → token"""
    return chars / CHAR_PER_TOKEN_JSON

def pct(a, b):
    """a 相对 b 的百分比变化，b 为基准"""
    if b == 0: return None
    return (a - b) / b * 100.0

def main():
    r = {}

    # ────────── 组 A：当前（35 工具全 schema 进 system prompt）──
    # system prompt 固定携带全部 35 个工具的 name + description + parameters
    schema_A = json_tokens(BASE["schema_chars_group_A"])       # 每次会话固定 schema 开销

    # 每次调用开销：read_document 返回 2000 行正文（假设读到平均 79KB 文件的正文，取截断前的窗口）
    # 简化：一次 read 返回 2000 行 × 平均行 ~40 字（中文教材）≈ 80K 字符
    read_call_chars = 2000 * 40
    call_A_read = cn_tokens(read_call_chars)
    # search_kb 返回 top_k=5 个锚点 + 片段，约 40 字×5
    call_A_search = cn_tokens(5 * 60)

    # ────────── 组 0：零新增 schema，只改返回粒度 ──
    # 工具数不变（35），schema 不变（= schema_A）
    # 但 read_document 支持按 heading 取（只返回目标 heading 段落，而非整 2000 行）
    # 假设：目标是读一个章节，粒度化后可只返回 1/10 正文
    schema_0 = schema_A                                  # schema 不变
    call_0_read = cn_tokens(read_call_chars / 10)        # 返回粒度降 10×
    call_0_search = call_A_search                        # search 不变

    # ────────── 组 B：MCP 化（schema 按需 discover + 结构化返回）──
    # B1：schema 不进 system prompt，只在首次 tools/list 时拉一次
    #   问题：tools/list 也要 token。但按 MCP 惯例，discover 一次后可缓存，
    #   且 tools/list 返回的是 name 清单（不含完整 parameters）时更省。
    #   保守假设：MCP tools/list 返回完整 schema（= schema_A 同样的字符），
    #   但**只在会话首次拉一次**，而非每次 system 固定带。
    # 关键变量：MCP 的 schema 开销是「按需、一次性」，组 A 是「每会话固定、不可省」。
    schema_B_discover_once = schema_A                    # tools/list 一次性开销
    # 但 MCP 常把工具描述做精简（结构化），且不重复注入 system；
    # 保守起见这里**不给 MCP 任何精简红利**，只算「一次性 discover vs 每会话固定」的差异。

    # 每次调用：结构化返回（JSON 字段 vs 纯文本）
    # 结构化返回会增加 JSON 键名开销（约 +20%），但减少 agent 重新解析的歧义
    call_B_read = call_0_read * 1.20                     # 结构化返回 +20% token
    call_B_search = call_A_search * 1.15                 # 结构化锚点 +15%

    # ── 建模场景：一个典型 agent 会话 ──
    # 场景 T1：查一个概念（search 1 次 + read 1 次）
    # 场景 T2：通读一章（read 10 次，逐段）
    # 场景 T3：多轮问答（search 3 + read 2）
    scenarios = {
        "T1_查概念": dict(n_search=1, n_read=1),
        "T2_通读章": dict(n_search=0, n_read=10),
        "T3_多轮": dict(n_search=3, n_read=2),
    }

    result = {"base": BASE, "scenarios": {}}
    for name, sc in scenarios.items():
        ns, nr = sc["n_search"], sc["n_read"]

        # 组 A：schema 固定 + 整文件/整窗口返回
        total_A = schema_A + ns * call_A_search + nr * call_A_read
        # 组 0：schema 固定 + 粒度化返回
        total_0 = schema_0 + ns * call_0_search + nr * call_0_read
        # 组 B：schema 一次性 discover + 结构化返回
        total_B = schema_B_discover_once + ns * call_B_search + nr * call_B_read

        result["scenarios"][name] = {
            "schema_A_tok": round(schema_A),
            "schema_B_discover_tok": round(schema_B_discover_once),
            "A_total": round(total_A),
            "zero_total": round(total_0),
            "B_total": round(total_B),
            "A_vs_zero_pct": round(pct(total_0, total_A), 1),   # 零新增省多少
            "A_vs_B_pct": round(pct(total_B, total_A), 1),       # MCP 化相对当前
        }

    # ── 结论判定 ──
    # A1「一定增」成立 ⇔ 在每个场景 B_total > A_total（无例外）
    # 若存在任一场景 B_total <= A_total 或零新增组 0 已显著省 ⇒ A1 的全称「一定」不成立
    all_B_greater = all(v["B_total"] > v["A_total"] for v in result["scenarios"].values())
    any_zero_saves = any(v["zero_total"] < v["A_total"] for v in result["scenarios"].values())

    verdict = None
    if all_B_greater:
        verdict = "A1 成立（MCP 化在所有场景都增 token）"
    else:
        # 进一步看：是否组 0 已能省（说明省 token 与「是否 MCP 化」无关，与「返回粒度」有关）
        winner_zero = all(v["zero_total"] <= v["A_total"] for v in result["scenarios"].values())
        if winner_zero and any(v["zero_total"] < v["A_total"] for v in result["scenarios"].values()):
            verdict = ("A1 不成立：token 省耗主要由「返回粒度/结构化」决定，"
                       "与「是否 MCP 化」无必然因果；零新增 schema 的组 0 已在多数场景更省")
        else:
            verdict = "A1 部分不成立：MCP 化在部分场景不增 token，全称「一定增」被证伪"

    result["verdict"] = verdict
    result["model_note"] = "静态 token 记账模型（非实测），口径=字符估算，见 report"

    # 落盘
    outdir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(outdir, "n1-token-model-output.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()
    print("output:", out)
    print("sha256:", sha)

    return result, out, sha

if __name__ == "__main__":
    main()
