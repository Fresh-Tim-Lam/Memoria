# 搜索引擎架构与实验测试结果

> **状态**：`[✓]` 实验记录（2026-07-11）
> **前置**：[search-kernel-v1.5.md](search-kernel-v1.5.md)、[search-retrieval-benchmark.md](search-retrieval-benchmark.md)
> **目的**：记录 SearchKernel v1.5 多模型架构的实际部署配置与 BEIR SciFact 基线实验结果（含 P3 Rerank），供后续中文 benchmark 对照。

---

## 1. 多模型架构（已落地）

### 1.1 阶段流水线

```
Query
  │
  ▼
QueryPlan（分词、拼音、alias 扩展、可选 MT→en）
  │
  ├─► P0  Lexical（rule + jieba + pypinyin，倒排）
  ├─► P1  Embed-Recall（bi-encoder，向量召回）
  ├─► P2  MT-Bridge（zh↔en 桥接，可选，本次实验关闭）
  └─► P3  Embed-Rerank（cross-encoder，Top-K 精排，可选，已开启）
  │
  ▼
RRF 融合 → Top-K
  │
  ▼  ↓（若 rerank_enabled）cross-encoder 精排 → Top-K'
  │
  ▼
LTR 反馈权重（weights.json）
  │
  ▼
置信分档 → Top-N kp_id + sources + evidence
```

### 1.2 ModelRouter 配置

| 阶段 | 角色 | 当前型号 | 状态 |
|------|------|----------|------|
| P0 | Lexical | rule + jieba + pypinyin | ✅ 启用 |
| P1 | Embed-Recall（bi-encoder） | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | ✅ 启用 |
| P2 | MT-Bridge | opus-mt-zh-en / NLLB-200 | ⏸ 未启用（英文库无需） |
| P3 | Embed-Rerank（cross-encoder） | `cross-encoder/ms-marco-MiniLM-L-6-v2`（light 档） | ✅ 启用 |

### 1.3 关键模块

| 模块 | 路径 | 职责 |
|------|------|------|
| ModelRouter | `src/memoria/services/model_router.py` | 统一调度各阶段模型；lazy load；KB manifest；`rerank_tier` 选 default/light |
| EmbeddingProvider | `src/memoria/services/embedding_provider.py` | P1 实现：`_TransformersEmbedder`（AutoTokenizer + AutoModel + mean pooling） |
| RerankProvider | `src/memoria/services/rerank_provider.py` | P3 实现：`_CrossEncoderReranker`（AutoTokenizer + AutoModelForSequenceClassification），失败降级原序 |
| SearchKernel | `src/memoria/services/search_kernel.py` | `search(modes="both")` → 调用 lexical + semantic，RRF 融合；若 `rerank_enabled` 调 `rerank_search_results` |
| LexicalIndex | `src/memoria/services/lexical_index.py` | P0 倒排索引 |

### 1.4 关键工程决策

| 问题 | 决策 | 原因 |
|------|------|------|
| `sentence_transformers` import 卡死 | 改用 `transformers.AutoTokenizer + AutoModel` + 手写 mean pooling | 避免子依赖链触发联网检查 |
| HF cache 模型名查找失败 | DEFAULT_MODEL 改为带 org 前缀的完整 id | `local_files_only=True` 按完整 id 查 cache |
| 短名配置兼容 | `_MODEL_ALIAS_MAP` 映射表补全短名 | 用户已保存的旧配置无需迁移 |
| transformers `_patch_mistral_regex` 联网 | 模块顶部 `os.environ.setdefault("HF_HUB_OFFLINE", "1")` | 必须在任何 HF import 之前设置 |
| torch 2.10.0+cu130 CUDA segfault | 强制 `CUDA_VISIBLE_DEVICES=""` | CPU 模式稳定 |
| `search_body_locate` C 扩展崩溃 | benchmark 时 `body_locate_enabled: False` | 783 doc KB 上 segfault，绕过 |
| 单进程重复 encode segfault | `multiprocessing.Pool(processes=1)` 隔离 | worker 加载模型一次后复用；崩溃自动重建 |
| `bge-reranker-v2-m3` CPU 推理卡死（568M 参数） | 切换 `cross-encoder/ms-marco-MiniLM-L-6-v2`（22M 参数，90MB） | CPU 友好；`rerank_tier="light"` 配置 |
| reranker 推理偶发卡住 | `torch.set_num_threads(1)` + `max_length=256` + `batch_size=8` | 限制资源，避免线程争用 |
| PowerShell stderr 杀进程 | `Start-Process -RedirectStandardOutput/-RedirectStandardError` 文件重定向 | NativeCommandError 处理会杀 stderr 的 Python 进程 |
| Pool worker 卡住无法跳出 | `apply_async.get(timeout=180)` + 超时重建 Pool | per-query 超时；崩溃 worker 终止后新建 |
| rerank 结果文件重复 | 启动时 `_load_done_qids()` 跳过已完成 + 聚合时 `seen_qids` 去重 | 续跑安全 |

