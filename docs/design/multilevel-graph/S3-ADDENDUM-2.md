# S3 增补 2（S3-ADDENDUM-2）：`EDGE_VIEW.rule_id?`（边抑制可解释）

> **性质**：S3 白名单字段追加（与 ADDENDUM-1 给节点加 `presence?/rule_id?` 对称）。
> **依据**：S4-10/R-S4-4（AdmissionResult 边逐条 `presence+rule_id`）；S4-6/R-S8-1（X-RULE 分母含边）；S3-12 边白名单。
> **状态**：S3 身份仍为 `0ca4ea0e…` + ADDENDUM-1/2；不重开 S3。

## 1. 变更

`EDGE_VIEW` 白名单追加：

```
rule_id?: string   （仅非 shown 边必填；shown 边可缺省）
```

- 与 `VM_NODE.rule_id?` 同义、同 11 类 `rule_id` 枚举；
- 只用于**解释/审计/抑制原因**（tooltip/G6/G7），**不参与布局/渲染几何**；
- `data_edge_ids` 仍仅审计、Renderer 禁读（不变）；
- 其余 S3-12 白名单字段不变。
