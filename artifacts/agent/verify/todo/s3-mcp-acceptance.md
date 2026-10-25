# S3 MCP 薄绑定独立验收（task-122）

> **验收者**：arch-contract。**对象**：agent-arch 的 S3 交付（`mcp_server.py` + 两个 fixture + 契约文档）。
> **方法**：独立复跑 + 复算 sha + **改坏实现验判别力** + **自己开 stdio 子进程当 MCP 客户端发 JSON-RPC**。
> **结论：通过（附 1 条已知限制 + 3 条观察）**。
> **未改 `src/**`**（两处改坏验证均已还原，`git diff` 为空），未 commit。
> **HEAD**：`570ccf6c`

---

## 0. 结论

# **通过**

| # | 查项 | 结论 |
|---|---|---|
| ① | 判别力（改坏验证） | ✅ **两处改坏都真的红/抖动，还原后都复好** |
| ② | 协议面对齐官方 schema | ✅ **我自己当客户端发请求，13 项全 PASS** |
| ③ | W1–W4 在 MCP 边界守住 | ✅ 含 **snippet 不偷发 handle**（Lead 最担心的一条） |

**已知限制 1 条**（按 Lead 要求登记为非缺陷，见 §5）。

---

## 1. ① 判别力（改坏验证，不做假通过）

### 1.1 基线（改坏前）

`mcp_binding.py` 连跑 3 次：**sha 单一 `0d32ed36`，全 PASS**。

### 1.2 改坏 A：去掉 `<HANDLE>` 稳定化 ⇒ 应出现不同 sha

改 `mcp_binding.py::_stable()`：删掉 `_HANDLE_RE.sub("<HANDLE>", value)`。

| run | 结果 | sha |
|---|---|---|
| 1 | PASS | `b1196690…` |
| 2 | PASS | `b32ad6ff…` |
| 3 | PASS | `10936627…` |

**⇒ 3 次跑出 3 个不同 sha**，且**三次都仍 PASS** —— 这正是 Lead 抓到的 flaky 形态：
**「绿但不稳定」**。证明 `<HANDLE>` 稳定化**真的在起作用**（它在时 sha 稳定，不在时抖动）。

**还原后**：连跑 3 次 sha 回到单一 `0d32ed36`。

### 1.3 改坏 B：`_next_txid` 改回内存自增 ⇒ 应出现 FAIL

改 `mcp_server.py::_next_txid()`：从"复用 `kb.py` 扫盘实现"改成"内存自增 `-01`"（即 agent-arch 第一版踩过的第二份分叉实现）。

| run | 结果 | 详情 |
|---|---|---|
| 1 | PASS | — |
| 2 | PASS | — |
| 3 | **FAIL** | `重读后写=backup_failed` |
| 4 | **FAIL** | 同上 |
| 5 | PASS | — |

**⇒ 5 次里 2 次 FAIL（间歇性 = flaky 特征），失败原因正是 `backup_failed`（txid 撞批次）**。
这与 agent-arch 记录的教训（"重启后 `_tx_seq` 归零 ⇒ 撞批次 ⇒ 6 次跑 3 红 3 绿"）**完全吻合**。

**还原后**：连跑 5 次**全 PASS，sha 单一 `0d32ed36`**。

### 1.4 还原完整性

```
git diff src/memoria/services/agent/mcp_server.py   → 空
git diff scripts/benchmark/maintenance/mcp_binding.py → 空
```
两处改坏**零残留**。

### 1.5 判别力结论

**两处改坏都真的触发了预期症状**（A=sha 抖动、B=间歇性 FAIL），且还原后都复好。
⇒ `mcp_binding.py` 的稳定性与 `_next_txid` 的唯一实现**都是被 fixture 真正钉住的**，不是"碰巧绿"。

---

## 2. ② 协议面：我自己当 MCP 客户端（不采信报告）

**方法**：起真实 stdio 子进程（`python -m memoria.services.agent.mcp_server --kb <tmp>`），
手工构造 JSON-RPC 帧从 stdin 发、从 stdout 读。**不 import 任何 agent-arch 的断言辅助**。
脚本留档：`artifacts/agent/verify/todo/s3-acceptance-client-probe.py`。

**结果：13/13 PASS**

| # | 断言 | 实测 |
|---|---|---|
| 1 | `server/discover` required 齐全 | `missing=[]`；实有 `cacheScope/capabilities/resultType/supportedVersions/ttlMs` ✅ |
| 2 | `tools/list` required 齐全 | `missing=[]`（`cacheScope/resultType/tools/ttlMs`）✅ |
| 3 | 工具数量 | 4 把：`outline/section/snippet/propose_write` ✅ |
| 4 | **W1 无直写工具** | 除 `propose_write` 外无任何 write/edit/patch/apply 类 ✅ |
| 5 | `propose_write` 语义 | 描述明写"按计划写库（唯一写入口；无直写工具）…必须带 read_handle" ✅ |
| 6 | `tools/call` required 齐全 | `missing=[]`（`content/resultType`）✅ |
| 7 | 未实现方法 | `-32601` ✅ |
| 8 | 非 JSON | `-32700` ✅ |
| 9 | 版本不匹配 | `-32022` ✅ |
| 10 | **W2 snippet 不发 handle** | `read_handle=None`，正文无 `rh-` ✅ **（Lead 最担心的一条）** |
| 11 | W2 section 给出 handle | `rh-NOz7xUCe…` ✅ |
| 12 | W2 无可信 handle 直写 | 被拒 + 文件未变 ✅ |
| 13 | W2 伪造 handle | 被拒 + 文件未变 ✅ |

