# steward 第五轮审计（r5）—— task-110：收据 sha 改为 LF 归一化内容 sha

> **触发**：task-110/SF-025（+ SF-031 一并处理）：收据 sha 之前是**工作区原始字节** sha，
> 跨平台不可移植（Linux CI / autocrlf=false 克隆会假红）。Lead 已批条款（org.md §2.6 B3 补充）。
> **处置**：改 `team_audit.py`（读校验口径）+ 跑 r5 重签（写入端同口径），历史收据不动。
> **审计者**：steward；**时间**：2026-10-26T08:xx+08:00；**git base**：`f2a415c5`（worktree 含未提交改动）

## 1. 本次实现（task-110）

| 改动 | 说明 |
|---|---|
| `content_sha256(path)` | `\r\n → \n` 后按字节算 sha256；**BOM 保留**（BOM 是内容的一部分；将来若 BOM 差异致假红再显式加归一化） |
| `steward_self_audit` 读校验 | `hashlib.sha256(read_bytes())` → `content_sha256(path)`（**读端**） |
| r5 收据（写端） | 5 个标准 sha 全用 `content_sha256`（**写端**；两端同口径，避免只改一边全红） |
| `--sha-explain <path>` | 并列输出 `raw_sha256` / `content_sha256_lf` / `git_blob_sha` / `head_blob_sha` |
| `STEWARD_STANDARDS` 5 项 | 加入 `scripts/agent/prompt_drift_check.py`（SF-031：它已进门禁，但收据不校验它 ⇒ 覆盖缺口） |
| selftest 双向判据 | ① LF/CRLF 同内容 ⇒ `content_sha256` 相同；② 原始字节 sha 不同（证明有判别力）；③ 旧口径（收据记原始 CRLF 字节 sha）必红；④ CRLF 工作区 + LF 口径收据必绿 |

## 2. 重读标准（sha256 = **LF 归一化内容 sha**，本机 raw 与 LF 恰好相同）

| # | 标准 | sha256（content-lf） |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | docs/guides/lead-dispatch-rules.md | `488d7ebd78c917e2…`（未变） |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | scripts/agent/team_audit.py | `d8f6a7d7f9b722a0…`（**task-110 变更**） |
| 5 | scripts/agent/prompt_drift_check.py | `6cbc9f8687e3a4d8…`（SF-031 纳入；prompt-owner 未提交改动） |

## 3. 验证

- `--selftest`：**PASS**（含 task-110 的双向移植性断言 + 旧口径必红 / CRLF 绿 fixture）。
- `--sha-explain scripts/agent/team_audit.py`：三列复算一致（raw==lf，git blob 可对账）。
- CRLF 样例：`--sha-explain artifacts/agent/verify/steward/r5/crlf-sample.txt` ⇒ raw≠lf，`raw_equals_lf=NO`。
- `team_audit.py --json`：**steward_self_audit = INFO（5/5 标准匹配）**；
  当前唯一 FAIL 见 §4（不是本任务产物）。
- `--determinism`：PASS（见报告记录）。

## 4. 当前唯一 FAIL（非本任务产物）

```
deliberation_quality dq6：未 git tracked 的辩论产物
  artifacts/agent/verify/debate/kgviz/PHASE2-UNION.md   ← 并行 kgviz 辩论产物，未提交
```
这是 J6' 的设计行为；**不属 task-110 写域**（我只写 team/steward/** + artifacts/agent/verify/steward/**），
需归属方/Lead 提交后自动转绿。本任务**没有为此放宽 dq6**。

## 5. 为什么必须跑 r5 而不是改旧收据

收据是"我何时用什么标准审计"的**历史证词**；改旧收据 = 事后篡改证词（append-only 原则，A3）。
正确处置是重读标准 → 新收据（r5），旧 r2/r3/r4 保留原样（它们记录的是当时口径，r2 甚至就是 CRLF 原始字节口径的证据）。

## blind_spots

1. 未在**真实跨平台克隆**上跑（本机 raw==LF）；移植性由 LF/CRLF fixture 双向断言证明，不是靠"本机没红"。
2. org.md §2.6 B3 的条款文字由 Lead 落盘（本任务按 Lead 消息视为已批，但文件改动不在我写域）。
3. 未审计并行 kgviz 产物内容；只按 dq6 报"未 tracked"。
4. `prompt_drift_check.py` 的 C1-C5 语义正确性属 prompt-owner/评审域，本轮只重读接口与口径。
