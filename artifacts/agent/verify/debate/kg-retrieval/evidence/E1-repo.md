# E1 · B 源取证：本仓代码现状（索引单元大小 / 知识点是否可作身份）

> **角色**：B 源（本仓代码，file:line）专职取证员；只回答「现状到底怎么做的」，不写提案。
> **冻结语料**：`artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理`
> —— 已校验与 `data/corpus-snapshot.json`（2026-10-27 14:09:46）**11 个 sidecar 的 sha256 全部相同**（探针 §1）。
> **方法**：读 `src/**` 源码 + 用 Memoria 自己的解析链跑冻结语料（只读，无写库）。
> **复跑**：`artifacts/agent/verify/debate/kg-retrieval/evidence/E1-repo-probe.py`（输出见同目录 `E1-repo-probe.out.txt`）。
> **纪律**：每条给 file:line；【事实】= 可直接复跑/读码确认；【判断】= 我的推断，单独标注。

---

## 0. 最关键 5 条（给 Lead 的摘要）

1. **读取侧四种粒度已实现，但预算极不对称**：`read_document` 有 2000 行 / 20,000 字符上限（`tools/kb.py:66,992`）；`section` 4000 tok、`outline` 800 tok、`snippet` 600 tok（`services/agent/section_index.py:51-56`）；**`read_kp` 完全无预算、无 offset/limit**，实测一个大 KP 回 13,409 字符 ≈ 4,870 tok（探针 §5b）。
2. **检索侧对 agent 只有 lexical 一条路**：`search_kb` 硬编码 `modes="lexical"`（`tools/kb.py:248`）；RRF 只在 `search_kernel.search()` 的 `both/full`（两者等价，`search_kernel.py:58-61`）且 semantic 可用时才走（`:103-123`）；`retrieval_fusion.fuse_search_results()` 的 `graph_hits` 通道**全仓无任何调用方**（`retrieval_fusion.py:145-161` 定义、grep 仅此一处）⇒ **graph 占位未启用**。
3. **检索单元 = sidecar 里的 KP**：词法索引只从 sidecar 的 `knowledge_points[]` 建记录（`services/lexical_index.py:163-190`），结果只有 `{kp_id,id,label,name,file,score,lexical_score,sources}`（`:591-600`）——**没有 line / char_range / snippet / evidence / source_hash**；行号要等 `search_kb` 二次解析（`tools/kb.py:265-288`）。冻结库 26 篇 md 只有 11 篇有 sidecar，覆盖约 46.4% md 字节（`data/kp_inventory.json`）。
4. **锚点定位只做「单行子串 + line_hint 优先」，且从不拒绝歧义**：`range/locator.py:33-64` 逐行 `needle in line`；hint 行命中即钉死（`:43-49`）；否则 hint±40 行窗（`:51-53`，`range/constants.py:2`）；仍无则全扫取首个（`:55,64`）；`resolve_range()` 不检查候选数 ⇒ 同名 snippet 只要 hint 行命中就 **ok=True 静默钉住**（设计 R1 的 `AMBIGUOUS_ANCHOR` 无实现）。
5. **写正文不在同一事务重算 range，也无失败自检**：`DocumentService.save_document()` 先原子写正文（`document.py:341-349`），随后**尽力而为**调 `_resync_kp_ranges_after_edit()`（`:373-380`，`except Exception: pass`），sidecar 才另写一次（`:476-477`）；失败只丢一个计数，不回滚、不报错、不校验 `range_ok/反转/span=0`。agent 的正文写入同样走这条（`services/agent/body_edit.py:322-358`）。

---

## 1. 读取侧：四种粒度的返回结构与 token 规模

### 1.1 `read_document`（`src/memoria/services/agent/tools/kb.py:293-334`，包装 `:1083-1094`）

