# Q1 复核报告：KP 边界重算会付出什么代价

> **复核员**：agent-index-verifier（「agent 索引」板块专职研讨复核员）
> **复核对象**：`round2/Q1-research.md`（作者 agent-index-researcher，sha256 `01fda8ce49970139…`，28,816 B）
> 及其自算产物 `round2/data/q1-research.json`（`4313aab3772df609…`）、脚本 `round2/scripts/q1_research_probe.py`（`a222a8fcea21a568…`）
> 以及材料引用的 `round2/Q1-corpus-analyst.md`（`ca0cab2197b046a0…`）/ `12_q1_boundary_numbers.py`（`c602edffcb868023…`）/ `data/q1-numbers.json`（`bf6552559e0fcb4a…`）
> **快照**：`round2/frozen/数字通信原理`（MANIFEST `a4beaedc5f852816…`，26 md / 11 sidecar，14:09:46）
> **方法**：不复用研究员的解析/切片代码。用**产品真值**独立复算：
> `memoria.range.locator.resolve_range`（read_kp 实际依赖的解析器）、`heading_proposals.scan_headings`（全仓唯一 heading 实现）、
> `graph.collector.collect_graph_data` / `derive_*`（图谱真值）、PyYAML（sidecar 真值）。
> 复核脚本：`round2/scripts-verify/verify_q1_independent.py`（`ec0ff2718e2fddd4…`），产物 `round2/scripts-verify/out/q1-independent.json`（`6b9e526ca33705fa…`）。
> **纪律**：只读语料；未修改研究员任何文件；未建库、未 commit。一次只做 Q1。

---

## 0. 结论总表（逐条）

| # | 复核项 | 结论 | 一句话理由 |
|---|---|---|---|
| ① | 数字可复跑（连续跑 2 次一致） | **通过（有条件）** | 两个脚本各跑 2 次输出 sha256 完全一致；`q1_research_probe.py` 输出与其 data 逐字段一致（唯一差异是我打补丁造成的 manifest 相对路径）；但它每次运行都读活动库做漂移检查，`live_drift` 字段使产物非完全封闭 |
| ② | 口径一致（同人群/同快照/同定义） | **不通过** | 快照绑定是干净的，但**同一量的定义在材料内/材料间不一致**：D2 三口径标签错位（真实值 hint 536 / resolved-raw 522 / clamped 484 / heading 581）；与 corpus-analyst 同题数字冲突（1,714/+74% vs 1,931/+55%；54.9% vs 56.3%）；A2「会变」94.1% 实为 97.8%；anchor 99.7% 是后修复投影而非当前值 |
| ③ | 用户可感知变化有无夸大/漏项 | **不通过** | **漏项**：图谱**边**会变（我按产品真值复算：A1 62→56、+8/−14；A2 62→53、+21/−30），材料只写「图谱节点不变」；**夸大**：「6 条教材 KP 会被放大到 1.5–1.6 万字」实测只有 2 条；「+20.4%」用的是 clamped→heading 口径，read_kp 实际口径为 raw→heading（+16.0%）；「726 tok」用的是 clamped 长度，read_kp 实际用 raw end |
| ④ | 三个选项「失败回滚」是否真可执行 | **不通过（按字面）** | 「整批撤销一个 txid」只在 `apply_plan`/manual-force 写路径成立；普通 sidecar 写（`DocumentService._write_sidecar` → `atomic_write_yaml`）**只留单代 `.bak`，不建 txid**；`restore_batch` 是**顺序写、非原子**（中途 OSError 返回 `restore_failed` 与已写清单）；无跨库单事务；B 的「写锁窗口」在现有产品中不存在（`file_version` 只在 UI 保存入口做 base_version 乐观校验） |
| ⑤ | anchor_verified 算法是否按 R1 三判据实现 | **不通过** | 脚本用「clamp 后的 range_ok=100%」代替判据①（产品真值 352/357=98.6%，5 条坏）；判据②的消歧是**从当前正文事后重建**（section 唯一 / 前文 40 字），而 R1 §3.1 的复合 anchor `(section_number, ordinal_in_section, identity)` 在 sidecar 中**一个字段都没有**（实测字段仅 id/name/range.{start,end}.{snippet,line_hint}/tags）；判据③「超预算」未实现，且对非标题起点 KP 会误夹。表中 99.7% 是「clamp/A1 修复后」的投影，不是当前覆盖率 |
| ⑥ | 孤儿率 20%：算的是「切片→KP」还是「KP→切片」 | **不通过（口径未钉死，不能判过/不过）** | 他算的是**切片→KP**（切片零重叠=孤儿）；「KP→切片」方向恒为 0（切片只建在 KP 范围内，构造性自证）。而 headline 的 **0.0%** 取自「切片只建在有 KP 的 section」这个**自证 scope**；换成整文件 41.4% / 全库 71.8% 就翻盘。R2 只写「切片找不到所属 KP」没写分母 scope ⇒ 同一方案 0%→71.8% 都「正确」，阈值 20% 目前**不可执行** |

