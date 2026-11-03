# S3 增补 1（S3-ADDENDUM-1）：VM 节点白名单扩展 presence/rule_id

> **性质**：S3 变更控制允许的「加字段」修订（S3-visual-v1.md §6），**不重开 S3、不改变 S3 任何核心规则**。
> **依据**：S4 冻结候选 `S4-render-v1.md` R-S4-4/R-S4-10；S3 freeze `dec-20261103-def8efcf`。
> **状态**：随 S4 一并冻结；S3 冻结身份仍为 `0ca4ea0e890aa7408a361ae97dbb4d8a8f06df60b1e191cbcb7d46ca5322cd6b` + 本增补。

## 1. 问题

S3-visual-v1 §S3-12 的 VM 节点白名单为：
`id/kind/label/role/member_count?/aggregate_count?/representative?/root_exempt?/range_ok?/layout_group?{semantic:false}`，
**不含节点 presence/rule_id**（S3-5 的 presence 只是边）。而 S4 要求「全部候选节点/边逐条 presence+rule_id」，
否则无法解释「为什么这个节点没出现」。若把节点决策只放 AdmissionResult、VM 不放，会形成两处事实源。

## 2. 增补内容（只加字段）

VM 节点白名单扩展为（新增两项，均为 **view-status** 字段）：
```
nodes[]: id / kind / label / role / member_count? / aggregate_count? /
         representative? / root_exempt? / range_ok? /
         layout_group?{semantic:false} /
         presence? ∈ {shown, suppressed, unknown} / rule_id?
```
- `presence/rule_id` 只表达 S4 的取景结果，**不改变**节点事实（kind/label/type 等）；
- Renderer 仍只渲染 `presence=shown` 的节点；`suppressed/unknown` 保留审计/度量；
- 边白名单不变（已含 `presence?/data_edge_ids?`，`data_edge_ids` Renderer 禁读）；
- S3 其余条款（渲染接口/事件/label/无簇/预算/可访问性）**完全不变**。

## 3. 机检

1. VM schema 节点含 `presence?/rule_id?`；
2. 节点事实字段与 DataSource 一致（presence 不改变事实）；
3. Renderer 只读 shown；未知 presence 值 fail-closed。

## 4. 变更控制

- 本增补为字段追加；若未来需改 presence 语义/取值范围，必须重开 S4 或 S3（按主规则）。
- S3 冻结身份 = 原 sha + 本增补文件；两者都被改动才视为破坏冻结。