【事实】
- 返回：`ToolOutput.text`（纯文本）+ `anchors=(…,)`。文本结构固定为「文档头 + 知识点清单（`文件:行号` + name）+ 正文窗口」（`:321-334`）；每个 KP 一个 anchor `{file,line,kp_id,name,snippet}`（`:319`）。
- 正文窗口：`DEFAULT_READ_LIMIT = 2000` 行，且声明为「默认且最多」（`:992,1089-1090`）；字符硬上限 `MAX_BODY_CHARS = 20_000`（`:66,1060-1066`）。
- **支持 `offset`/`limit`**：`offset` 1-based 正文行（frontmatter 已剥），越界转 `NOT_FOUND`（`:1085-1094,1055-1056`）；截断时 footer 给续读 offset 并把 `truncated=True`（`:1068-1080,334`）。
- 非 `.md` 文本走同一 `offset/limit`，但有 1 MiB 字节上限（`:3631,3666-3685`）。
- **知识点清单本身不计入 20,000 字符预算**（预算只作用于正文窗口 `_read_window`，`:1034-1080`；KP 行在 `:308-319` 先拼进结果）⇒ 返回总长可超 20k。
- range 解析失败的 KP **不标注失败**：`resolved.ok=False` 时回退 `line_hint`（`:310-319`）；hint 也缺才只写文件、不写行号。所以 `read_document` 会把「坏锚点」当正常行号展示。
- `.md` 缺 sidecar 时显示「该文档没有 sidecar 知识点」（`:326`）。

【实测（冻结语料，探针 §5b）】`教材/03_第3章_模拟信号的数字编码.md` 默认读取：
- 2,958 行文档、28 个 KP ⇒ 输出 **21,291 字符 ≈ 7,885 est tok**、`truncated=True`；
- `offset=1200, limit=200` ⇒ 9,407 字符 ≈ 3,921 tok。

### 1.2 `read_kp`（`tools/kb.py:337-377`，包装 `:3719-3732`）

【事实】
- 返回：文本「知识点 <id>（name）@ file:start-end」+ 可选 `tags/aliases/description`（`:357-368`）+ 正文 `body_lines[start-1:end]`（`:349-351`）+ 一个 anchor（`:370-377`）。
- **无 token/字符/行数预算，无 offset/limit，不切片**（整段 `start..end` 一次回）。
- 索引来源是**全库重建** `build_kp_index(kb_path)`（`:344`；`kp_index.py:37-73` 每次遍历全库 md + 全部 sidecar 并解析全部 KP，无缓存）⇒ 单次 `read_kp` 成本随全库规模线性增长。
- **不检查 `range_ok`**：`entry.start_line or 1`、`entry.end_line or start`（`:349-350`）。`KpIndexEntry.start_line` 只在 `range_resolved.ok` 时非空（`kp_index.py:58-65`）⇒ range 失败时回退到 **正文第 1 行**，静默返回错误内容。
- 同 id 多文件命中时取 `entries[0]`（`:347`），不报歧义。

【实测（探针 §5b）】
- `read_kp("nonuniform-quantization")`：`教材/03` 第 646-933 行（288 行）⇒ **13,409 字符 ≈ 4,870 tok**；
- 坏 range KP `img-ch2-4-13-随机过程的统计值`：输出头 `…@ img/ch02-4_随机信号分析.md:1-1`，正文是 `# 第2章 信号分析基础：随机信号分析`（82 字符）——即设计 §1.3 所指「坏了返回第 1 行且无感知」，**代码确认存在**。

### 1.3 `section`（`services/agent/section_index.py:441-596`，工具包装 `tools/kb.py:796-880`）

【事实】
- 返回「标题 + L行号区间 + h级 + 行数」头 + 节正文；超预算**自动切片**为 `part i/n` + `next_cursor`（`section_index.py:525-546,549-596`），按 `part` 续读；预算 `SECTION_MAX_TOKENS=4000`（`:52`），工具层 `max_tokens` ≥200（`kb.py:943`）。
- 选择器：`heading`（归一化）/`line`（#L 一等回退）/`path`（父级链后缀）/`near_line`/`level`；同名多候选且消歧不了 ⇒ `AMBIGUOUS_SECTION`（不取首个）（`:316-438`，工具描述 `kb.py:926-948`）。
- 自适应回退：目标节 token / 全文 > `WHOLE_DOC_FALLBACK_RATIO=0.5` 且整篇在预算内 ⇒ 直接回整篇（`:72,503-520`）。
- token 是**静态估算**（CJK 1.5 字/tok、其它 3.5 字/tok，`:91-97`），所有返回带 `tokens_estimated=True`（模块 docstring `:26-31`）。
- 非 md / 无 heading 有稳定错误码（`NO_HEADINGS`/`SECTION_NOT_FOUND`/`INVALID_SELECTOR`，`:81-88,341-386`）。

【实测（探针 §5b）】`section("3.2.3 混叠现象与低通抽样定理")` ⇒ 2,356 est tok、1 片；`section("3.3.4 非均匀量化")` ⇒ 4,826 est tok、切 2 片。

