# S5 trace 跨边界独立验收（task-124，0.5.0 最后一段）

> **验收者**：arch-contract。**对象**：commit `512513a7`（trace 成本字段 + 容量淘汰 + 索引 cache + MCP `_meta` 串联）。
> **方法**：读夹具代码验判据构造 + **改坏实现验隐私判别力** + 独立复跑 + 复算 sha + 逐条核自曝项。
> **结论：通过**（附 1 条须记录的理论边界 + 4 条已知限制）。
> **未改 `src/**`**（改坏已还原，`git diff` 为空），未 commit。**HEAD**：`512513a7`

---

## 0. 结论

# **通过**

| # | 查项 | 结论 |
|---|---|---|
| ① | 隐私边界真断言 | ✅ **判据真可证伪**（改坏后秘密标记真的出现在 trace 里并被抓） |
| ② | 容量淘汰保护 + 无界增长 | ✅ **不会无界增长**（单条 2KB 硬上限兜底），但有一条理论边界须记录 |
| ③ | 索引是 cache 不是事实源 | ✅ 热路径零写索引；删除后**条目行逐字节重建一致** |
| ④ | 跨边界 trace_id 串联 | ✅ 两侧 trace_id **真的相同**（非只写字段） |

**我复算的 sha**：`trace_cost_s5.py` = **`03ad9894f3d53940`**（20 条全 PASS）
**pytest**：**1464 passed / 0 failed**（独立复跑）

---

## 1. ① 隐私边界（最重要 —— 这是数据泄露面）

### 1.1 判据构造是否真可证伪（读夹具代码核）

`trace_cost_s5.py` 的判据设计：
```python
_SECRET = "SECRET-MARKER-9F3A"
long_body = "填充文本用于把关键信息推到第 256 字符之后。" * 18
# 同时其它节足够长，使目标节占比 <50% ⇒ 不触发 whole_document 回退（否则"首 256"会包含秘密）
```

**我独立验证了构造的前提**（非采信注释）：
```
_SECRET 在文档中的位置: 460          ← 确实在第 256 字符之后 ✅
文档总长: 1745
heading 数: 4 ['长文档','短节','长节','尾节']
```

**关键**：作者刻意避开了 `whole_document` 回退陷阱——如果目标节占比 >50%，工具会返回整篇，那么"首 256"就会包含秘密，判据就失效。这个陷阱被显式处理了（L141 注释 + 长尾节）。

### 1.2 我做的改坏验证（判别力的硬证明）

把 `trace_index.RESULT_PREVIEW_CHARS` 从 `256` 改成 `10000`（= 存全文）：

| | 结果 |
|---|---|
| 改坏后 | **`[FAIL] 隐私硬边界…`**，`preview_len=641`（全文都存了），且**输出里真的出现了 `SECRET-MARKER-9F3A`** |
| 还原后 | `[OK]`，`preview_len=256`，sha 回到 `03ad9894` |

⇒ **判据真的会红**，不是"看起来对"。**这是本次验收最重要的一条证据**。

### 1.3 顺带核的一个边界（Lead 问的）

**若正文正好 ≤256 字符，是否等于存了全文？**

- 实际情况：`text[:256]`，正文 ≤256 时 `preview == 正文全文` —— **技术上确实存了全文**。
- **但按设计这就是允许范围**（256 是明确的值域上限）。
- **文档是否说清**：`trace_index.py:21-24` 明写"`result_preview`（**首 256 字符**）"、`:94` "正文预览硬边界（隐私）：只留前 N 个字符 + 全文 digest + 长度"。
- **判定**：**不算违反**，因为 256 是**设计约定的允许范围**，且文档有明确表述。但建议在文档里补一句更明确的："≤256 字符的结果等价于全文入索引，这是已接受的边界"——避免后续有人误以为"永远不存全文"。

### 1.4 隐私字段清单核实

夹具 L244 断言条目含：`ts/tool_id/turn/args_digest/result_chars/result_digest/result_preview/...`
- `args_digest` 与 `result_digest` 都是 16-hex（**摘要而非正文**）✅
- 无任何"完整 args/result 正文"字段 ✅

---

## 2. ② 容量淘汰 + 无界增长风险（Lead 重点问的）

### 2.1 常规场景（夹具，我复跑）

```
6000 条 ⇒ entries=5000, dropped=1000
写路径 50 条 / 错误 50 条 ⇒ 100% 保留
每条 ≤2KB：max_entry_bytes=528, cap=2048
```

### 2.2 极端场景（**我独立构造**，Lead 最担心的）

**全部 6000 条都是写路径或错误**（`_protected()` 全为 True）：

