"""Build Chinese benchmark KB from 人工智能导论知识点汇总 docs.

Uses 18 .md files as corpus (each = 1 KP), creates queries.json + qrels.json.
kp_id format: m{module}_{file_num} (e.g. m1_1, m5_3)
"""
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.manifest import rebuild_manifest

SRC = ROOT / "docs" / "example" / "人工智能导论知识点汇总"
OUT = ROOT / "benchmarks" / "ai_zh"
KB = OUT / "kb_gold"

# Module directory -> kp_id prefix
MODULES = [
    ("模块1：人工智能的发展历史", "m1", [1, 2]),
    ("模块2：知识表达与推理", "m2", [1, 2]),
    ("模块3：搜索探寻与问题求解", "m3", [1, 2]),
    ("模块4：机器学习", "m4", [1, 2]),
    ("模块5：深度学习", "m5", [1, 2, 3]),
    ("模块6：强化学习", "m6", [1, 2]),
    ("模块7：人工智能博弈", "m7", [1, 2]),
    ("模块8：人工智能伦理与安全", "m8", [1]),
    ("模块9：人工智能架构与系统", "m9", [1]),
    ("模块10：人工智能应用", "m10", [1]),
]

# Topic summary for each kp_id (for tags/description in sidecar)
KP_INFO = {
    "m1_1": ("可计算理论与图灵机", ["人工智能", "可计算理论", "图灵机", "希尔伯特", "哥德尔"]),
    "m1_2": ("图灵测试与AI三大流派", ["人工智能", "图灵测试", "符号主义", "连接主义", "行为主义"]),
    "m2_1": ("知识表示方法与逻辑推理", ["知识表示", "命题逻辑", "谓词逻辑", "产生式规则"]),
    "m2_2": ("知识图谱推理与因果推理", ["知识图谱", "FOIL", "PRA", "贝叶斯网络", "因果推理"]),
    "m3_1": ("搜索算法基础与A*搜索", ["搜索算法", "贪婪搜索", "A星搜索", "启发式"]),
    "m3_2": ("对抗搜索与蒙特卡洛树搜索", ["Minimax", "Alpha-Beta剪枝", "MCTS", "博弈搜索"]),
    "m4_1": ("机器学习基本概念与模型评估", ["机器学习", "监督学习", "损失函数", "正则化", "线性回归"]),
    "m4_2": ("聚类与降维算法", ["K-Means", "聚类", "PCA", "LDA", "降维"]),
    "m5_1": ("感知机与卷积神经网络", ["感知机", "CNN", "反向传播", "深度学习"]),
    "m5_2": ("循环神经网络与注意力机制", ["RNN", "LSTM", "GRU", "Transformer", "注意力机制"]),
    "m5_3": ("网络结构搜索与经典架构", ["NAS", "LeNet", "AlexNet", "ResNet", "网络结构搜索"]),
    "m6_1": ("强化学习基础与Q学习", ["强化学习", "MDP", "贝尔曼方程", "Q学习", "探索与利用"]),
    "m6_2": ("深度强化学习与AlphaGo", ["DQN", "策略梯度", "Actor-Critic", "AlphaGo", "深度强化学习"]),
    "m7_1": ("博弈论与纳什均衡", ["博弈论", "纳什均衡", "囚徒困境", "混合策略"]),
    "m7_2": ("博弈策略求解与匹配算法", ["遗憾最小化", "CFR", "Gale-Shapley", "双边匹配"]),
    "m8_1": ("AI伦理与模型安全", ["AI伦理", "可信AI", "可解释性", "对抗攻击", "数据投毒"]),
    "m9_1": ("AI架构与分布式训练", ["AI芯片", "GPU", "分布式训练", "通信优化", "计算框架"]),
    "m10_1": ("语言大模型与AI应用", ["大模型", "RLHF", "机器翻译", "图像分类", "机器人"]),
}