### 1.4 `snippet`（`section_index.py:627-715`，包装 `kb.py:882-905`）

【事实】
- 按 `query`（**子串、大小写敏感**，`:661-663`）或 `line` 取命中行 ± `ctx_lines` 窗口；默认 `ctx_lines=3`、上限 20（工具 schema `kb.py:962`；默认常量 `section_index.py:56`）。
- 硬预算 `SNIPPET_MAX_TOKENS=600`（`:53`）；最多 `SNIPPET_MAX_WINDOWS=5` 个窗口（`:75`）；预算按窗口均分（`max(80, budget/n)`，`:674-685`），窗口内先缩 ±ctx、仍超则截断单行字符（`:600-624`）。
- 返回 `windows[]{line_no,start_line_no,end_line_no,text,tokens,ctx_lines,chars_truncated}` + `match_count/shown/truncated`（`:687-715`）。
- 0 命中返回 `ok=True, windows=[], scanned_lines=…`（`:664-672`）。

【实测】`snippet(query="量化")` ⇒ 5 窗口、449 est tok。

### 1.5 `outline`（补充，`section_index.py:182-259`，包装 `kb.py:771-794`）
标题树 + 每节行区间 + 行数/块数，预算 `OUTLINE_MAX_TOKENS=800`（`:51`）；超预算三级降级（`:218-235`）；同名标题附 `preview`（`:198-216`）。实测 `教材/03` 32 heading、375 est tok。

### 1.6 工具结果的上下文边界
【事实】内置工具结果**没有统一截断**：`ToolRegistry._invoke()` 直接 `ToolResult(..., output)`（`tools/registry.py:332-347`），`ToolResult.content = output.text`（`:106-109`）；`EXT_TOOL_OUTPUT_MAX_BYTES` 只作用于**插件扩展工具**（`:410-441`）。⇒ 各工具的预算完全靠工具自己声明；`read_kp` 没有声明，故可无界。

---

## 2. 检索侧：模式、RRF、graph 占位、search_kb 硬编码

### 2.1 `search_kernel.search()`（`services/search_kernel.py:38-133`）
【事实】
- `modes` 默认 `"lexical"`（`:58`）；分支：`semantic` 只走语义（`:63-87`）；`both` 与 `full` **完全等价**（`use_rrf = mode in ("both","full")`，`:61`）——设计与 API 文档把 `both|full` 写成两种（`docs/design/search-kernel-v1.5.md:402`），代码不区分。
- RRF 只在 `both/full` 且 `search_semantic()` 返回 `available` 时执行（`:103-123`），`fusion` 标记 `"rrf"`（或 `"rrf+rerank"`）。
- semantic 是否可用由 UI 设置决定：`is_embedding_enabled() = bool(ui_settings.search.embedding_enabled)`（`embedding_provider.py:50-51`，设置缺省 `{}` 见 `storage/ui_settings.py:140-152`）⇒ **默认关**。
- `query_plan` 是占位：`query_plan_stub()` 返回 `expanded=[]`、只带 roles（`services/model_router.py` `def query_plan_stub`，注释「MT / alias 扩展在 1.5d 实现」）。
- 每次 `search()` 附加 `body_locate`（`:16-35`），但 `is_body_locate_enabled()` 默认 False（`body_locate.py:12-16`，同为 UI 设置）。

### 2.2 RRF（`services/retrieval_fusion.py`）
【事实】
- `RRF_K = 60`（`:7`）；通道权重 `lexical_explicit=1.0 / lexical_implicit=0.9 / semantic=1.0 / graph=0.5`（`:47-52`）；按 `sources` 拆显/隐式（`:55-65`）；`reciprocal_rank_fusion()` 标准 `w/(k+rank)`（`:68-94`）；融合后写 `rrf_score/channel_ranks/tier/confidence/score`（`:179-195`）；lexical-only 只做 tier/confidence 标注（`:198-209`）。
- **graph 通道是纯占位**：`fuse_search_results(..., graph_hits=None)` 参数存在、传了才会进 channels（`:145-161`），但**全仓没有任何调用方传 `graph_hits`**（`grep graph_hits` 只在本文件命中）。`DEFAULT_CHANNEL_WEIGHTS["graph"]` 因此永不参与计算（`:51`）。