```python
from memoria.services.agent import trace_index as tr
rows = [{'tool_id':'propose_write','write':{...}} or {'error_code':'E'} for _ in range(6000)]
kept, dropped, over = tr.apply_capacity(rows)
→ kept=6000, dropped=0, over_capacity=True
```

**实测结果**：
| 指标 | 值 |
|---|---|
| 条目数 | **6000（超过 5000 上限）** |
| dropped | **0**（一条都不丢） |
| `over_capacity` | **True**（如实标注） |
| 单条最大字节 | 78（**cap 2048，硬上限生效**） |
| 总量估算 | 0.45 MB |

### 2.3 判定：**不会无界增长，但有理论边界**

**为什么不会无界增长**：
1. **单条 2KB 是硬上限**（`_fit_entry` 在裁剪前对每条生效，L303）⇒ 每会话 trace 索引**最大约 5000×2KB ≈ 10MB**（正常）或 N×2KB（over_capacity 时）。
2. **写路径/错误条目数本身有天然上限**：一个会话的写次数与错误次数受会话轮次约束，不可能无限。

**必须记录的理论边界**（`over_capacity=True` 时）：
- 条目数**不再受 5000 约束**，只有 2KB/条 兜底。
- 若异常场景产生**海量错误条目**（如循环失败 100 万次），会是 100万×2KB ≈ **2GB**。
- **当前是不是缺陷？不是** —— 因为错误数受会话规模约束，且 `over_capacity` 如实标注（不假装 ≤ 上限）。
- **建议**（非阻断）：未来可加"over_capacity 时按字节总量再兜底"（如每会话索引总字节 ≤ 20MB），把理论边界也关掉。

**实现是诚实的**：`apply_capacity` 返回 `over_capacity` 并在 header 里落盘（`trace_index.py:403`），查询时也如实报告（夹具输出"索引：0 片重建、0 条被容量淘汰"）。**没有假装达成上限**。

---

## 3. ③ 索引是 cache 不是事实源

### 3.1 热路径是否真的不写索引（我的独立核查）

调用链核实：
```
_write_shard  ← 只被 rebuild_index（:408）调用
rebuild_index ← 只被 ensure_index（:437）调用
ensure_index  ← 只被 trace_cost_summary 类聚合（:444, :505）调用
```
⇒ **`loop.py` / `ask.py` 的每次工具调用路径里没有任何 `ensure_index` 调用**。
⇒ 索引**只在查询/聚合时生成**，热路径零写 ✅

### 3.2 删除后重建是否完整（我的独立实验）

**第一次实验失败（我的测试数据错，如实记录）**：我造的 JSONL 把字段放顶层，但 `trace_events()` 要求 `record["data"]` ⇒ `entries=0`。**这是我的测试没走被测路径**，不是实现缺陷。修正后重测。

**修正后的结果**：
```
首次:   entries=7 dropped=0 over=False bytes=1280
删除 trace/ 后重建: entries=7 bytes=1280
  -> 条目完整(7):        True  ✅
  -> 非 trace 未混入:     True  ✅
  -> 整文件字节一致:      False ⚠️
```

**追查字节不一致的根因**（不能只报"不一致"）：
```
header1 rebuilt_at: 1792901803068
header2 rebuilt_at: 1792901803072   ← 时间戳不同
条目行相同: True                     ← 条目行完全一致
```
⇒ **不一致只来自 header 的 `rebuilt_at` 时间戳**，**条目数据逐字节相同**。

**夹具的比较方式是正确的**（`trace_cost_s5.py:370-373`）：
```python
first_entries_blob = b"".join(
    line for line in open(shard,"rb").read().splitlines(keepends=True)[1:]   # [1:] 显式跳过 header
)
```
它**显式跳过 header**，只比条目行 —— 因为 header 含时间戳。**这是正确做法，不是漏比**。且它还额外验了 `calls` 数一致、`rebuilt=True`、`elapsed≤5s`、`degraded=False`。

### 3.3 「单文件 vs 分片」的偏离是否合理（Lead 要我判）

- 任务文本写 `trace/index.jsonl`（单文件），但同时要求"按 session 分片"+"每会话 5000 条 FIFO" ⇒ **自相矛盾**（单文件装不下 per-session 配额）。
- 实现取 `trace/index/<session_id>.jsonl` 每会话一片，并在 `trace_index.py:39-41` **写明了理由**。
- **我的判断：偏离合理**。理由：
  1. 两条要求本身冲突，必须二选一；
  2. "per-session FIFO 配额"是**功能要求**（有夹具钉住），"单文件"只是路径写法；
  3. 分片还带来**按需重建**（只重建被查询的会话）的性能优势。