---

## 2. 实验设置

### 2.1 数据集

- **BEIR SciFact**：5183 docs、300 test queries
- **qrel-coverage 子集**（`kb_gold_subset`）：783 docs（至少被一条 qrel 命中），用于加速评测
- 每条 corpus 文档 → 1 个 KP（`kp_id = doc_id`），qrels 直接映射为 `expected_kp_ids`

### 2.2 评测脚本

| 脚本 | 用途 |
|------|------|
| `scripts/benchmark/_pool_emb.py` | P1 评测：`multiprocessing.Pool` worker 复用 bi-encoder |
| `scripts/benchmark/_aggregate_emb.py` | 聚合 `results_embedding.jsonl` → IR 指标 |
| `scripts/benchmark/_pool_rerank.py` | P3 评测：worker 复用 bi-encoder + cross-encoder；per-query 超时 |
| `scripts/benchmark/_aggregate_rerank.py` | 聚合 `results_rerank.jsonl` → IR 指标 |
| `scripts/benchmark/run_search_benchmark.py` | Lexical-only 评测 |

### 2.3 评测配置

```python
# _pool_rerank.py init_worker()
ui_settings.save_ui_settings({"search": {
    "embedding_enabled": True,         # 启用 P1
    "allow_model_download": True,
    "body_locate_enabled": False,      # 绕过 C 扩展崩溃
    "rerank_enabled": True,           # 启用 P3
    "rerank_tier": "light",           # 用轻量级 reranker
}})
search(text, kb_path=KB, modes="both", limit=20)  # RRF 融合 → cross-encoder 精排
```

### 2.4 指标

| 指标 | 含义 |
|------|------|
| Recall@k | 相关 KP 是否出现在 Top-k |
| MRR | 第一个相关 KP 的排名倒数均值 |
| nDCG@k | 分级相关性（BEIR qrel score 0/1） |
| Precision@k | Top-k 中相关占比 |
| Noise@k | Top-k 中不相关 KP 占比（= 1 − Precision@k） |

---

## 3. 实验结果

### 3.1 三档基线对比（783 doc qrel-coverage 子集）

| 指标 | Lexical-only | Lexical+Embed (RRF) | +Rerank (light) | Δ Rerank vs Embed | Δ Rerank vs Lexical |
|------|------|------|------|------|------|
| **MRR** | 0.4294 | 0.4710 | **0.6064** | **+28.7%** | **+41.2%** |
| **Recall@1** | 0.3342 | 0.3508 | **0.5176** | **+47.6%** | **+54.9%** |
| **Precision@1** | 0.3557 | 0.3767 | **0.5533** | **+46.9%** | **+55.6%** |
| **Noise@1** | 0.6443 | 0.6233 | **0.4467** | **-28.3%** | **-30.6%** |
| **nDCG@1** | 0.3557 | 0.3767 | **0.5533** | **+46.9%** | **+55.6%** |
| **Recall@5** | 0.5031 | 0.5759 | **0.6754** | **+17.3%** | **+34.3%** |
| **Precision@5** | 0.1107 | 0.1307 | **0.1553** | **+18.8%** | **+40.3%** |
| **Noise@5** | 0.8893 | 0.8693 | **0.8447** | **-2.8%** | **-5.0%** |
| **nDCG@5** | 0.4309 | 0.4804 | **0.6161** | **+28.3%** | **+43.0%** |
| **Recall@10** | 0.5635 | 0.6688 | **0.7044** | **+5.3%** | **+25.0%** |
| **Precision@10** | 0.0624 | 0.0770 | **0.0810** | **+5.2%** | **+29.8%** |
| **Noise@10** | 0.9376 | 0.9230 | **0.9190** | -0.4% | -2.0% |
| **nDCG@10** | 0.4512 | 0.5121 | **0.6255** | **+22.1%** | **+38.6%** |