### 2.3 `search_kb`（agent 工具，`tools/kb.py:241-290`）
【事实】
- **硬编码** `modes="lexical"`、`scope="kb"`、`limit=top_k`：`payload = search(text, kb_path=kb_path, scope="kb", modes="lexical", limit=top_k)`（`:248`）；`top_k` 默认 5、上限 20（`:64,573-578`）。
- 结果处理：`by_file` 每文件解析一次 KP map（`:271`，`_kp_map_for_file()` `:210-231`），行号优先 range 解析、失败回退 `line_hint`（`:222-225`）；输出 `文件:行号` + name + snippet + score（`:276-289`）；anchor 带 `{file,line,kp_id,name,snippet,score}`（`:279-288`）。
- 索引不可用时返回 `SEARCH_UNAVAILABLE`（`:250-254`）；0 命中提示「lexical 通道，库内 N 条 KP 记录」（`:256-263`）。
- 与 UI 检索的差异：UI `search_api()` 透传 `modes`（`presentation/api/ui.py:247-264` → `services/document.py:1629-1648`），前端在 embedding 打开时传 `"both"`、否则 `"lexical"`（`ui/static/app/js/search-settings.js:89,105,121,205`、`toolbar-search.js:151`）。**agent 侧无此通路。**

### 2.4 词法索引 = KP 级
【事实】`build_lexical_index()` 只遍历 `sidecar.knowledge_points[]`（`lexical_index.py:163-190`）；记录字段含 `kp_id/file/name/tags/aliases_explicit/kp_description/file_description/body_excerpt`（`:180-190`），`body_excerpt` 用 `range.start.line_hint..end.line_hint` 截 ≤2400 字符（`:66-75`）——**用的是 line_hint，不是解析后行号**。
⇒ 【判断】没有 sidecar 的 md 对 `search_kb` 不可见；agent 只能退回 `grep`（`tools/kb.py:1286-1376`）找正文。

---

## 3. 锚点侧：locator 判定 + sidecar KP schema

### 3.1 `locate_snippet` / `resolve_range`（`src/memoria/range/locator.py`）
【事实】
- snippet 先 `strip()` 再截断到 `SNIPPET_MAX_LEN=80`（`locator.py:13-15`，`range/constants.py:1`）。
- 匹配方式：**逐行子串** `needle in _norm(line)`（`:33-36`）；不做跨行、不做归一化（仅 `strip()`）。
- 判定优先级：
  1) `line_hint` 有效且 hint 行**包含** needle ⇒ 直接返回 hint 行（`forward_only` 时要求 hint ≥ search_from）（`:43-49`）；
  2) 否则在 hint±`HINT_WINDOW=40` 行窗内扫（`:51-53`，`constants.py:2`）；
  3) 窗口无候选再全扫（`:54-55`）；
  4) 有 hint ⇒ 在多候选中取**离 hint 最近**（`:60-62`）；无 hint ⇒ 取首个（`:64`）。
- `resolve_range()`：start 全局；end 从 start 起 `forward_only`（`:73-94`）；缺任何一端 ⇒ `start_snippet_not_found` / `end_snippet_not_found`；`end < start` ⇒ `end_before_start`（`:104-112`）；成功返回 `{ok,start_line,end_line,start_candidates,end_candidates}`（`:114-120`，类型 `domain/range.py:18-32`）。
- **多候选不构成失败**：`ok=True` 时仍可能 snippet 出现多次（候选只在返回里，`start_candidates/end_candidates`），调用方（`kp_resolver`）只读 `ok/start_line/end_line`（`services/kp_resolver.py:12-21`）。

### 3.2 sidecar 里 KP 的 schema（逐字段，事实）
**顶层 sidecar**（`{kb}/.memoria/sidecars/**/<stem>.memoria.yaml`，`storage/sidecar.py:75-98`）：`schema_version` / `file` / `description`（文件级，可选）/ `knowledge_points[]` / `links[]` / `edges[]`（后两者由 `validate_sidecar` 校验，`sidecar_validate.py:283-410`）。

**KP 对象字段**（读/写/校验位置）：