- **建议**：在文档里把这条偏离登记为"已知偏离 + 理由"（现在已经写了，位置在模块 docstring，够用）。

---

## 4. ④ 跨边界 trace_id 串联

### 实测（夹具输出，我复跑确认）

```
MCP 侧 trace/call: transport=mcp, trace_id=4bf92f3577b34da6a3ce929d0e0e4736 (32-hex)
跨边界串起两侧：mcp_trace_ids=['4bf92f3577b34da6a3ce929d0e0e4736']
                apply_trace_ids=['4bf92f3577b34da6a3ce929d0e0e4736']
                applied=1
```

⇒ **两侧 trace_id 完全相同**，且：
- MCP 响应 `_meta` 回执了**同一 traceparent/tracestate/baggage** 三键 ✅
- 进程内写路径 `capability/apply` 通过 `otel_scope` contextvar 带上**同一 trace_id** ✅

**不是"只写了字段"**：`applied=1` 表示真的发生了一次 apply，且它的 trace_id 与 MCP 侧一致。⇒ **真的串起来了**。

---

## 5. 两条自曝项的核实

### 5.1 审批 `asked` 语义（它自曝"初版错，已改"）

**核实**：`registry.py:252` 注释 + `:253` 初始化 + `:315` 置 True：
```python
state = {"approval": {"asked": False, "decided": None}}
...
state["approval"]["asked"] = True      # ← 在审批闸门真正被询问时
```
注释明写：**「`asked` = 审批闸门真的被询问过（参数非法/未知工具在闸门之前就返回 ⇒ 不冒充询问）」**。

**判定**：✅ **现在的语义正确**。`asked` 只在真正 `decide()` 路径置 True，参数非法/未知工具**不会**计入审批拒绝率。

### 5.2 S4 验收脚本基线写死 39 → 改为派生（它自曝"污染了 task-123 证据脚本"）

**这是 Lead 最关心的一条**：它改的是**已验收任务（task-123）的证据脚本**。

**diff 核实**：
```diff
-        len(baseline) == 39,
+        base_names == list(BUILTIN_NAMES),
-        len(off) == 39,
+        len(off) == BUILTIN_COUNT,
```

**我的判断：没有放宽 task-123 的断言，反而更强**：
1. 旧版 `len(baseline)==39` **只比数量**；新版 `base_names == list(BUILTIN_NAMES)` **比名字+顺序**。
2. **关键**：task-123 的核心断言（"启用插件后前 39 把名字+顺序+read_only 逐项不变"）**原样保留**在 `check.py:169`：
   ```python
   names_on[:BUILTIN_COUNT] == base_names and all(ro_on[n] == base_ro[n] for n in base_names)
   ```
   这里 `base_names` 来自**无插件时实跑 `build_kb_tools()` 的结果**（L137），**不是** `KB_TOOL_NAMES`。
3. `KB_TOOL_NAMES` 只用于**确定切分点**（前 N 把），不用于断言内容本身。

⇒ **改的是"基线来源"，不是"语义断言"**。而且它自己写了警告注释：
> "基线只应从 `KB_TOOL_NAMES` 派生 —— 否则每加一把工具就要手改验收脚本，而'手改基线'与'放宽断言'只差一步"

**这条自省写得很好**，我认可。

---

## 6. 已知限制（如实登记，非缺陷）

| # | 限制 | 触发条件 / 影响 |
|---|---|---|
| L1 | `over_capacity=True` 时条目数无上限（只有 2KB/条兜底） | 极端场景（海量错误条目）下索引可达 GB 级；建议未来加"每会话索引总字节上限" |
| L2 | 正文 ≤256 字符时 `preview` 等价全文 | 设计允许范围，文档已表述；建议补一句更明确的说明 |
| L3 | 索引 header 含 `rebuilt_at` 时间戳 ⇒ 整文件字节不稳定 | **不是缺陷**：条目行逐字节一致，夹具正确跳过 header |
| L4 | 任务文本的"单文件 index.jsonl"被改为 per-session 分片 | 已写明理由（两条要求冲突），偏离合理 |

---

## 7. 复现

```bash
cd D:/AAA_Jupyter/Memoria
python scripts/benchmark/maintenance/trace_cost_s5.py    # 20 条, sha 03ad9894
python -m pytest -q tests                                # 1464 passed

# 隐私判别力（我已跑的改坏验证，当前已还原）
# 把 trace_index.RESULT_PREVIEW_CHARS 改 10000 ⇒ 隐私断言 FAIL，trace 里出现 SECRET-MARKER-9F3A
```