**评测规模**：Lexical-only = 298 queries；Lexical+Embedding = 300 queries；+Rerank = 300 queries（全量）

### 3.2 关键观察

1. **P3 Rerank 显著提升 Top-1 质量**：Precision@1 从 0.3767 → 0.5533（+46.9%），Noise@1 从 0.6233 → 0.4467（-28.3%），cross-encoder 精排把最相关结果顶到首位
2. **MRR +28.7%**：第一个相关结果位置大幅靠前，用户体验直接改善
3. **nDCG@10 +22.1%**：整体排序质量提升，Top-10 中相关结果排序更靠前
4. **Recall@10 仅 +5.3%**：rerank 不改变候选集（仍是 RRF Top-20 的子集），Recall 上限受 P1 召回约束，印证 R17 图扩散的必要性
5. **Noise@k 全面下降但绝对值仍高**：Noise@5=0.8447、Noise@10=0.9190，因 KP 数量远大于 qrel 标注数，Top-k 必然混入未标注文档
6. **0 失败 / 0 超时 / 0 跳过**：Pool + per-query 超时方案稳定

### 3.3 性能数据

| 指标 | Lexical-only | Lexical+Embedding | +Rerank (light) |
|------|------|------|------|
| 评测总耗时 | — | 423s（300 query） | 996s（300 query） |
| 单 query 平均 | — | ~1.4s | ~3.3s（含 cross-encoder 推理） |
| 模型加载次数 | 0 | 1（worker 复用） | 2（bi-encoder + cross-encoder） |
| 失败/超时/跳过 | 0/0/0 | 0/0/0 | 0/0/0 |

---

## 4. 结论（英文 SciFact）

**多模型架构（P1 + P3 启用）相比 Lexical-only 在所有 IR 指标上显著提升**，验证了 SearchKernel v1.5 多模型分工设计的有效性：

- **P1 Embed-Recall**：Recall@10 +18.7%，补充 lexical 盲区
- **P3 Embed-Rerank**：Precision@1 +55.6%，MRR +41.2%，cross-encoder 精排把最相关结果顶到首位
- **Recall@10 增长放缓（+5.3%）**：rerank 不扩展候选集，后续需 R17 图扩散突破召回上限

---

## 5. 中文 benchmark（AI 导论知识点）

### 5.1 数据集

因 HuggingFace 网络不可达，无法下载 MIRACL zh / DuReader 等标准中文数据集。改用**项目内自建中文 KB**：

- **语料来源**：`docs/example/人工智能导论知识点汇总/` 下 10 个模块、18 个 `.md` 文件
- **每文件 → 1 个 KP**（`kp_id = m{module}_{file}`，如 `m1_1`、`m5_3`）
- **查询集**：38 条中文 query，覆盖关键词匹配、语义匹配、跨主题精度
- **qrels**：每条 query 标注 1-2 个相关 KP

### 5.2 三档基线对比

| 指标 | Lexical-only | Lexical+Embed (RRF) | +Rerank (light) |
|------|------|------|------|
| **MRR** | **0.9868** | 0.7982 | 0.7625 |
| **Recall@1** | **0.9474** | 0.6842 | 0.6579 |
| **Precision@1** | **0.9737** | 0.6842 | 0.6842 |
| **Noise@1** | **0.0263** | 0.3158 | 0.3158 |
| **nDCG@1** | **0.9737** | 0.6842 | 0.6842 |
| **Recall@5** | **0.9868** | 0.9605 | 0.8158 |
| **nDCG@5** | **0.9778** | 0.8398 | 0.7520 |
| **Recall@10** | **1.0000** | 0.9737 | 0.9737 |
| **nDCG@10** | **0.9825** | 0.8456 | 0.8038 |

**评测规模**：38 queries × 18 docs

### 5.3 关键观察