| 字段 | 类型 | 代码依据 | 现状 |
|---|---|---|---|
| `id` | str，必填、文件内唯一 | 校验 `sidecar_validate.py:193-199`；创建唯一性 `document.py:1566-1573` | 全库语义 id；跨文件重复时 `read_kp` 取首个（`kb.py:347`） |
| `name` | str，缺省仅 warning | `sidecar_validate.py:201-202`；缺省回退 id（`kp_index.py:61`） | 检索/展示名 |
| `range.start` / `range.end` | `{snippet: str, line_hint?: int}` | 类型 `domain/range.py:8-16`；校验要求 **两端 `snippet` 非空**（`sidecar_validate.py:260-272`）；`line_hint` 可缺（`import_engine.py:550-553` 只写 snippet） | 定位锚；snippet 写入时截 `SNIPPET_MAX_LEN=80`（`document.py:1537-1538`） |
| `tags` | list[str] | `sidecar_validate.py:204-211`；写入 `document.py:1922-1930` | 词法/语义字段 |
| `aliases` | list[str] | `sidecar_validate.py:213-220`；写入 `document.py:1946-1954` | 词法字段 |
| `description` | str | 不校验形状，写入 `document.py:1932-1933`；读 `lexical_index.py:186`、`read_kp`（`kb.py:362-363`） | **当前大库 0 条**（设计 §1.2 与实测一致：冻结语料 KP 层无 description） |
| `tag_candidates` | list[{tag, source∈system/user/feedback, status?}] | `sidecar_validate.py:222-241`；写入 `document.py:1935-1944` | 候选，未采纳也可检索（aux） |
| `alias_candidates` | list[{alias, source, status?}] | `sidecar_validate.py:243-250`；写入 `document.py:1956-1968` | 同上 |
| `description_candidates` | list[{text, source, status?}] | `sidecar_validate.py:251-258`；写入 `document.py:1970-1973` | 同上 |
| `weight` | number | **仅导入期写**：`import_engine.py:526,563`、`import_executor.py:197-198`；`validate_sidecar` 不校验、检索不读 | 冻结语料 0 条；属导入遗留字段 |

候选 `status` 允许 `candidate/selected/dismissed`（`sidecar_validate.py:116-130`）。

**代码里不存在**的 KP/slice 字段（`grep` 全 `src/memoria/**/*.py`）：`anchor_verified`、`section_number`、`slice_id`、`char_range`、`identity`、`source_hash`、`note`、`kp_ids[]`（`kp_ids` 只作为导入计划的内存字段出现在 `import_engine.py:26,223` / `import_plan.py:78,120`，**不落 sidecar**）。

【实测分布（冻结语料 357 KP，PyYAML 解析）】KP 字段出现次数：`id 357 / name 357 / range 357（start.snippet 357、start.line_hint 357、end.snippet 357、end.line_hint 357）/ tags 50`；**无 description / aliases / weight**。顶层 sidecar 只出现 `schema_version/file/knowledge_points`（11 个文件），`links` 3 个、`edges` 1 个。

---

## 4. 写入侧：正文写入是否同事务重算 range；失败有无自检

### 4.1 正文保存顺序（`services/document.py:319-386`）
【事实】`save_document(rel_path, body)`：
1. 读原文件、剥 frontmatter、`compose_markdown()`（`:335-340`）；
2. 原子写正文：`tmp` + `fsync`（可选）+ `replace_with_retry(tmp, full)`（`:341-349`）——**正文此刻已落盘**；
3. 清缓存、manifest 延迟 touch（`:353-361`）；图片注册表增量维护（`:366-370`，异常吞）；
4. **然后**才调 `_resync_kp_ranges_after_edit(rel_norm)`，整段 `try/except Exception: pass`（`:373-380`）；
5. 返回 `{"status":"ok","ranges_resynced":N}`（`:383-386`）。

⇒ **不是同一事务**：正文写与 sidecar 写是两次独立原子写（`save_document:349` 与 `_write_sidecar:291`）；中间失败会留下「正文已改、sidecar 未改」的漂移。没有任何回滚。

### 4.2 重算逻辑（`document.py:420-478`）
【事实】
- 逐 KP 调 `resolve_range(lines, start, end)`（`:455`）；
- 成功且 line_hint 漂移 ⇒ **只改 `line_hint`**，snippet 不动（`:456-464`）；
- 失败且错误为 `end_snippet_not_found` 且 start 已定位 ⇒ 从 start 起按下一个 heading（或文末）重建 **end 的 line_hint + snippet 截断**（`:466-475`）；
- 其它失败（如 `start_snippet_not_found` / `missing_snippet`）**不修**；
- 有变更才 `_write_sidecar()`（`:476-477`；`_write_sidecar` 会按 start.line_hint 排序、touch manifest、后台重建词法索引、失效 kp_targets，`:285-298`）。

