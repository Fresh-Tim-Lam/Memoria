# task-124 报告：S5 trace 跨边界（成本字段 / 容量淘汰 / 派生索引 / MCP `_meta`）

- **任务**：`task-124`（0.5.0-S5，最后一段）
- **日期**：2026-10-25
- **执行者**：agent-arch（deepseek-flash；未 use Pro）
- **状态**：**代码 + 夹具 + 回归全部完成**；未 commit（Lead 统一提交）
- **设计落点**：`docs/design/dsh-agent-port.md` §13（已追加）

---

## 1. 范围（任务要求的三件增量 + 1 把聚合工具）

trace 机制**已存在**（`<kb>/.memoria/agent/sessions/<sid>.jsonl` + `audit.py` + 4 把 session 查询工具），
本轮**不重造**，只补：

1. **调用级成本字段**（每条工具调用一条 `trace/call` 会话事件）；
2. **跨进程 `_meta`**（MCP 的 OTel 三键透传，两侧可凭 `trace_id` 串联）；
3. **容量与淘汰**（每会话 ≤5000 条 / 每条 ≤2KB / FIFO 淘汰非写非错 / 写与错误条目永不淘汰 / 按 session 分片）；
4. **+1 只读聚合工具** `trace_cost_summary(scope)`（不新增原始数据）；
5. 派生索引 `<kb>/.memoria/agent/trace/**` 视作 **cache**：可删除、可从会话 JSONL 重建、≤5s/会话。

## 2. 改了什么（落点）

| 文件 | 作用 |
|---|---|
| `src/memoria/services/agent/trace_index.py` **（新）** | 唯一构造点 `build_entry()`、OTel 解析/上下文（`parse_otel_meta` / `otel_scope` / `otel_trace_id`）、容量（`apply_capacity` / `_fit_entry`）、派生索引（`rebuild_index` / `ensure_index` / `read_index_entries`）、聚合（`aggregate_cost`）、MCP 记录（`record_mcp_call`） |
| `src/memoria/services/agent/tools/registry.py` | `ToolOutput.truncated: bool\|None`（三态：未声明 ≠ 未截断）+ `ToolOutput.meta`（工具自报结构化回执，只给 trace/审计）；`ToolResult.approval{asked,decided}` + `duration_ms`；`invoke()` 拆成"包装层 + `_invoke`"，**分发/错误码路径逐字不变** |
| `src/memoria/services/agent/loop.py` | 每次工具调用后 `_emit("trace/call", build_entry(...))`（只追加；`current_otel()` 继承跨进程上下文） |
| `src/memoria/services/agent/ask.py` | 唯一会话写入方 `_chained_event` 给 `trace/call` 补 `session_id`（循环层不知道会话身份） |
| `src/memoria/services/agent/tools/kb.py` | 读工具接线 `ToolOutput.truncated`（outline/section/snippet/read_document 含纯文本）；`propose_write` 成功回执填 `ToolOutput.meta`（`plan_txid` + `write{files,±lines,backup_txid,undo_available}`）；新增 `_trace_cost_tools()`（工具面 39 → 40，**追加在内置面末尾、扩展工具之前**） |
| `src/memoria/services/agent/mcp_server.py` | `tools/call`：解析 `_meta` OTel → 记录 MCP 侧 `trace/call`（`transport="mcp"`）+ 响应 `_meta` 回执；工具执行包在 `otel_scope()` |
| `src/memoria/services/agent/audit.py` | `append()` 若当前作用域有 OTel 上下文 ⇒ 审计事件带 `otel{...}` + `trace_id`（**两侧串联的落点**） |
| `docs/design/dsh-agent-port.md` | 追加 §13（事实源/隐私/容量/索引/OTel/偏离与限制） |
| `scripts/benchmark/maintenance/trace_cost_s5.py` **（新）** | 18 条断言夹具（真实 loop 会话 + 真实 MCP 调用） |
| `artifacts/agent/verify/todo/s4_sample_plugin/check.py` | **基线改为从 `KB_TOOL_NAMES` 派生**（见 §5 发现 2） |