1. **Lexical 在中文上表现极优**：MRR=0.9868，Precision@1=0.9737，Recall@10=1.0。jieba 分词对 AI 术语（如"卷积神经网络"、"强化学习"、"纳什均衡"）切分精准，关键词直接命中
2. **Embed (RRF) 反而降低排序质量**：MRR 从 0.9868 → 0.7982（-19.0%）。RRF 融合引入了语义相似但不精确的候选，稀释了 lexical 的精确匹配
3. **Rerank 进一步降低**：MRR 从 0.7982 → 0.7625。`ms-marco-MiniLM-L-6-v2` 是英文训练的 cross-encoder，对中文 (query, doc) pair 的相关性判断能力不足
4. **Recall@10 差距小**：Lexical=1.0，Embed=0.9737，Rerank=0.9737。小语料 + jieba 精准分词使 lexical 召回已接近上限

### 5.4 结论

| 场景 | 英文 SciFact (783 docs) | 中文 AI (18 docs) |
|------|------|------|
| Lexical MRR | 0.4294 | **0.9868** |
| +Embed MRR | 0.4710 (+9.7%) | 0.7982 (-19.0%) |
| +Rerank MRR | 0.6064 (+41.2%) | 0.7625 (-22.8%) |
| **最佳方案** | Lexical+Embed+Rerank | **Lexical-only** |

**关键差异**：
- **英文**：lex recall 不足（同义词/变形），embed 补充召回 → rerank 精排提升 top-1
- **中文**：jieba 分词精准（术语固定、无词形变化），lex recall 已饱和 → embed/rerank 引入噪音
- **reranker 语言不匹配**：`ms-marco-MiniLM-L-6-v2` 英文训练，对中文 pair 无判别力

### 5.5 性能数据

| 指标 | Lexical-only | Lexical+Embed | +Rerank |
|------|------|------|------|
| 评测总耗时 | 2s（38 query） | 18s（38 query） | 73s（38 query） |
| 单 query 平均 | ~0.05s | ~0.5s | ~1.9s |
| 模型加载次数 | 0 | 1 | 2 |
| 失败/跳过 | 0/0 | 0/0 | 0/0 |

---

## 5b. 大规模中文 benchmark（MIRACL zh）

### 5b.1 数据集

通过 `hf-mirror.com` 镜像下载 MIRACL zh dev split：

- **语料来源**：MIRACL zh（多语言信息检索基准，维基百科语料）
- **qrel-coverage 子集**：966 docs（被 dev qrels 命中的文档子集），从 4.9M 全量语料中提取
- **每文档 → 1 个 KP**（`kp_id = docid`，如 `70#42`、`13#0`）
- **查询集**：393 条中文 dev queries
- **qrels**：每条 query 标注 1-3 个相关 KP

### 5b.2 三档基线对比

| 指标 | Lexical-only | Lexical+Embed (RRF) | +Rerank (light)† | Δ Embed vs Lexical | Δ Rerank vs Embed |
|------|------|------|------|------|------|
| **MRR** | 0.6453 | **0.8550** | 0.6953† | **+32.5%** | **-18.7%** |
| **Recall@1** | 0.2634 | **0.4505** | 0.2983† | **+71.0%** | -33.8% |
| **Precision@1** | 0.5216 | **0.7990** | 0.5500† | **+53.2%** | -31.2% |
| **Noise@1** | 0.4784 | **0.2010** | 0.4500† | **-58.0%** | +123.9% |
| **nDCG@1** | 0.5216 | **0.7990** | 0.5500† | **+53.2%** | -31.2% |
| **Recall@5** | 0.6510 | **0.8364** | 0.7376† | **+28.5%** | -11.8% |
| **nDCG@5** | 0.5893 | **0.8168** | 0.6575† | **+38.6%** | -19.5% |
| **Recall@10** | 0.7522 | **0.9098** | 0.9235† | **+21.0%** | +1.5% |
| **nDCG@10** | 0.6297 | **0.8419** | 0.7301† | **+33.7%** | -13.3% |

**评测规模**：Lexical = 393 queries；Embed = 393 queries；Rerank = 120/393 queries（†部分评测，CPU 推理过慢未跑完全量）

### 5b.3 关键观察