### 4.3 失败自检
【事实】
- `save_document` 对 resync 的异常**静默吞掉**（`:377-380`），`status` 仍是 `"ok"`；调用方只能看到 `ranges_resynced` 计数，**没有** `range_ok/反转/span=0` 的校验结果。
- 结果：坏样本不会被拦住。冻结语料中 span=0 的 KP `test`（`教材/08` 第 4163 行）在 `range_ok=True` 下仍存在（探针 §2）；设计 §4.3 要求「重算后立即自检（range_ok / 反转 / span=0）」——**无实现**。
- agent 的正文写入同样走 `save_document`（`services/agent/body_edit.py:322-358`，`:344`），因此同样无事务/无自检。
- agent `propose_write` 路径额外有的「写后重跑校验」只是**把既有问题列成文本回执**，不阻断、不修复（`tools/kb.py:3391, 3775-3827`）；且它只覆盖该批次 `files`。
- KP 创建/改 range 走 `confirm_kp_range()`：会做行号合法性（`document.py:1522-1528`）、空行拒绝（`:1539-1552`）、`validate_sidecar(..., baseline=盘上基线)`（`:1580-1590`）——**创建时刻有校验，正文编辑时刻没有**。
- `set_kp_range` 在 agent plan 里是「未编译」（`services/agent/plan.py:1131`），agent 改 range 实际走 `upsert_kp → confirm_kp_range`（`services/agent/apply.py:21,104-105`）。

---

## 5. 已知冲突对账（⑤）

### 5.1 「358 KP / 98.9% / 8 坏」 vs 「357 / 98.6% / 5 坏」
【事实（均可复跑）】
- 冻结语料 = `corpus-snapshot.json` 14:09:46 的 11 个 sidecar，sha256 全等（探针 §1）。
- 冻结语料用 Memoria 自己的解析链：**357 KP，`range_ok=352`（98.60%），坏 5**：4 条 `missing_snippet`（`end.snippet` 为空串）+ 1 条 `end_snippet_not_found`；`span_zero=1`（`test`），`inverted=0`（探针 §2）。
- `validate_sidecar` 视角：**4 errors（`kp_range_missing_snippet`）+ 1 warning（`kp_range_relocate_failed`）**，受影响 KP = 5（探针 §3），与 `round2/gate-probe.json` 的 `M4_validate_kb.affected_kp_count=5` 一致。
- `data/kp_target.csv` 有 **357 行数据**（表头之外），`data/kp_inventory.json` 记 `n_kps=357`；`data/anchor_stats.json` 的 `per_kb["数字通信原理"].n = 358`。
- 358/98.9%/8 的算术关系：`start_ok_hint_verified=354 / n=358 = 98.88%`；「8 坏」= `start_ambiguous 4 + end_not_found 1 + end_ambiguous 2 + degenerate 1`（`anchor_stats.json` `target_kb`）。

【判断】
- **357 / 98.6% / 5 坏 是对的**（对冻结基线、对代码自身 `range_ok` 口径）；`358` 只能来自 `anchor_stats.json` 那次**未绑定快照的 live 目录探针**，而同目录同脚本的 `kp_target.csv` 只有 357 行、冻结快照也只有 357 ⇒ 358 在冻结基线上**不可复现**，应视为探针口径/时点漂移。
- 98.9% 与 98.6% 不是同一口径：98.9% 只统计 **start 端** hint 验证；代码的 `range_ok` 要求 **start+end 双端解析成功**（`kp_resolver.py:17-20`）⇒ 5 坏 = 98.60%。
- 「8 坏」也不是 `range_ok`：其中 4 条 start-ambiguous、2 条 end-ambiguous 在代码里仍 `ok=True`（hint 钉住），1 条 `end_not_found` 与 4 条 missing-snippet 才对应代码坏；degenerate 1 条（`test`）是 `ok=True` 但 span=0。**混用了三种口径**，不能与 5 坏直接比。
- 「含 1 条 range 反转 span=0」：冻结语料 **inverted=0**；只有 1 条 **start==end** 的 span=0（`test`）。【判断】这是把「退化 span」写成了「反转」。