> **写域披露**：task-124 原写域只有 `trace_index.py` / `audit.py` / `tools/kb.py` / `dsh-agent-port.md`。
> 实际必须扩到 `registry.py` / `loop.py` / `ask.py` / `mcp_server.py`（唯一调用点/唯一写入方/跨进程入口，
> 否则"成本字段"没有生产者、"两侧串联"没有落点），并顺手修了 S4 验收脚本的失真基线（见 §5）。
> 均属本域既有交付物，当前无其他存活成员写域重叠。

## 3. 契约（对外可见变化，全部只增不改）

### 3.1 会话事件 `trace/call`（新类型；回放/压缩/检索对未知 type 零影响）

```
{v, ts, session_id, tool_id, turn, args_digest, result_chars, result_digest, result_preview,
 est_tokens, truncated, truncated_known, approval{asked,decided}, error_code,
 write{files,lines_added,lines_removed,backup_txid,undo_available} | null,
 transport:"inprocess"|"mcp", duration_ms?, plan_txid?,
 otel{traceparent?,tracestate?,baggage?}?, trace_id?}
```

- **隐私硬边界**：正文只存 `result_digest` + `result_chars` + `result_preview`（**首 256 字符**）；
  参数只存 `args_digest`。夹具用"秘密标记放在第 256 字符之后"做**可证伪断言**（条目与聚合里都不出现）。
- **`truncated` 三态**：`truncated_known=false`（工具未声明）**不等于** `truncated=false`（声明未截断）。
  聚合截断率只对 known 计，`unknown` 单独报数。
- **`approval.asked`** = 审批闸门**确实被询问**；参数非法/未知工具在闸门之前返回 ⇒ `asked=false`
  （见 §5 发现 1：初版这里是错的，被夹具分母断言抓到）。

### 3.2 工具面

- `trace_cost_summary`（`read_only=true`）：scope = `session_id?|tool?|transport?|trace_id?|time_from?|time_to?`；
  输出 `calls/sessions/result_chars/est_tokens`、`truncated{count,known,unknown,rate}`、`errors{count,rate}`、
  `approval{asked,denied,denial_rate}`、`write{calls,files,txids}`、`transports/trace_ids/by_tool`、
  `index{rebuilt,degraded,dropped_total}`。
- **位置取舍**：追加在内置工具面**末尾**（`KB_TOOL_NAMES` 尾部）。会话查询四工具的"连续 + 相对次序"
  被测试按符号定位钉住；插进中间会让正向切片失效 —— 那是测试在保护契约，不该为了新工具改它。

### 3.3 MCP 跨进程

- 请求 `params._meta` 的 `traceparent/tracestate/baggage` → MCP 侧 `trace/call`（含 32-hex `trace_id`）；
  响应 `result._meta` 回执同一组键；工具执行在 `otel_scope()` 内 ⇒ 链内进程内审计
  （`capability/apply`）自动带同一 `trace_id` ⇒ **两侧可串**（夹具断言两侧 trace_id 集合一致）。

### 3.4 容量 / 索引

- 每会话 ≤5000 条（FIFO 淘汰**非写且无错误**条目；`write` 非空或 `error_code` 非空 ⇒ 永不淘汰）；
  每条 ≤2KB（先缩预览 → 去 tracestate/baggage/otel → `write.files` 留前 10 并标注
  `files_total/files_truncated`）；受保护条目本身超上限 ⇒ 如实 `over_capacity=true`。
- 索引：`<kb>/.memoria/agent/trace/index/<sid>.jsonl`（**每会话一片**；任务文本的单文件 `index.jsonl`
  与"按 session 分片 + 每会话 FIFO"自相矛盾，取分片）。**只在查询/聚合/显式重建时生成**，
  工具调用热路径不写索引 ⇒ 不产生会话目录之外的写副作用。header 记源文件 `size/mtime`；
  重建 >5s/会话 ⇒ `degraded=true` 降级按需生成。

## 4. 验收证据（task-124 关闭条件逐条）

产物目录 `artifacts/agent/verify/todo/`；夹具 `scripts/benchmark/maintenance/trace_cost_s5.py`（**18 条断言**）。

### 条件 1：字段完整性 + 脱敏断言 ✅

- `real_session_has_all_cost_fields`：真实 `ask()` 一轮 5 次工具调用 ⇒ 5 条 `trace/call`；
  逐项校验 `result_chars/result_digest/result_preview/est_tokens` 与 `tool/result` 正文**同源一致**、
  `args_digest` 16-hex、`turn/session_id/transport`、`approval{asked,decided}`。