1. **Embed 在大规模中文上显著优于 Lexical**：MRR 从 0.6453 → 0.8550（+32.5%），Recall@10 从 0.7522 → 0.9098（+21.0%）。与 AI 导论（18 docs）结论相反——大规模语料上 jieba 分词不再使 lexical 召回饱和，embed 的语义匹配能力补充了大量未命中候选
2. **Recall@1 大幅提升**：从 0.2634 → 0.4505（+71.0%）。大规模语料中存在大量近义/相关但非字面匹配的文档，embed 能有效召回
3. **Rerank 仍降低质量**：MRR 从 0.8550 → 0.6953（-18.7%）。`ms-marco-MiniLM-L-6-v2` 英文 reranker 对中文 pair 无判别力，打乱了 embed 的好排序
4. **Recall@10 基本持平**：Embed=0.9098，Rerank=0.9235。rerank 不扩展候选集，仅重排序

### 5b.4 小规模 vs 大规模中文对比

| 场景 | AI 导论 (18 docs) | MIRACL zh (966 docs) |
|------|------|------|
| Lexical MRR | **0.9868** | 0.6453 |
| +Embed MRR | 0.7982 (-19.0%) | **0.8550 (+32.5%)** |
| +Rerank MRR | 0.7625 (-22.8%) | 0.6953† (-18.7%) |
| **最佳方案** | Lexical-only | **Lexical+Embed** |

**核心结论**：
- **小语料（18 docs）**：jieba 分词精准 + 术语固定 → lexical recall 饱和 → embed 引入噪音
- **大语料（966 docs）**：候选空间大 + 近义表达多 → lexical recall 不足 → embed 语义匹配补充召回
- **reranker 语言不匹配**：两种规模下 `ms-marco-MiniLM-L-6-v2` 均降低质量，需多语言 reranker

### 5b.5 性能数据

| 指标 | Lexical-only | Lexical+Embed | +Rerank |
|------|------|------|------|
| 评测总耗时 | 596s（393 query） | 580s（393 query） | ~30min/120 query（未完成） |
| 单 query 平均 | ~1.5s | ~1.5s | ~15s（含 timeout 重建） |
| 模型加载次数 | 0 | 1 | 2（每次 Pool 重建重新加载） |
| 失败/跳过/超时 | 0/0/0 | 0/0/0 | 0/0/未记录 |

---

## 6. 后续工作

### 6.1 多语言 reranker

- `ms-marco-MiniLM-L-6-v2` 在中文上无判别力（AI 导论 -22.8%，MIRACL zh -18.7%）
- 需切换 `BAAI/bge-reranker-v2-m3`（多语言，568M 参数，CPU 推理慢）
- 或使用中文专用 reranker（如 `BAAI/bge-reranker-base`）

### 6.2 ~~大规模中文 benchmark~~ ✅ 已完成

- ~~当前 18 docs 规模太小，lexical recall 已饱和~~
- ~~待网络恢复后下载 MIRACL zh（4.9M docs, 393 queries）或 DuReader~~
- **已完成**：通过 `hf-mirror.com` 镜像下载 MIRACL zh，构建 966 docs qrel-coverage 子集，三档评测完成（rerank 部分评测 120/393）
- **结论**：大规模中文语料上 Embed 显著优于 Lexical（MRR +32.5%），验证了"大规模语料才能体现 embed 召回补充价值"的假设

### 6.3 R17 双向生长图扩散（v2）

- 同一 qrels，对比图扩散是否进一步降低 Noise@k
- 突破 RRF Top-K 的召回上限

### 6.4 5183 doc 全量评测

- 当前因 `search_body_locate` C 扩展间歇性 segfault 仅用 783 doc 子集
- 待修复 C 扩展后跑全量验证

---

## 7. 数据文件归档

### 7.1 英文 SciFact

| 文件 | 内容 |
|------|------|
| `benchmarks/beir_scifact/results_gold_subset_lexical_fixed.json` | Lexical-only 基线（298 queries） |
| `benchmarks/beir_scifact/results_embedding.jsonl` | Lexical+Embedding per-query 结果（300 queries） |
| `benchmarks/beir_scifact/results_embedding_summary.json` | Lexical+Embedding 聚合指标 |
| `benchmarks/beir_scifact/results_rerank.jsonl` | +Rerank per-query 结果（300 queries） |
| `benchmarks/beir_scifact/results_rerank_summary.json` | +Rerank 聚合指标 |
| `benchmarks/beir_scifact/_pool_emb.log` | P1 Pool 评测进度日志 |
| `benchmarks/beir_scifact/_pool_rerank.log` | P3 Pool 评测进度日志 |