### 5.2 A1：只改 `line_hint`、不改 `end.snippet`，`resolve_range` 还会不会 False？
【事实 + 反事实实验（探针 §4）】**会，仍然 False**：
- 4/5 坏 KP 的 `end.snippet` 是**空串**。`kp_resolver.resolve_knowledge_points()` 的条件是 `if start_spec.get("snippet") and end_spec.get("snippet")` 才调 `resolve_range`，否则直接 `{"ok": False, "error": "missing_snippet"}`（`services/kp_resolver.py:17-20`）⇒ 只改 `line_hint` **根本不会进入 locator**，`range_ok` 恒为 False。
- 第 5 条 `数字通信的特点`（`教材/01`）：start 解析成功，end snippet 是 80 字符（`SNIPPET_MAX_LEN` 截断，`document.py:1537-1538`），但正文已被改写成 3 行 + 插入了 `[[\c:yellow|…]]` 行内标记；`locator` **只做单行子串**（`locator.py:33-36`）⇒ 该 needle 在任何单行里都不存在。把 end.line_hint 依次改成 1 / 110 / 208 再跑，结果仍是 `end_snippet_not_found`；且 `locate_snippet` 直接定位该 snippet 也返回 None。
【判断】A1 只能更新位置提示，无法修复内容已不存在的锚点；至少要重写 `end.snippet`（并考虑多行/行内标记归一化），否则 5 条全不会转好。

### 5.3 `slices[]` 缺 `source_hash`
【事实】
- 本仓代码**根本没有 `slices[]` 这一层**：`grep "slices|slice_id|char_range|anchor_verified|source_hash|section_number"` 在 `src/memoria/**/*.py` 无命中（`kp_ids` 只出现在导入计划/链解析的**内存**结构中，不落 sidecar）；检索/读取返回里也没有 slice 结构（检索结果字段见 §2.4，读取只有 `anchors[]`）。
- `source_hash` 在 `src/**/*.py` **0 命中**；但**等价的源文件哈希已存在**：`manifest` 每条 md 记录 `md_sha256` / `md_size` / `md_mtime` 与 `sidecar_sha256`（`storage/manifest.py:35-62`），漂移审计正是比对 `md_sha256`/`sidecar_sha256`（`:238-302`）。
- 「缺 source_hash」这句话的来源是**研讨产物**：`round2/Q1-research.md:157` 的迁移步骤列了 `slices[]` 字段（含 source_hash），`round2/Q1-verify-addendum.md:102` 指出「材料 §4.C 的 slices[] 字段清单漏了 source_hash」——是**提案文档的漏列**，不是本仓实现的缺陷。
- 另：`round2/Q1-research.md:418` 声称「sidecar 当前仅有 `id/name/range.{start,end}.{snippet,line_hint}/tags`」——**与实测不符**，还漏了 `description/aliases/tag_candidates/alias_candidates/description_candidates/weight`（见 §3.2 表）；本报告以代码 + 全仓 sidecar 实测（含 build/dist 副本共 22,335 个 `*.memoria.yaml`，去重前）为准。

【判断】若新切片层要 `source_hash`，不需要新算哈希：`manifest` 已有 `md_sha256`，但它是**按文件**而非按切片；且 manifest 有 pending/延迟落盘路径（`manifest.py:75-110`），取用时要走 overlay，否则可能读到旧基线。当前 agent 侧检索结果不带任何哈希/版本 ⇒ 无法在结果里表达 stale。

---

## 6. 与 docs/design/** 及本体裁决的冲突清单

