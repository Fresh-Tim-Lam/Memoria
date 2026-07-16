# 检索基准：权威数据集 → Memoria 知识库

> 2026-07-10。针对痛点：**用户对 KP 刻画不完善 → 检索召回差、精度低、无关信息多**。  
> 用可复现的 **qrels + 多档 KP 元数据 profile** 量化 SearchKernel 迭代效果。

---

## 1. 痛点建模

Memoria 检索单元是 **已确认 KP**。引擎只能索引 sidecar 里用户给出的信号：

| 用户刻画程度 | sidecar 状态 | 典型检索表现 |
|--------------|--------------|--------------|
| **Gold** | id + name + tags + description + range 正文 | 高 Recall@k、低噪声 |
| **Minimal** | id + name + range，无 tag/description | 依赖 name/正文 token，易漏同义 query |
| **Skeleton** | id + 敷衍 name（如 doc id），仅正文 | 无关 KP 易因正文词共现进入 Top-k |

基准的目的不是替代用户测试，而是 **固定语料与 query**，对比：

1. 同一引擎在不同 profile 下的 **Recall@k / MRR / nDCG@k / Precision@k**
2. SearchKernel 版本迭代（v1 → v1.5 hybrid → v2 图扩散）的 **相对提升**
3. **噪声率**：Top-k 中无 qrel 标注的 KP 占比（刻画「引入无关信息」）

---

## 2. 权威数据集选型

| 数据集 | 来源 | 规模 | 选用理由 |
|--------|------|------|----------|
| **SciFact**（BEIR） | [UKP BEIR](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip) | ~5.2k 文档、300 test queries | IR 社区标准；claim 式 query 贴近「找知识点」；体积适合本地 |
| **NFCorpus**（备选） | 同上 BEIR 系列 | ~3.6k 文档 | 更长文档，测 description/正文权重 |
| **CMedQA / 自建中文**（二期） | 医疗 QA | 大 | 验证拼音、中文分词；需单独清洗 |

**首版实现：SciFact**。每条 corpus 文档 → **1 个 KP**（`kp_id = doc_id`），qrels 直接映射为 `expected_kp_ids`。

---

## 3. Memoria KB 转换规则

### 3.1 目录

```
benchmarks/beir_scifact/
  raw/                    # 下载的 zip 解压（gitignore）
  kb_gold/                # profile=gold
  kb_minimal/
  kb_skeleton/
  eval/
    queries.json          # [{query_id, text}]
    qrels.json            # {query_id: [kp_id, ...]}
```

### 3.2 单文档 → md + sidecar

- **md**：`corpus/{doc_id}.md`，`# {title}\n\n{text}`
- **sidecar**：`.memoria/sidecars/corpus/{doc_id}.memoria.yaml`
- **range**：`start.snippet = # {title}`，`end.snippet = text` 末句（或全文末行）

### 3.3 Profile 差异（仅 sidecar 元数据）

| 字段 | gold | minimal | skeleton |
|------|------|---------|----------|
| `name` | corpus title | title | `{doc_id}` |
| `tags` | `["scifact", "science"]` + metadata 关键词 | — | — |
| `description` | abstract 前 240 字 | — | — |
| range / 正文 | 全量 | 全量 | 全量 |

正文相同 → **profile 差异纯测「元数据刻画」对检索的影响**，符合产品痛点。

---

## 4. 评测指标

对每条 query，调用 `search_kernel.search()`，取 `results[].kp_id` 排序列表。

| 指标 | 含义 |
|------|------|
| **Recall@k** | 相关 KP 是否出现在 Top-k |
| **MRR** | 第一个相关 KP 的排名倒数均值 |
| **nDCG@k** | 分级相关性（BEIR qrel score 0/1） |
| **Precision@k** | Top-k 中相关占比 |
| **Noise@k** | Top-k 中 **不相关** KP 占比（= 1 − Precision@k） |

可选分桶：按 query 长度、是否含专有名词、profile 档位输出 CSV/JSON 报告。

---

## 5. 工具链

```bash
# 1. 下载 BEIR SciFact 并生成三档 KB
python scripts/benchmark/build_scifact_kb.py --profiles gold minimal skeleton

# 2. 跑 Lexical 评测（CI 可用 tiny fixture）
python scripts/benchmark/run_search_benchmark.py \
  --kb benchmarks/beir_scifact/kb_gold \
  --qrels benchmarks/beir_scifact/eval/qrels.json \
  --queries benchmarks/beir_scifact/eval/queries.json \
  --modes lexical --k 5 10

# 3. pytest（仓库内 tiny fixture，无需下载）
pytest tests/unit/benchmark/ -q
```

实现代码（**开发工具，不在 `src/memoria` 产品包内**）：

| 模块 | 路径 |
|------|------|
| 指标 | `scripts/benchmark/metrics.py` |
| SciFact 加载/建库 | `scripts/benchmark/beir_scifact.py` |
| 统一 eval | `scripts/benchmark/eval.py` |
| CLI | `scripts/benchmark/build_scifact_kb.py`、`run_search_benchmark.py` |
| CI fixture | `tests/fixtures/benchmark_retrieval_tiny/` |

---

## 6. 与路线图关系

- **R09 / SearchKernel v1.5（R18）**：SciFact 上报告 aux + 多模型 + proposals 的 ΔRecall / ΔNoise
- **R17 双向生长**：同一 qrels，对比图扩散是否进一步降低 Noise@k
- **R16 反馈**：显式+隐式事件 → weights.json → MRR 变化

---

## 7. 原则

1. **基准 KB 与 examples/ 分离**，大体积 raw/generated 不入 git（见 `.gitignore`）
2. **tiny fixture 入 git**，保证 CI 无网络可跑
3. 每次 SearchKernel 行为变更，跑 tiny +（本地）全量 SciFact 对比表
4. 中文场景 **不强行用 SciFact 代表**；二期加 CMedQA 子集或 `example-boonie` 人工 qrels