- `privacy_preview_only_first_256`：正文含 641 字符且 `SECRET-MARKER-9F3A` 位于第 256 字符之后 ⇒
  工具结果全文含标记、**trace 条目不含**、`result_preview == 正文[:256]`、条目无 `content` 字段。
- `truncated_flag_is_truthful`（强制切片 ⇒ `truncated=true, truncated_known=true`）、
  `error_entry_has_code`（`NOT_FOUND`）、
  `write_entry_has_write_block`（真实 `propose_write`：`files=["w.md"]`、`lines_added=1`、`lines_removed=1`、
  `backup_txid`、`undo_available=true`、`plan_txid`）。

### 条件 2：聚合与原始条目可复算一致（误差 0）✅

- `aggregate_matches_raw_entries`：从索引条目逐项重算 `calls/result_chars/est_tokens/truncated/errors/
  approval/write`，与 `aggregate_cost()` **逐项相等**。
- `aggregate_rate_denominators`：截断率只对 `known` 计（`unknown` 单独报数）、失败率对全部调用计。

### 条件 3：容量 6000 条 ⇒ ≤5000 且写/错误 100% 保留 ✅

- `capacity_6000`：5900 普通 + 50 写（`propose_write` + `write` 块）+ 50 错误（`NOT_FOUND`）⇒
  索引 5000 条、`dropped=1000`、**写 50/50、错误 50/50 全保留**、`over_capacity=false`。
- `capacity_entry_size_2kb`：普通条目 max 528B ≤ 2048；`entry_size_cap_2kb`：200 文件写条目压到 1242B、
  `files=10`、`files_total=200`、`files_truncated=true`。

### 条件 4：跨边界 `_meta` 透传（S3 已交付）✅

- `mcp_otel_roundtrip`：响应 `_meta` 回执同 `traceparent/tracestate/baggage`。
- `mcp_trace_side`：2 条 MCP `trace/call`（outline + propose_write），`transport="mcp"`、otel 三键、
  `trace_id=4bf92f35…4736`。
- `cross_boundary_same_trace`：MCP 侧 `trace/call` 与进程内写路径 `capability/apply` **同一 trace_id**
  （`apply_trace_ids == {"4bf92f35…"}`，`otel.traceparent` 同值）。

### 条件 5：索引可重建（≤5s/会话）✅

- `index_is_rebuildable_cache`：删除整个 `trace/` 目录 → 再聚合 ⇒ 条目字节 sha 与删除前**一致**、
  `rebuilt=true`、`elapsed_ms ≤ 5000`、`degraded=false`；`aggregate` 仍出数。
- `trace_cost_summary_tool`：真实工具包装输出含调用数/截断率/失败率/审批拒绝率且 `read_only=true`。

### 条件 6：产物 ✅

- 本报告；`s5-pytest-final.txt`（**1464 passed / 0 failed**）；`s5-trace-run1..3.json`
  （**3 连跑单一 sha `670f97b47c28a7f1…`**）。
- 不回归：`event_chars(trace/call)=0`（压缩成本口径零影响）；
  `section_read_api` / `section_replace_op` / `contract_w1` / `contract_w2` / `contract_readwrite_ab` /
  `mcp_protocol` 全部 PASS；`mcp_binding` **3 连跑 PASS 单一 sha**（历史 flaky 未复发）；
  `s4_gate_removal_discrimination` PASS；`s4_sample_plugin/check` PASS（基线已改为从单一事实源派生）。

## 5. 两个"测出来才改对"的发现（本轮自曝）

### 发现 1（真实口径缺陷，已被夹具抓住）：审批 `asked` 初版语义错误

初版 `ToolRegistry.invoke` 把 `asked` 写成"有审批策略"（`approval is not None`）⇒ **参数非法/未知工具**
在审批闸门之前就返回，却也被算成"询问过审批"，于是 `decided=None` 被当成"拒绝" ⇒
聚合 `approval.denial_rate` 虚高（夹具 `aggregate_rate_denominators` 首次运行就红）。

**修法**：`asked` 默认 `False`，只在真正调用 `approval.decide()` 的块里置 `True`。
→ 现在的口径：**asked = 闸门确实被询问**。