### 2.1 一处需要点明的口径细节（非缺陷）

第 13 项我最初期望错误码是 `WRITE_GATE_BYPASS`，实测返回的是 **`FS_NOT_OBSERVED`**
（"没读过 d.md —— 请先用 outline/section 读它、拿到 read_handle"）。

**这是正确的拒绝**：伪造的 `rh-FORGED…` 服务端查不到观察记录，因此报"没读过"。
**安全性上等价**（伪造 handle 无法获得任何写权限），只是**错误码口径**与
`WRITE_GATE_BYPASS` 不同。建议：契约文档若声称"handle 伪造 ⇒ `WRITE_GATE_BYPASS`"，
应改为"伪造 ⇒ `FS_NOT_OBSERVED`（因为服务端查不到该 handle 的观察）"，**错误码是契约面，别写错**。

---

## 3. ③ W1–W4 在 MCP 边界（逐条）

| 守卫 | 实测 | 结论 |
|---|---|---|
| **W1** 只有入口、无直写 | `tools/list` 4 把，除 `propose_write` 外无写类；其描述明确"产 plan + 必须带 read_handle" | ✅ |
| **W2** snippet 不构成"看过" | `snippet` 返回 `read_handle=None`，正文无 `rh-` token | ✅ **未偷发** |
| **W2** 无 handle / 伪造 handle 写 | 两者均被拒，文件 sha 未变 | ✅ |
| **W3** 备份失败零写入 | `mcp_binding.py` 断言 `code=backup_failed, sha不变=True`（我复跑确认在 PASS 输出里） | ✅ |
| **W4** 外部 `approval=auto` + 有写权限 | `mcp_binding.py` 断言 `APPROVAL_REQUIRED` | ✅ |

---

## 4. 我自己复算的数字（不采信自报）

| 项 | 我的复跑 | Lead/agent-arch 自报 | 一致 |
|---|---|---|---|
| `mcp_binding.py` 10 次 | 连跑 3 次 + 5 次区间，全 PASS，单一 sha **`0d32ed36`** | `0d32ed36` | ✅ |
| `mcp_protocol.py` | 连跑 2 次，单一 sha **`226075ff`** | `226075ff` | ✅ |
| `pytest -q tests` | **1462 passed / 0 failed** | 1462 passed / 0 failed | ✅ |

---

## 5. 已知限制（**按 Lead 定性：不是缺陷**）

### L1 未与真实 MCP 客户端对拍

- **事实**：环境无 MCP SDK/客户端；`Tool`、`ServerCapabilities` 两处**内部字段**因官方页面截断未逐字对拍。
- **agent-arch 已主动披露**，且文档 §8 明写「不得声称已验证兼容」。
- **判定：这是已知限制，不是缺陷。** 理由（采纳 Lead 的定性）：
  1. 它**主动披露**，没有把未验证说成已验证；
  2. 无 SDK 环境下，「逐字对拍 schema + 自己当客户端发请求」（= 本报告 §2 做的事）**已是能做到的上限**；
  3. 判成缺陷会诱导下一个人去"补一个假的兼容性声明"——那比诚实披露更糟。
- **触发条件（何时必须处理）**：**首个真实 MCP 客户端（Claude Desktop / Cursor / DSH 等）联调时，必须做一次完整的协议面对齐**，
  重点核 `Tool` / `ServerCapabilities` 两处内部字段与本报告的 13 项。
- **在此之前**：可以交付，但**不得对外声称"已与 MCP 客户端验证兼容"**。

---

## 6. 三条观察（非阻断，但需记录）

| # | 观察 | 建议 |
|---|---|---|
| O1 | **工作区不干净（与 Lead 说的不同）**：`docs/example/AAA_Vocab/` 有 65 个 tracked 文件被改（mtime 为 **10-23 / 10-24**，非本轮）+ `src/memoria/services/agent/ask_stream.py` 也有改动（mtime **10-12**） | 这些**不是 S3 fixture 造成的**（`mcp_binding.py` 用 `tempfile.mkdtemp`，不碰 docs/example），是**更早的历史遗留**。建议 Lead 收口前确认归属并 `git checkout` 干净，否则"git status 干净"这个前提不成立 |
| O2 | **handle 伪造的错误码口径**：契约若写 `WRITE_GATE_BYPASS`，实测是 `FS_NOT_OBSERVED` | 建议契约文档 §4 更正（错误码是契约面） |
| O3 | `mcp_binding.py` 的 W2 断言**接受了多个错误码** | 已核对：不影响安全性（文件未变即判过），但"具体哪个码"未钉死；建议后续收紧 |

---

## 7. 复现

```bash
cd D:/AAA_Jupyter/Memoria
# 判别力（改坏验证已还原，当前应全绿）
python scripts/benchmark/maintenance/mcp_binding.py     # sha 0d32ed36
python scripts/benchmark/maintenance/mcp_protocol.py    # sha 226075ff
# 我自己写的客户端探测（13 项）
python artifacts/agent/verify/todo/s3-acceptance-client-probe.py
# 全量
python -m pytest -q tests                               # 1462 passed
```