### 7.2 中文 AI 导论

| 文件 | 内容 |
|------|------|
| `benchmarks/ai_zh/kb_gold/` | 18 docs + sidecars 的 Memoria KB |
| `benchmarks/ai_zh/eval/queries.json` | 38 条中文 query |
| `benchmarks/ai_zh/eval/qrels.json` | query → relevant kp_id 映射 |
| `benchmarks/ai_zh/results_lexical.jsonl` | Lexical-only per-query 结果 |
| `benchmarks/ai_zh/results_lexical_summary.json` | Lexical-only 聚合指标 |
| `benchmarks/ai_zh/results_embed.jsonl` | Lexical+Embed per-query 结果 |
| `benchmarks/ai_zh/results_embed_summary.json` | Lexical+Embed 聚合指标 |
| `benchmarks/ai_zh/results_rerank.jsonl` | +Rerank per-query 结果 |
| `benchmarks/ai_zh/results_rerank_summary.json` | +Rerank 聚合指标 |

### 7.3 MIRACL zh（大规模中文）

| 文件 | 内容 |
|------|------|
| `benchmarks/miracl_zh/raw/queries.tsv` | MIRACL zh dev queries（393 条，原始 TSV） |
| `benchmarks/miracl_zh/raw/qrels.tsv` | MIRACL zh dev qrels（原始 TREC qrels） |
| `benchmarks/miracl_zh/raw/corpus_subset.jsonl` | qrel-coverage 子集（966 docs） |
| `benchmarks/miracl_zh/kb_gold/` | 966 docs + sidecars 的 Memoria KB |
| `benchmarks/miracl_zh/eval/queries.json` | 393 条中文 query |
| `benchmarks/miracl_zh/eval/qrels.json` | query → relevant kp_id 映射 |
| `benchmarks/miracl_zh/results_lexical.jsonl` | Lexical-only per-query 结果（393 queries） |
| `benchmarks/miracl_zh/results_lexical_summary.json` | Lexical-only 聚合指标 |
| `benchmarks/miracl_zh/results_embed.jsonl` | Lexical+Embed per-query 结果（393 queries） |
| `benchmarks/miracl_zh/results_embed_summary.json` | Lexical+Embed 聚合指标 |
| `benchmarks/miracl_zh/results_rerank.jsonl` | +Rerank per-query 结果（120/393，部分评测） |
| `benchmarks/miracl_zh/results_rerank_summary.json` | +Rerank 聚合指标（部分） |

---

## 8. 复现步骤

```bash
# === 英文 SciFact ===

# 1. 确保 HF cache 已下载模型
#    sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
#    cross-encoder/ms-marco-MiniLM-L-6-v2

# 2. 设置环境变量
export CUDA_VISIBLE_DEVICES=""
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# 3. 运行 P1 多模型评测（约 7 分钟）
python scripts/benchmark/_pool_emb.py
python scripts/benchmark/_aggregate_emb.py

# 4. 运行 P3 rerank 评测（约 17 分钟）
python scripts/benchmark/_pool_rerank.py
python scripts/benchmark/_aggregate_rerank.py

# === 中文 AI 导论（小规模，18 docs） ===

# 5. 构建 KB + eval 文件
python scripts/benchmark/build_ai_zh_kb.py

# 6. 运行三档评测（约 2 分钟）
python scripts/benchmark/_run_ai_zh.py

# === MIRACL zh（大规模，966 docs） ===

# 7. 下载 MIRACL zh 数据（需 hf-mirror.com 镜像）
$env:HF_ENDPOINT="https://hf-mirror.com"
python scripts/benchmark/_download_miracl_zh.py

# 8. 构建 KB
python scripts/benchmark/build_miracl_zh_kb.py

# 9. 运行三档评测（Lexical ~10min, Embed ~10min, Rerank 部分评测）
python scripts/benchmark/_run_miracl_zh.py
```
