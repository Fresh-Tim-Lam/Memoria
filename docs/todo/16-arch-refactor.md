# 16. 架构重构 S1–S5（原定 0.5.0，**已撤回** → 内容归入 0.4.7） — 活跃详情（原文逐字）

> **本文件是 `docs/todo.md §16` 的活跃详情**（2026-10-26 索引化搬迁，**原文逐字**，未改写）。
> **状态事实源 = `docs/todo.md` 索引行**；本文件只放详情。历史归档仍在 `docs/design/**`，不在此重复。



## 原文（逐字，自 docs/todo.md 搬迁）

## 16. 架构重构 S1–S5（原定 0.5.0，**已撤回** → 内容归入 0.4.7）

> **⚠️ 2026-10-25 人裁决**：MINOR 位只保留给「架构级/范式级」变更（0.3→0.4 = 引入 DSH）；
> S1–S5 是能力增量 ⇒ **0.5.0 撤回**（Release 与 tag 已删除，commit `8067cde6` 保留在历史），
> 内容归入 **0.4.7**（S1–S5 代码本就是 v0.4.7 的祖先，随该版安装包发布）。门槛见 `version.md §2`。

> **依据**：辩论冻结 `artifacts/agent/verify/debate/PROTOCOL.md`（commit `48ca704e`）+ 26 条协议裁决 + R-L1..L3 + R-R1..R7 + R-D1..D3。
> **计划报告**：`artifacts/agent/verify/todo/agent-arch-plan-2026-10-25.md`（阶段详表/证据/风险/复跑命令）。
> **版本关系**：本 §16 原定 0.5.0，经人裁决后**归入 0.4.7**（不是独立版本）；验收仍按 R1 级做（已由 `task-139` 完成）。
> **不做**（裁决结论 7）：不移植 Cordis 宿主运行时（scoped layers/服务注册/bundle+preset 分层）、不移植 DSH 17 个 `dsh-*` 自用技能内容、不追 `skill-office`/`tool-workspace-dependencies`。

> **✅ 已发布 0.5.0（2026-10-25，第二次）**：tag `v0.5.0` → **annotated tag 对象 `b43306e4`**，**commit `8067cde6`**（两者不同：annotated tag 有自己的对象 sha；核对时勿混用）。资产 2 件（win64 约 1.18 GB / lite 约 35 MB）。
> **⚠️ 命名注意**：本次用 `Memoria-v0.5.0-lite.zip`（**漂移**，见 `AG108`）；canonical 是 `-win64-lite.zip`。已发布资产不改名。
> **⚠️ 勿引用 `release-0.5.0-record.md`**：那是**被撤回**的首次发布记录（tag `c7c5fb39`，12:26），与本次无关；本记录见 `8067cde6` 提交信息与 `release-0.4.7-record.md` §一（发布顺序）。
> R1 重验收 `task-139`（HEAD `093dac0e`）：五份旧验收逐条复核 + 必红重证明 + 12 剧本 12/12 + pytest 1474 passed，报告 `artifacts/agent/verify/todo/0.5.0-acceptance-reverify.md`。
> **0.5.0 body 保留更正声明**：S1–S5 代码已随 0.4.7/0.4.8 发布但当时未提（见 `8067cde6` 提交标题）。§16.1–16.5 原计划详情 → [design/ledger-archive-2026.md §10.10](design/ledger-archive-2026.md)。

***
