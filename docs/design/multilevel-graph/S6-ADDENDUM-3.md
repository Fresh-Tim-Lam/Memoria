# S6 增补 3（S6-ADDENDUM-3）：`run_id` 公式与 S2 对齐（文本更正）

> **性质**：S6 冻结文本与上游 S2 冻结语义冲突的**文本更正**；不改 S0–S5/S7–S10 语义。
> **依据**：S2-7（六元组）+ S2-10（切 H/A 维度不改变簇）；S6-4 自注「（S2 六元组）」。
> **决定**：`dec-20261104-b2runid`（Lead，随 B2 实现裁决）。
> **状态**：S6 身份仍为 `40f12e5f…` + ADDENDUM-1/2/3。

## 1. 更正

S6-4 原文：

```
run_id = sha256(level|view_family|dimension|edition|params_hash|algorithm)
```

**更正为（S2-7 六元组，维度不参与）**：

```
run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id,
                          algorithm_id, algorithm_version, params_hash))
```

## 2. 理由

- S2-10 冻结：**A 维度不产生/不改变簇**——同 DataSource + params 下切换 H/A，cluster run 不变；
  若 `run_id` 含 `dimension_id`，切维度即换 run，直接违反 S2-10。
- S6-4 自己标注「（S2 六元组）」⇒ 以 S2 为准。
- 实现已按 S2-7，并钉 `run_id` 与 dimension 无关的不变式测试。

## 3. 变更控制

- 本增补只更正 S6-4 文本；改簇算法/维度语义须重开 S2/S6。