# Queries: (query_text, [relevant kp_ids])
# Designed to test: keyword matching, semantic matching, cross-topic precision
QUERIES = [
    # --- Module 1: AI History ---
    ("图灵机模型的基本结构是什么", ["m1_1"]),
    ("希尔伯特纲领和哥德尔不完全性定理的关系", ["m1_1"]),
    ("图灵测试如何判断机器是否具有智能", ["m1_2"]),
    ("人工智能的三大主流算法流派", ["m1_2"]),
    ("符号主义连接主义行为主义的区别", ["m1_2"]),

    # --- Module 2: Knowledge Representation ---
    ("知识表示有哪些方法", ["m2_1"]),
    ("命题逻辑和谓词逻辑的区别", ["m2_1"]),
    ("知识图谱推理的代表性方法", ["m2_2"]),
    ("贝叶斯网络和马尔可夫逻辑网络", ["m2_2"]),
    ("因果推理中的do算子和反事实推理", ["m2_2"]),

    # --- Module 3: Search ---
    ("A星搜索算法的原理", ["m3_1"]),
    ("搜索算法的完备性和最优性", ["m3_1"]),
    ("Minimax搜索和Alpha-Beta剪枝", ["m3_2"]),
    ("蒙特卡洛树搜索MCTS", ["m3_2"]),

    # --- Module 4: Machine Learning ---
    ("监督学习无监督学习半监督学习的区别", ["m4_1"]),
    ("经验风险和期望风险的区别", ["m4_1"]),
    ("没有免费午餐定理", ["m4_1"]),
    ("K均值聚类算法", ["m4_2"]),
    ("PCA主成分分析和LDA线性判别分析", ["m4_2"]),

    # --- Module 5: Deep Learning ---
    ("感知机模型和多层感知机", ["m5_1"]),
    ("卷积神经网络CNN的基本结构", ["m5_1"]),
    ("反向传播算法的原理", ["m5_1"]),
    ("RNN循环神经网络和LSTM", ["m5_2"]),
    ("注意力机制和Transformer", ["m5_2"]),
    ("网络结构搜索NAS的发展", ["m5_3"]),

    # --- Module 6: Reinforcement Learning ---
    ("强化学习的马尔可夫决策过程", ["m6_1"]),
    ("Q学习算法和探索与利用", ["m6_1"]),
    ("深度Q网络DQN和策略梯度", ["m6_2"]),
    ("AlphaGo的深度强化学习", ["m6_2"]),

    # --- Module 7: Game Theory ---
    ("纳什均衡和囚徒困境", ["m7_1"]),
    ("遗憾最小化算法和CFR", ["m7_2"]),

    # --- Module 8: Ethics ---
    ("人工智能伦理和可信AI", ["m8_1"]),
    ("对抗攻击和数据投毒", ["m8_1"]),

    # --- Module 9: Architecture ---
    ("AI芯片和分布式训练系统", ["m9_1"]),

    # --- Module 10: Applications ---
    ("语言大模型和RLHF", ["m10_1"]),
    ("Transformer和注意力机制", ["m5_2", "m10_1"]),

    # --- Cross-topic queries (test precision) ---
    ("深度学习和强化学习的区别", ["m5_1", "m6_1"]),
    ("搜索算法和博弈论的关系", ["m3_2", "m7_1"]),
]


def build_kb():
    """Copy .md files into KB directory and create sidecars."""
    if KB.exists():
        shutil.rmtree(KB)
    KB.mkdir(parents=True)

    corpus_dir = KB / "corpus"
    corpus_dir.mkdir(parents=True)
    sidecar_dir = KB / ".memoria" / "sidecars" / "corpus"
    sidecar_dir.mkdir(parents=True)

    count = 0
    for mod_name, prefix, file_nums in MODULES:
        mod_dir = SRC / mod_name
        for fn in file_nums:
            kp_id = f"{prefix}_{fn}"
            src_file = mod_dir / f"{fn}.md"
            if not src_file.is_file():
                print(f"  [WARN] missing: {src_file}")
                continue

            content = src_file.read_text(encoding="utf-8")
            title, tags = KP_INFO.get(kp_id, (kp_id, ["人工智能"]))

            # Write md file
            rel_md = f"corpus/{kp_id}.md"
            md_path = KB / rel_md
            md_path.write_text(content, encoding="utf-8")

            # Write sidecar
            heading = content.split("\n")[0].lstrip("# ").strip() or title
            sidecar = {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "file": rel_md.replace("\\", "/"),
                "knowledge_points": [{
                    "id": kp_id,
                    "name": title,
                    "tags": tags,
                    "description": content[:240].replace("\n", " "),
                    "range": {
                        "start": {"line_hint": 1, "snippet": heading},
                        "end": {"line_hint": max(1, content.count("\n")), "snippet": content[-120:].strip()},
                    },
                }],
                "links": [],
            }
            sc_path = sidecar_dir / f"{kp_id}.memoria.yaml"
            with open(sc_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(sidecar, f, allow_unicode=True, sort_keys=False)
            count += 1

    rebuild_manifest(str(KB))
    print(f"Built KB: {count} docs -> {KB}")
    return count


def export_eval():
    """Create queries.json and qrels.json."""
    eval_dir = OUT / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    query_list = [
        {"query_id": f"q{i+1:02d}", "text": text}
        for i, (text, _) in enumerate(QUERIES)
    ]
    qrels = {}
    for i, (_, rels) in enumerate(QUERIES):
        qid = f"q{i+1:02d}"
        qrels[qid] = rels

    (eval_dir / "queries.json").write_text(
        json.dumps(query_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (eval_dir / "qrels.json").write_text(
        json.dumps(qrels, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Eval: {len(query_list)} queries -> {eval_dir}")
    return len(query_list)


def main():
    print("=== Building Chinese AI benchmark KB ===")
    build_kb()
    export_eval()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
