# Memoria MCP 薄绑定（0.5.0-S3 / task-122）

> **定位**：MCP 是**交付形态之一，不是硬需求**（R-L2 / R-R4）；且**不以"省 token"为立项理由**（N1 实测：
> 组 B 比组 0 贵 11.10/18.49/14.24%）。它的独特价值只有两条：**跨进程互操作** + **跨边界可观测**。
> **实现**：`src/memoria/services/agent/mcp_server.py`（**零新依赖**：不引入 `mcp` SDK / pydantic / anyio）。
> **验收**：`scripts/benchmark/maintenance/mcp_protocol.py`（协议+schema 预算）、`mcp_binding.py`（W1–W4+端到端+重启）。

## 1. 接入方式（本地 stdio，客户端 spawn 子进程）

```bash
python -m memoria.services.agent.mcp_server --kb <知识库根目录>
```

- 传输：**stdio**，`newline-delimited` JSON-RPC 2.0（UTF-8），日志一律走 **stderr**；
- 无会话握手、无 HTTP 端口、无后台服务：**客户端 spawn 就活，退出就死**；
- 与桌面应用**共库格式**（`<kb>/**/*.md` + `.memoria/**`），不新增事实源。

## 2. 覆盖子集（**逐项声明：这是 MCP 2026-07-28 的子集，不是"符合规范"**）

| RPC / 能力 | 状态 | 说明 |
|---|---|---|
| `server/discover` | ✅ 实现 | spec **MUST**；返回 `DiscoverResult` required：`cacheScope/capabilities/resultType/supportedVersions/ttlMs` |
| `tools/list` | ✅ 实现 | `ListToolsResult` required：`cacheScope/resultType/tools/ttlMs` |
| `tools/call` | ✅ 实现 | `CallToolResult` required：`content/resultType`；请求 required：`_meta/name` |
| `notifications/cancelled` | ⚠️ 只接收 | stdio 的取消通知；本 server 请求都短，忽略而不报错 |
| `initialize` 时代握手 | ❌ 不实现 | 只支持无状态时代；旧版本 ⇒ `-32022`（**不做静默降级**） |
| `resources/*` | ❌ 未实现 | 不在最小集（读能力由 3 把读工具承担） |
| `prompts/*` | ❌ 未实现 | 同上 |
| `sampling/*` / `roots/*` / `elicitation/*` | ❌ 未实现 | 且这些在 2026-07-28 已**弃用**（新实现不应采用） |
| `tasks/*` / `input_required`（MRTR） | ❌ 未实现 | 本 server 只返回 `resultType:"complete"` |
| 进度通知 / 订阅 / `list_changed` | ❌ 未实现 | 工具集静态（4 把） |

> 未实现的 RPC 一律返回 **`-32601 Method not found`**（`mcp_protocol.py` 有断言），**不假装支持**。

## 3. 最小工具集与 schema 上限

| 工具 | 语义 | 是否签发 `read_handle` |
|---|---|---|
| `outline(file)` | 标题树（标题 + 行号区间 + 行数） | ✅ |
| `section(file, heading\|line, path?, near_line?, part?)` | 单节正文 | ✅ |
| `snippet(file, query\|line, ctx_lines?)` | 命中窗口（≤5 窗） | ❌ **不签发、不记观察** |
| `propose_write(intent, ops, handles, approval?)` | **唯一写入口**（plan 形态；无直写工具） | — |

- **schema 实测**：4 把工具 schema = **544 tok**（`tokens_estimated`，N1 静态口径 1.5 CJK/3.5 其他）；
  上限设 **1,450 tok**（N1 实测 35 工具 ≈ 4,349 tok 的 1/3）。断言在 `mcp_protocol.py`（超上限即红）。

## 4. 安全边界：W1–W4 在**进程边界**复跑

| 不变量 | 在 MCP 边界的落法 | 必红断言 |
|---|---|---|
| **W1 入口唯一** | 工具面只有 4 把，**无任何直写工具**；写只能 `propose_write(plan)`，走 `validate_plan → preview_plan → apply_plan(origin="agent", gate_token)` 唯一写者链 | 工具名列表 + "无 handle 即拒" |
| **W2 读后写** | 读成功 ⇒ 签发 `read_handle`（绑 `(kb, rel, sha256)`）；`snippet` **不签** | ④ `snippet` 后写 ⇒ `FS_NOT_OBSERVED` |
| **W3 写前备份** | `apply_plan` 第一步 `snapshot_pre_images`；失败 ⇒ 零写入 | 注入备份失败 ⇒ 文件 sha 不变 |
| **W4 审批在分发前** | `approvals.WRITE_CAPABILITY.require_approval()` 在调用工具前执行；外部不得 `auto` | `approval=auto` ⇒ `APPROVAL_REQUIRED` |