| # | 冲突点 | 设计/裁决 | 代码现状 |
|---|---|---|---|
| C1 | 坏锚点仍返回内容 | `kg-agent-index-v0.md:110`（R1 ① `range_ok==False → ANCHOR_UNRESOLVED`，不得返回第 1 行） | `read_kp` 用 `start_line or 1` 静默回第 1 行（`tools/kb.py:349-351`）；设计自己在 `:44-49` 已点名该缺陷 |
| C2 | 歧义锚点未拒绝 | `kg-agent-index-v0.md:111`（snippet 多次出现且无法消歧 → `AMBIGUOUS_ANCHOR`）、`:116-120`（消歧手段 A/B/C） | `locator.py:60-62` 取离 hint 最近/首个即 `ok=True`；无候选数判据、无 `context_hash`、无 `AMBIGUOUS_ANCHOR` 错误码 |
| C3 | 只有 `anchor_verified` 才准进上下文 | `kg-agent-index-v0.md:91`（slice 字段）、`:110`（P3 锚点自证） | 无 `anchor_verified` 字段/判定；`read_document`/`search_kb` 解析失败直接回退 `line_hint`（`tools/kb.py:222-225,310-319`） |
| C4 | 写入必须同事务重算 + 自检 | `kg-agent-index-v0.md:122-127`（§4.3「同一事务内重算…重算后立即自检 range_ok/反转/span=0；禁止事后补一条」） | 正文先落盘，再 best-effort resync，异常吞掉；无 span/反转自检（`document.py:341-386,420-478`）——**违反** |
| C5 | 切片 schema 落地 | `kg-agent-index-v0.md:80-93`（slice 含 `char_range/identity/kp_ids/description/anchor_verified/source_hash`） | 后端无切片层；sidecar 无这些字段（§3.2）；`source_hash` 代码 0 命中 |
| C6 | 检索结果应有 evidence | `docs/design/search-kernel-v1.5.md:402-404`（`results: [{kp_id, score, tier, sources[], evidence[]}]`、`query_plan.expanded/bridge_lang`） | 结果无 `evidence[]`（`lexical_index.py:591-600`）；`query_plan_stub` 的 `expanded=[]`（`model_router.py`） |
| C7 | `both` 与 `full` 是两种模式 | `search-kernel-v1.5.md:402` | `search_kernel.py:61` 视为同一 RRF 模式 |
| C8 | 「长度/行数/块数」不得作判据 | **本体裁决** `docs/design/kg-ontology-v0.md:156`「禁用判据 长度 / 行数 / 块数 —— 它们可相互抵消」 | 代码把这些当**预算/截断**用（`tools/kb.py:66,992`；`section_index.py:51-56`）= 允许的用法；**但若 E1 用「单元该多大（行数/字数/块数）」作通过/否决判据，则直接撞 L156**。当前代码没有任何「KP 尺寸合格线」，只有读取预算 【判断】 |
| C9 | 同 id 多文件应消歧 | 设计 P1「kp_id 是唯一语义身份」（`kg-agent-index-v0.md:56`） | `by_id` 是 list，`read_kp` 取 `entries[0]` 静默（`kb.py:347`；`kp_index.py:39,67`）——身份唯一性未在读取侧兜底 |

> 另：`kg-agent-index-v0.md:24`「358 KP，14:09:46 快照」与同一文档 `:40`「大库 0/357」**自相矛盾**；本报告 §5.1 已用冻结快照证明 14:09:46 = 357。

---

## 7. 对 E1 的直接含义（【判断】，不是提案）

1. **身份**：现状只有一种语义身份 = `kp_id`（sidecar → 词法索引 → FSRS/图/链接都挂它；`design P1:56`）。后端**没有**切片身份；若引入第二个 id，将与 `P1`/`P2`（slice_id 只做视图键，`kg-agent-index-v0.md:57-58`）以及「块 id 管身份、行区间管位置」的既有裁决（`docs/design/block-identity-design.md:184-185`）发生口径冲突——但块身份属于**前端渲染域**，不是后端可复用实现。
2. **单元大小**：以 KP 为单元时，实测尺寸跨度极大：p50 = 16 行 / 527 字 / 186 est tok，p90 = 75 行 / 2,919 字 / 982 est tok，max = 469 行 / 18,199 字 / 6,006 est tok（探针 §5a，n=352）；23.9% 的 KP >1,200 字。读取侧对"一个 KP"没有任何硬预算（§1.2），所以「KP 作单元」在**成本上**不可控，在**身份上**是稳定的。
3. **错切片风险点**已定位到三个可复跑机制：`end.snippet` 缺失（4/5 坏）、snippet 跨行/行内标记（1/5 坏）、无歧义拒绝（任意同名 snippet）。三者都不在「单元大小」维度上，而在「锚点自证」维度上——与 E1 的「该不该用知识点作身份」直接相关：**用 kp_id 做身份没问题；用 kp 的 `range` 做「可注入内容边界」目前不成立**（没有 gate、没有自检、预算不可控）。

---

## 8. 复跑 / 局限

- 复跑：`python artifacts/agent/verify/debate/kg-retrieval/evidence/E1-repo-probe.py`；输出快照 `E1-repo-probe.out.txt`。
- 探针只读：不写 kb、不写 sidecar、不建缓存（`tools/kb.py` 的只读守卫未触发写路径；`build_kp_index` 只读）。
- 局限：① 冻结语料只含 `数字通信原理` 一库，同仓 `artifacts/baseline-kb` 是另一份快照（329 KP / 12 sidecar，实测 324 ok = 98.48%，坏 5，口径与冻结库一致但数字不同——**引用基线时勿混用**）；② UI 检索的 `embedding_enabled`/`body_locate_enabled` 取决于用户 `ui-settings.json`，本报告只报「默认关」；③ 行号均为当前 HEAD 工作区实测，改动文件后需重取。