> 说明：本复核只判断「数字/结论能否进决策包」，不评价选型对错，也不提供替代方案。
> 但需要指出：材料 §0 推荐的三个支撑数中，**①孤儿率 0.0%** 与 **②anchor_verified 99.7%** 正是本报告判为不能进包的两项；**③用户数据改动=0** 成立但「回滚」表述不成立（见 ④）。即推荐结论的**数字底座尚未达到决策级**。

---

## 1. 我的独立数字 vs 他的数字（对照）

| 量 | 我的独立复算（产品真值/独立口径） | 他的材料 | 判定 |
|---|---|---|---|
| 快照 | 26 md / 11 sidecar；frozen 37/37 sha 一致；live 0/37 漂移；MANIFEST 与 corpus-snapshot 逐文件一致 | 同（§1） | ✅ 一致 |
| KP 数 / 人群 | 357（教材 71 / slides 285 / notes 1） | 同 | ✅ |
| start 是标题行 | 93.3% 全部 / 教材 66.2% | 同 | ✅ |
| **产品 range_ok（read_kp 实际依赖）** | **352/357 = 98.6%**；5 条 `end_snippet_not_found` | §3.2 报 352/357=98.6%（✅）；但 §7 表头写 range_ok=100%（clamp 后） | ⚠️ 同一份材料两个数，需并置标注 |
| 坏 KP 身份 | `img-ch2-4-13/17/29/36` + `数字通信的特点` | 同 5 条（与 gate-probe 的 validate_kb 4+1 对齐） | ✅ |
| 反转 / span=0 | 0 / 1（`test` @ 教材/08:4163） | 0 / 1 | ✅ |
| start snippet 多义 | 131/357 = 36.7% | 同（并解释与 A 方 132 的差） | ✅ |
| **end 需修复** | 产品候选语义：**57/357=16.0%**（缺失5+超边界17+end候选>1的37，有重叠）；全文 occurrence 语义：**80/357=22.4%** | **74/357=20.7%**（缺失5+多义54+超边界16） | ⚠️ 三种引擎三个数；材料未标「end 多义」是按全文 occurrence 还是候选端点 |
| **尺寸口径** | start(解析后)→end.line_hint **536**；resolved-raw **522**；clamped **484**；heading **581** | D2 写 hint=**522** / resolved=**484** / heading=581 | ❌ **标签错位**：522 实为 resolved-raw，484 实为 clamped，literal-hint 是 536 |
| 教材尺寸 | start(解析后)→end.line_hint 1,714；resolved-raw **1,686**；clamped **1,714**；heading **2,985** | "resolved p50 **1,714**"（实为 clamped） | ⚠️ 定义与标签不符 |
| 教材 >1200 | raw 53.5% / clamped 54.9% / heading 69.0% | 54.9%（resolved=clamped）/ 69.0% | ⚠️ 与 corpus-analyst「current anchor=56.3% / 1,931」冲突未解 |
| **A2「会变」** | **349/357 = 97.8%**（end<boundary 332 + end>boundary 17） | **336/357 = 94.1%** | ❌ 少算 13 条「当前 end 已超边界」的 KP |
| 总字数变化 | raw→heading：478,321→554,660 = **+16.0%** | clamped→heading：461,578→555,798 = **+20.4%** | ⚠️ read_kp 用 raw end，用户可感增长应按 raw 口径说明 |
| anchor（产品 ok 为前提） | ok 352；strict **63.0%**；section **98.3%**；context **98.6%** | strict 63.3%；section **99.7%**；context **100%** | ⚠️ 他 5 条 range 失败按「clamp 修复」算 verified ⇒ 99.7% 是修复后投影 |
| `比特率` 消歧 | 3 次 occurrence（182/186/233）同 section，但**前文 hash 互异 ⇒ context 可消歧** | §7 脚注称「section/context 都无法消歧」 | ❌ 与他自己表格（context=100%）及复算矛盾 |
| links / edges | **3 links（5 instances，1 个孤儿 target `通带抽样定理`）/ 26 edges（0 孤儿）** | 3 / 26 / 1 孤儿 | ✅ 一致（早期旧输出曾为 0，最终版已修） |
| 图谱真值 | 357 nodes / **62 edges**（contain 33 / reference 8 / extend 21） | 未给边数，只说 A2「图谱覆盖范围整体变大」 | ⚠️ 漏项，见下 |
| 图谱边 churn（A1） | **62→56：新增 8 / 删除 14** | 称「ids/链接/**图谱节点**不变」（未提边） | ❌ 用户可见的图谱**边**会变 |
| 图谱边 churn（A2） | **62→53：新增 21 / 删除 30** | 「图谱覆盖范围整体变大」 | ⚠️ 定性对，但量级未给 |
| 孤儿率（独立 leaf-section 口径） | 全库 26 md：1,071 片 / **61.5%**；9 个 KP 文件：604 片 / **31.8%**（字符覆盖 58.6%） | 41.4%（整文件 packed）/ 71.8%（全库 packed）/ 0.7%/0.0%（section-overlap） | ⚠️ 切片规则+scope 双敏感；**方向/分母未钉死** |
| 教材 08 单 KP | `test`（跳转测试节点），span=0 | 同 | ✅ |
| 复跑 | `q1_research_probe.py` 2 次 → `deef2f34…`（= 其 data `4313aab3…`，仅补丁路径差）；`12_q1_boundary_numbers.py` 2 次 → `bf655255…`（= 其 data） | 材料称可复跑 | ✅ |
| token 系数 | `data/token_calibration.json`：uniform **0.4247**（n=116） | 硬编码 **0.4237**，注释却写「按 data/token_calibration.json」 | ⚠️ 小项，「宣称≠事实」 |
| read_kp 坏 KP 实测 | `_read_kp(frozen,"数字通信的特点")` → 返回 `…@ 教材/01:1-1` + 第 1 行 `## 第1章 绪论`（静默错内容） | 引 R1 证据，非自测 | ✅ 我实测确认（真实用户可感知缺陷） |

---

## 2. 逐条复核（细节与证据）

### ① 数字可复跑 —— **通过（有条件）**

- 亲自跑 `12_q1_boundary_numbers.py`（路径补丁到我的 repro 目录，逻辑零改动）2 次：输出 sha256 均为 `BF6552559E0FCB4A…`，与作者 `data/q1-numbers.json`、corpus-analyst 引用的 `bf6552559e0fcb4a` **完全一致**。
- 亲自跑 `q1_research_probe.py`（同法）2 次：输出 sha256 均为 `DEEF2F348BA89CA5…`；与其 `data/q1-research.json` 逐字段一致，唯一差异是 `/snapshot/manifest`（我改路径常量导致相对路径变成 `frozen/MANIFEST.json`）。
- 我自己的独立脚本跑 2 次：`6B9E526CA33705FA…` 一致。
- **条件/瑕疵**：该脚本每次运行读活动库 37 个文件做漂移检查并把结果写进产物；若活动库在两次运行间被编辑，产物会变（当前 0 漂移）。作为决策材料应只声明「对 frozen 快照可复跑」。另：研究员在我复核期间曾出现「data 已生成、脚本又改」的短暂不同步（14:46 的旧 data 里 links=0，14:49 后修正）；最终版本已同步，但**证据身份必须用 sha256 绑定**（本报告已绑）。

### ② 口径一致 —— **不通过**

1. **材料内部标签错位（D2 / §3.1）**：脚本里 `size_hint` 实际 = 解析后 start → **解析后 end**（raw resolved，522）；`size_resolved` = `min(resolved_end, boundary)`（clamped，484）；真正用到 `end.line_hint` 的算法得到 **536**（start 用解析后行；纯 line_hint→line_hint 的旧 526 未在本快照复算）。材料把 522 叫「hint」、484 叫「resolved」，按材料文字复算不复现。教材 1,714 同理是 clamped，不是「解析后 end」。
2. **跨材料同题冲突（同一快照、同一人群、同一「现行 end 锚点」标签）**：
   - `Q1-corpus-analyst.md`：教材现行 p50 **1,931**、>1200 **56.3%**、→heading「+55%」；
   - `Q1-research.md`：教材现行 p50 **1,714**、>1200 **54.9%**、→heading「+74%」。
   两者若同时进决策包，就是本项目踩过的「526 vs 1822」式口径混比（这次差 ~12.7%，非 3.5×，但性质相同）。至少一方必须解释差异来源（kpcore 解析 vs 产品 clamp）。
3. **A2「会变」少算**：材料 336/357=94.1%；产品口径 349/357=97.8%（另有 17 条当前 end 已越界，改语义边界会**变短**，应计入「会变」）。
4. **anchor 99.7%** 与 **range_ok 100%** 都是「clamp/A1 修复后」值；材料在 §3.2 脚注承认「clamp 前 352/357」，但 §7 表与 §0 结论仍用修复后值。两个数必须并置且标明「修复前/后」。
5. **同名碰撞**（材料未直接引用，但 corpus-analyst 会进包）：33 组/106 条（29.7%）可复现；「全部组 68.9%」=单位加权 (106−33)/106，可复现；「top-15 组 78.6%」用对称公式复算为 **73.95%**，corpus 的 json 写 78.57%，公式未定义；旧「77.6%」仍无定义。若进包必须先给公式。

### ③ 用户可感知变化 —— **不通过（有漏项 + 有夸大）**

**已做对的**：
- links 3 / edges 26 / 1 孤儿 target：与我用 PyYAML 独立复算一致（他早期版本曾误报 0，最终版已修）。
- 「本库无 FSRS/进度」正确；并把 5 库聚合标注为「未复算」——诚实。
- 「read_kp 静默返回第 1 行」：我实测确认（`数字通信的特点` → `教材/01:1-1` + 第 1 行内容），是真实的用户可感知缺陷。

**漏项（必须补）**：
- **图谱边会变**：边是由 KP range 几何派生（`edge_derivation.derive_contain_edges` + link instances 落在 range 内）。我按产品函数复算：
  - A1（只修需修复的 end）：**62 → 56 条边（+8 / −14）**；
  - A2（end 全部语义化）：**62 → 53 条边（+21 / −30）**。
  材料 A1 行写「ids / 链接 / 图谱节点不变」——节点确实不变，但**边变了**，这是用户在图谱视图里看得见的。不能只报节点。

**夸大/口径不符（必须改）**：
- **「6 条教材 KP 会被放大到 1.5–1.6 万字」不成立**：我按同一批非标题起点、需修复 KP 复算，尺寸为 16,056 / 15,387 / 9,511（仅 +1.5%）/ 1,427 / 341 / 219 字 ⇒ **只有 2 条**达到 1.5 万字。§4.A1 举的「3 条病态」里第 3 条（9,374→9,511）也不是病态。该数字影响 A1 的风险叙事，必须改。
- **「+20.4% 总字数」**：来源是 clamped 总字数 461,578 → heading 555,798；但 `read_kp` 实际用 **raw resolved end**，实际是 478,321 → 554,660 ≈ **+16.0%**。+74%/1,714→2,985 同理依赖 clamped 起点。
- **「read_kp 单次中位 726 tok」**：用 clamped 1,714×0.4237 得出；read_kp 实际长度是 raw resolved（1,686），按同一系数约 **714 tok**。
- 跨库「22 cards / 9 progress / 276 links」的 B 选项损失：**我无法验证**（语料纪律只允许 `数字通信原理`）。材料 §9 用它支撑「真实损失」，但 §3.3/§10 又标注「未复算」——同一数字在结论里被当事实用、在限制里被标未验证，需二选一。

### ④ 失败回滚是否真可执行 —— **不通过（按字面）**

证据（代码事实，均指到行）：
- txid 批次由 `backup.snapshot_pre_images()` 建立，调用方只有：`services/agent/apply.py:619`（agent 计划写入）、`storage/file_version.py:101`（用户「强制保存」）、`tools/kb.py` 的 review 写路径。**普通 sidecar 写**走 `DocumentService._write_sidecar`（`document.py:285`）→ `save_sidecar` → `atomic_write_yaml`，只在**同目录留一份单代 `.bak`**（`atomic_yaml.py:46`），**不建 txid 批次**。
- `restore_batch`（`backup.py:529`）是**逐文件顺序写回**（`backup.py:626-643`）；中途 OSError 返回 `restore_failed` + 已写清单，**不回滚已写文件** ⇒ 不是「原子回滚」。
- `apply_plan` 事务内失败确实会调 `restore_batch` 兜底（`apply.py:668-692`），但 `allow_unverified=True` 且仍是顺序写。
- 「写锁窗口」在产品里不存在：`file_version.guard_save` 只对 UI 保存入口做 `base_version` 乐观校验；`apply_plan` 只在开头做一次 stale 检查，**不会阻止人在迁移期间继续编辑**。
- 跨库（B 选项 5 库）没有单事务：txid 批次是 per-KB / per-session 的。
- A1/C 的「回滚=删字段/整批撤销」因此**有前提**：迁移必须被实现为 apply_plan 或显式调用 backup API；材料未写这个前提，按字面「迁移脚本 + 现有 backups」执行会**没有 txid 可撤**。C 的回滚还取决于 `slices[]` 最终放 sidecar 还是 `.memoria` 派生层（材料自己写「待裁」）——位置未定，回滚方案不可执行。

### ⑤ anchor_verified 是否按 R1 三判据实现 —— **不通过**

R1 三判据（PHASE4-RULINGS R1 / 设计 §4.1）：
1. `range_ok == False → ANCHOR_UNRESOLVED`；
2. snippet 出现 >1 且**无法消歧** → AMBIGUOUS；消歧手段按 §4.2 A（heading 结构）/ B（出现序号 + 前文 hash）/ C（失败）；
3. end 非唯一 / 超预算 / 解析失败 → 夹到下一同级标题。

对照他的脚本：
- **判据①被绕过**：脚本 `range_ok = start_ok and start<=boundary and end_clamped>=start`，永远是 100%（5 条产品 `resolve_range` 失败被 clamp 掉）。R1 ① 要的正是产品 `ok`（read_kp 依赖它）——当前 352/357。这是「用修复结果替代准入门槛」。
- **判据②是事后重建，不是 anchor 验证**：R1 §3.1 的 anchor 是 `(section_number, ordinal_in_section, identity)`，§4.2-B 要「出现序号 + 前文 hash」。**现网 sidecar 里没有 section_number / ordinal_in_section / context_hash**（我逐字段统计：全部 357 条只有 `id, name, range.start.snippet, range.start.line_hint, range.end.snippet, range.end.line_hint, tags`）。脚本的 section/context 档是从当前正文临时算出来的——它无法发现「hint 漂了、但当前正文恰好自洽」的静默钉错（正是 R1 依据里 18.8% 那类）。他 §7 诚实限定 1 已承认「实现必须新增 section_number/context_hash」，但 headline 仍写 99.7%。
- **判据③口径不一致且不完整**：`end 多义`用的是全文 occurrence（54 条），产品候选端点口径是 37 条；「超预算」完全未实现；对 33.8% 非标题起点教材 KP 直接套「下一同级标题」会误夹（他自己在 A1 里发现了，但 gate 本身没带这条规则）。
- **数值矛盾**：§7 脚注称 `比特率`「section/context 都无法消歧」，但他自己的表 context=100%，我的复算也显示 3 次出现（182/186/233）的前文 hash 互异 ⇒ **context 可消歧**。
- 结论：**99.7% 不是当前 R1 覆盖率**；按产品口径的当前值 ≈ range_ok 98.6%（352），section 档 98.3%（351），context 档 98.6%（352，我的实现）。A1 修复后的投影可以报，但必须标「修复后」。

### ⑥ 孤儿率 20%：方向与分母 —— **不通过（无法判定通过/不通过）**

- **方向**：他算的是「切片→KP」（切片与任何 KP 零重叠）。反方向「KP→切片」在他的 scope 里恒为 0（切片只建在 KP span/section 内，构造性自证）。两种方向的含义完全不同：前者度量**索引覆盖缺口**，后者度量**映射是否断链**（R2 falsifier 的原文「切片找不到归属 KP」更接近前者，但 U2 又写「KP→切片映射孤儿率」，两处文案本身不自洽）。
- **分母 scope 决定生死**（材料 §6 已列，我复算同量级）：全库 26 md ~61–72%；KP 文件整文件 ~32–41%；只建在有 KP 的 section/union 上 0–0.7%。**headline 的 0.0% 取自「切片只建在有 KP 的 section」——这是自证口径**（材料 §6 自己写「门禁退化为自证」）。用它证明「C 通过 R2 的 20% 门禁」是循环论证。
- 因此：**20% 阈值目前不可执行**——同一方案可以「0.0% 通过」也可以「71.8% 触发 falsifier」。这不是研究员算错，是 R2/U2 文案缺 scope 定义；但材料不应在 §0 把 0.0% 当成 C 的通过证据。需要 Lead/人先钉死「分母 = 哪一层切片」，再决定该数字（以及它是映射门禁还是覆盖门禁）。

---

## 3. 我认为**不能进决策包**的项

1. **「C 的映射孤儿率 = 0.0%（通过 20%）」作为 R2 falsifier 通过证据** —— 自证 scope；必需先裁分母（0% / 0.7% / 41.4% / 71.8% 都是同方案）。
2. **「anchor_verified 99.7%（R1 原文口径）/ 100%」作为当前覆盖率** —— 是 clamp/A1 修复后的投影；当前产品口径 352/357=98.6%、section 档 351/357≈98.3%；且 R1 复合 anchor 字段在 sidecar 中不存在。
3. **「A2 336/357=94.1% 会变」** —— 产品口径 349/357=97.8%，含 17 条「变短」。
4. **「教材中位 1,714→2,985（+74%）/ 总字数 +20.4%」** —— 未标「clamped→heading」；read_kp 实际口径 +16.0%；且与 corpus-analyst 的 1,931/+55% 冲突未解。
5. **D2 的 hint/resolved 两档标签（522/484）** —— 实测分别为 resolved-raw/clamped；按材料文字复算不复现（start解析后→end.line_hint=536、raw=522）。
6. **「6 条教材 KP 会被放大到 1.5–1.6 万字」** —— 实测只有 2 条；其余 4 条 219–9,511 字。
7. **A1「整批撤销一个 txid」/ B「3 份快照 + 原子回滚 + 写锁窗口」** —— 前提未写（需 apply_plan/backup API）；普通 sidecar 写只有单代 `.bak`；restore_batch 顺序写非原子；无跨库单事务、无写锁窗口。
8. **A1「ids/链接/图谱节点不变」作为「用户可感知变化」的完整表述** —— 图谱**边**会变（A1 +8/−14；A2 +21/−30）。
9. **跨库 5 库 22 cards / 9 progress / 276 links 的损失量** —— 我无法验证（语料纪律），且材料内部一处当事实、一处标未复算。
10. **同名碰撞 78.6% / 77.6%**（若由 corpus 材料进包）—— 78.6% 用对称公式复算为 73.95%，77.6% 无定义；须先给公式。
11. **`比特率`「section/context 都无法消歧」** —— 与他自己表格及我的复算矛盾（context 可消歧）。
12. **read_kp 726 tok**（用 clamped 长度）—— 与 read_kp 实际口径（raw end）不符（≈714 tok）。
13. 小项：token 系数 0.4237 vs 标定文件 0.4247；`12_q1_boundary_numbers.py` 差异归因（637 vs 639/720 是切分规则，不是「section 分区规则」）。

## 4. 我认为**可以进决策包**的项（通过复核）

1. 快照绑定：26 md / 11 sidecar / 357 KP（71/285/1）；frozen 37/37 sha 一致；live 复核时点 0 漂移；MANIFEST 与 corpus-snapshot 逐文件一致。
2. 产品 range_ok = **352/357=98.6%**、坏 KP 5 条（ids 与 validate_kb 的 4+1 完全一致）；反转 0、span=0 1（`test`）。
3. start 标题行比例 93.3%（教材 66.2%）；start snippet 多义 131/357=36.7%；`end="$$"` 全文行数 532（>500）。
4. heading（语义边界）口径：全部 p50 581 / >1200 24.6%；教材 p50 2,985 / >1200 **69.0%**（复现裁决引用值）。
5. links 3（targets 3，1 孤儿 `通带抽样定理`）/ edges 26（0 孤儿）；本库无 FSRS/进度。
6. 图谱真值 357 nodes / 62 edges（contain 33 / reference 8 / extend 21）。
7. C 在他定义下的切片数/映射：291/301/688 片；per-KP p50 6/3.5/1；预算敏感性 800/1200/2000 → 451/301/201 片（这些数字可复跑，但**绑定他的切分规则**）。
8. B1 639–720、B2 1,166；fanout p50 1 / p90 4–5 / max 19–34；42 个多父单元、483 个无旧 KP 单元（同样绑定他的规则）。
9. 复跑性：两个脚本各 2 次输出 sha256 完全一致，data 与脚本一致（已 pin sha256）。
10. 真实用户可感知缺陷：坏 range 的 KP 当前 `read_kp` **静默返回第 1 行**（我实测）。

## 5. 无法判断（超出我的语料/权限）

1. 5 库聚合（1,590 KP / 276 links / 22 cards / 9 progress）及 B 的跨库迁移损失——只做了单库复核。
2. FSRS「kp_id 变不丢进度」——本库无卡/进度，无法在本库验证（材料亦声明）。
3. 工作量人日（0.5–1 / 1.5–2.5 / 4–6 / 6–8）——估算，无实测；不作为通过/不通过对象，但不应进包当承诺。
4. description 生成 token 估算（0.19M tok / 3.4%）——粗估（材料已标 ⚠️估算）；且系数 0.4237 与标定 0.4247 有小差。
5. 用户研究（UI/用户证据）——未做。

---

## 6. 复跑与证据身份

```powershell
# 我的独立复算（产品真值；frozen 快照；只读）
$env:PYTHONIOENCODING='utf-8'
python artifacts/agent/verify/debate/kg-retrieval/round2/scripts-verify/verify_q1_independent.py
# 2 次运行产物 sha256 一致：6b9e526ca33705fa…（out/q1-independent.json）

# 研究员脚本复跑（复制到 scripts-verify/repro/，仅把路径常量改到 repro 目录，逻辑零改动）
python artifacts/agent/verify/debate/kg-retrieval/round2/scripts-verify/repro/q1_research_probe_final.py
# 2 次一致：deef2f348ba89ca5…；与 data/q1-research.json（4313aab3772df609…）逐字段一致（仅 manifest 路径差异）
python artifacts/agent/verify/debate/kg-retrieval/round2/scripts-verify/repro/12_q1_boundary_numbers_repro.py
# 2 次一致：bf6552559e0fcb4a…；与 data/q1-numbers.json 完全一致
```

| 证据 | sha256 前 16 |
|---|---|
| `round2/Q1-research.md`（复核对象） | `01fda8ce49970139` |
| `round2/scripts/q1_research_probe.py`（复核对象） | `a222a8fcea21a568` |
| `round2/data/q1-research.json`（复核对象） | `4313aab3772df609` |
| `round2/Q1-corpus-analyst.md`（交叉引用） | `ca0cab2197b046a0` |
| `round2/scripts/12_q1_boundary_numbers.py` | `c602edffcb868023` |
| `round2/data/q1-numbers.json` | `bf6552559e0fcb4a` |
| `round2/frozen/MANIFEST.json` | `a4beaedc5f852816` |
| 复核脚本 `round2/scripts-verify/verify_q1_independent.py` | `ec0ff2718e2fddd4` |
| 复核产物 `round2/scripts-verify/out/q1-independent.json` | `6b9e526ca33705fa` |
| 研究员脚本复跑产物 `round2/scripts-verify/repro/q1-research.json` | `deef2f348ba89ca5` |
| 12 脚本复跑产物 `round2/scripts-verify/repro/q1-numbers.json` | `bf6552559e0fcb4a` |

> 若 `Q1-research.md` 在本次复核后再次变更，本报告不自动适用；请按 sha256 判断对象版本。