### 4.1 `read_handle` 设计（spec SEP-2567：无状态协议里的跨调用状态用**服务端签发 handle**）

```
outline/section 结果 → structuredContent.read_handle = "rh-<secrets.token_urlsafe(32)>"
服务端进程内表：token → (kb_path, rel_path, sha256, expires_at)
propose_write 的每个 op 目标文件必须带 handles[rel_path]=token：
  缺 token            ⇒ FS_NOT_OBSERVED
  token 无效/过期/被淘汰 ⇒ WRITE_GATE_BYPASS
  token.sha ≠ 现盘 sha  ⇒ FS_STALE_VERSION
```

- **不可猜测**：`secrets.token_urlsafe(32)`（**不用** `random` / 递增 id / 路径哈希）；同一文件读两次得到不同 token，两者都有效；
- **有界**：`TTL = 1800s`（30 分钟）+ `max_entries = 1024`（超出按 LRU 淘汰最久未用）；淘汰/过期后再用 ⇒ **响亮失败** `WRITE_GATE_BYPASS`；
- **诚实边界**：handle 防"客户端伪造"，**不防**"同一客户端多逻辑会话共享进程表"（本地 stdio、同一 OS 用户，信任域不变）。

### 4.2 W2 为什么不在 MCP 边界"降级"
`observation` 是进程内状态、按 `(kb, session_id)` 记账；MCP 无协议 session。本实现的解法是
**进程内固定 owner `mcp-stdio`**（stdio transport 由客户端 spawn ⇒ 进程生命周期 ≈ 客户端会话）
**+ 服务端签发 handle 作为对外契约**。⇒ **W2 语义完整保留**（未读即写、读后被改都会被拒）；
消费方可观察到的契约只有 handle，不依赖我们内部用哪个 session 键。

## 5. 无状态语义（协议无状态 ≠ server 无内部状态）

- **协议层**：每次请求自带 `_meta`（`io.modelcontextprotocol/protocolVersion` + `clientCapabilities`），
  不依赖握手，也不依赖任何会话 id；**缺失/不匹配 ⇒ `-32022`**；
- **进程内**：`read_handle` 表与 `observation` 表都是内存态；**重启 ⇒ 两表皆空 ⇒ 客户端必须重读**
  （与 `observation` 既有"不跨会话存活"一致）。`mcp_binding.py` 有"重启后旧 handle 无效、重读后可写"的断言。
- **txid 只有一份实现**：`mcp_server` **复用** `tools/kb.py::_next_txid`（扫 `session_dir` 里已占用的编号）。
  第一版曾在此文件内写"内存自增 `-01`"的第二份实现 ⇒ 重启后同一秒生成已被占用的 txid ⇒ `backup_failed`
  ⇒ 验收脚本 flaky（6 跑 3 红）。**教训：同一概念写两遍，第二遍必然漏掉第一遍的经验；并行事实源 = 缺陷。**

## 6. 兼容性

- 只支持 **`2026-07-28`**；**不提供** 2025-11-25 的 `initialize` 回退（三理由：两套握手语义无法一人维护；
  老客户端属上一代；**回退会把"版本不匹配"从响亮失败变成静默降级**——正是本项目一路在防的形态）。
- 版本不匹配的错误信息含**可操作提示**（带 `_meta` 版本 / 使用 2026-07-28 客户端）。

## 7. 六个月复盘口径（X-1，写死在此，避免"做了就忘"）

复盘**只看三件事**，且**复盘结论不决定"做不做"**（既定方向），只决定"优化 / 加文档 / 调工具集"：

| 指标 | 采集方式 | 用途 |
|---|---|---|
| 调用量（工具调用次数 / 会话） | server stderr 日志（本地、不含正文） | 判断工具集是否被用、哪些工具从未被调 |
| 外部客户端数 | 接入文档分发渠道 + `clientInfo` 上报（若有） | 判断"跨进程互操作"价值是否兑现 |
| 维护成本（改 schema / 改协议面的工时） | 变更记录 | 若成本 > 收益，只收缩工具集，不下线 |

## 8. 已知缺口（诚实，不留到验收）

1. **未与真实 MCP 客户端对拍**：环境无 `mcp` SDK / 无客户端，本实现只做了 **schema 逐字自校验**
   （`DiscoverResult`/`ListToolsResult`/`CallToolResult` 的 required 全部来自官方 `schema.json`）。
   首个真实客户端联调时可能需要对齐 `Tool` / `ServerCapabilities` 内部字段（这两处官方 schema 页面被我抓到时已截断）。
2. **未实现**：resources / prompts / sampling / roots / elicitation / tasks / 进度通知 / 订阅（见 §2）。
3. **取消**：`notifications/cancelled` 只接收不处理（请求都短；长任务若引入需要真正中断）。
4. **写幂等**：仍与 S2 一致 = 重复 txid 被拒（`backup_failed`），非真幂等。