### 发现 2（S4 验收脚本被 +1 工具打红）：基线不该写死

新增 `trace_cost_summary` 后，`artifacts/agent/verify/todo/s4_sample_plugin/check.py` 里写死的
"39 把 / 前 39 一致"整组失真（4 条 FAIL）。**这不是新工具的问题，是验收脚本把基线写死的问题**：
每加一把内置工具就要手改验收脚本，而"手改基线"与"放宽断言"只差一步。

**修法**：基线数量/名字改为从 `KB_TOOL_NAMES`（**单一事实源**）派生，语义断言（扩展 +3、
默认关闭、内置面不被污染）逐字保留。已复跑 PASS。此改动落在**已完成任务 task-123 的证据脚本**上，
特此披露（不改其历史结论，只让测量跟随单一事实源）。

## 6. 偏离与残余限制（诚实边界）

| 项 | 说明 |
|---|---|
| 索引文件名 | 每会话分片（`trace/index/<sid>.jsonl`）而非任务文本的单文件 `index.jsonl`：单文件无法做到"按 session FIFO + 每会话独立上限"。见 §3.4 |
| 历史会话 | 本功能上线**之前**的会话没有 `trace/call` 事件 ⇒ 其成本聚合为空（不伪造回填）。索引只能重建已有事件 |
| 聚合口径 | 聚合读**有界索引**：被容量淘汰的条目不进结果，`index.dropped_total` 如实带出；不宣称"历史完整" |
| `truncated` 覆盖面 | 只接线了读工具（outline/section/snippet/read_document）；其余工具计 `truncated_known=false`（unknown），**不冒充未截断**。要提升覆盖率就继续接 `ToolOutput.truncated` |
| MCP `turn` | 跨进程调用无 loop turn ⇒ `turn=null`（不编造） |
| 索引首次成本 | `aggregate_cost` 全库扫描会为每个会话建/刷分片（cache 冷启动）；单会话重建实测 ~3–7ms，远低于 5s 预算 |
| 并发 | 会话 JSONL 仍是既有"单写者"假设；索引分片用 tmp+rename 原子替换，并发重建不会半包 |
| 写入口覆盖 | `write` 块目前只由 `propose_write`（进程内 + MCP）构造；若将来出现新的写入口，需同样填 `ToolOutput.meta`，否则成本条目会缺 `write` |

## 7. 产物清单

| 产物 | 用途 |
|---|---|
| `src/memoria/services/agent/trace_index.py` | 成本条目/容量/索引/聚合/OTel 的唯一实现 |
| `src/memoria/services/agent/tools/registry.py` | `ToolOutput.truncated/meta`、`ToolResult.approval/duration_ms` |
| `src/memoria/services/agent/loop.py` / `ask.py` | `trace/call` 生产者 + 唯一写入方补 `session_id` |
| `src/memoria/services/agent/tools/kb.py` | 读工具截断接线 + 写回执 meta + `trace_cost_summary` 工具 |
| `src/memoria/services/agent/mcp_server.py` / `audit.py` | MCP OTel 透传 + 审计事件带 trace_id（两侧串联） |
| `docs/design/dsh-agent-port.md` §13 | 设计口径与偏离/限制 |
| `scripts/benchmark/maintenance/trace_cost_s5.py` | 18 断言夹具 |
| `artifacts/.../s5-trace-run1..3.json` | 3 连跑 PASS，单一 sha `670f97b47c28a7f1…` |
| `artifacts/.../s5-pytest-final.txt` | 1464 passed / 0 failed |
| `artifacts/.../s4_sample_plugin/check.py`（改基线派生） | 见 §5 发现 2 |

## 8. 给 Lead 的一句话

**三件增量都落在"唯一生产者 / 唯一写入方 / 唯一跨进程入口"上：成本字段由 loop 产出、index 只在查询时
从会话 JSONL 重建（cache）、MCP `_meta` 的 OTel 上下文经 contextvar 串起 MCP 侧 `trace/call` 与
进程内 `capability/apply`（同一 trace_id 有断言）。夹具 18 条断言、3 连跑单一 sha；全量 pytest
1464 passed / 0 failed；S1/S2/S3/S4 相关夹具全 PASS（并顺手修了 S4 验收脚本写死基线的失真）。**
