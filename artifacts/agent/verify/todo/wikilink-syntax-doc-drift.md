# 文档仍在教 `[[id#type]]`（会改用户正文）— 核实、修复、全仓排查

> **任务**：task-153 ｜ **Owner**：`doc-consistency` ｜ **日期**：2026-10-26
> **结论**：4 份指定文档**逐条核实成立并已修复**；全仓排查**发现 13 处**（比原 4 处多 9 处）；
> ③ 机检**可以扩到 `docs/**`**，已给出含实测读数的方案。
> **改动**：4 个 `docs/**` 文件；未动 `src/**`、`resources/agent-prompts/**`、`docs/example/AAA_Vocab/**`；未 commit。

---

## 0. 先说结论

| 项 | 结果 |
|---|---|
| `[[id#type]]` 是否真的会改用户正文 | ✅ **已独立复现**（见 §1） |
| 4 份指定文档 | ✅ 逐条核实成立，已按文档定位分别修复（§2） |
| 全仓排查 | **13 处**：4 处指定 + 1 处历史设计 + 5 处陈旧分发副本 + 3 处已在警示语境内 |
| ③ 机检能否扩到 `docs/**` | **能**，方案见 §4（含实测：扩了之后修前 7 红 → 修后剩 6 红，且 6 红全部属"应保留/不归我改"两类） |

---

## 1. 代码行为复核（没有照抄转述，自己跑了一遍）

### 1.1 读码

| 事实 | 位置 | 结论 |
|---|---|---|
| 权威来源声明 | `src/memoria/graph/edge_types.py:3-5` | "sidecar `links[].edge_type` / `edges[].type`：唯一权威来源；正文 `[[target]]` **不含** `#类型`" |
| 遗留片段映射 | `edge_types.py:41-48` `WIKILINK_HINT_ALIASES` | `#prerequisite`/`#analogy`/`#ref` → `reference`；`#extend` → `extend`；`#contain` → `contain` |
| 片段识别 | `edge_types.py:74-76` `is_wikilink_edge_type_fragment()` | 已注册类型才剥；`#贝尔曼方程` 这类真锚点**不剥** |
| 剥离实现 | `src/memoria/services/link_md.py:27` `strip_known_wikilink_edge_hints()` | 逐链改写为 `format_wikilink(target)` |
| **回写正文** | `src/memoria/graph/kb_build.py:293-297` | `if hints_stripped: raw = compose_markdown(...); open(full,"w")...` ⇒ **真的写文件** |
| 类型落 sidecar | `kb_build.py:71-88` `_apply_wikilink_edge_hint()` | 仅在**该链已有 `entry`**（即落在某 KP range 内）时写入 |

### 1.2 实测复现（临时库，绝不碰真实库）

构造含 5 种写法的文档后跑 `build_knowledge_base()`：

| 正文原写法 | 构建后 | 判定 |
|---|---|---|
| `[[d#extend]]` | `[[d]]` | **被剥** |
| `[[d#contain]]` | `[[d]]` | **被剥** |
| `[[d#ref]]` | `[[d]]` | **被剥** |
| `[[d#prerequisite]]` | `[[d]]` | **被剥** |
| `[[d#贝尔曼方程]]` | 原样保留 | 非类型片段，不剥 |

**`正文被改写: True`** —— 与 prompt-owner 的结论一致，且是我独立复现的。

### 1.3 一处**未能端到端验证**的环节（如实交代）

任务书说"类型读进 sidecar"。读码确认逻辑存在，但**我没能构造出成功的端到端 sidecar 写入**：`sync_file_sidecar_links()` 需要 KP `range` 带 `snippet` 才能解析出区间（`resolve_knowledge_points()` 要求 `start.snippet` + `end.snippet`），我三次构造都得到 `changed:false`、`links:[]`。

⇒ 因此**我不能断言"类型一定存进 sidecar"**；能确定的只有两件：**① 正文一定被改写**（已复现）；**② 类型只在链接落在 KP range 内时才可能进 sidecar**（读码 + `links_created:0` 的实测旁证）。这也解释了任务书说的"链接在 KP range 外时边直接丢"——那种情况下**正文被改、类型也没了**，是最坏情形。

> 这条不影响本任务的文档修复（无论类型存没存，正文被改都已成立），但**作为证据边界必须写明**。

---

## 2. 4 份指定文档：逐条核实 + 按定位分类修复

### 2.1 核实结果（原文）

| # | 文件:行 | 原文 | 定位 | 处置 |
|---|---|---|---|---|
| ① | `docs/conventions/markdown-form-std.md:17,19` | 表格行「`[[id#type]]` \| 带边类型的链接 \| `[[mdp#prerequisite]]`」「`[[id#type\|text]]` \| **完整形式**」 | **规范** | ✅ 删两行 + 加警示块，改教 sidecar 写法 |
| ② | `docs/prompts/role-a-content-agent.md:98,99` | 表格行「`[[kp-id#type]]` \| 带边类型的引用」「`[[kp-id#type\|显示文本]]` \| **完整形式**」 | **提示词（发给 agent）** | ✅ 删两行 + §3 加警示块 + §4 补"正确落点" |
| ③ | `docs/guides/usage-agent-workflow.md:159` | 表格「`extend` \| 扩展/下游 \| **正文 `[[id#extend]]` 标注**」 | **指南** | ✅ 把"是否手动标注"列改成"落点"列，教 `links[].edge_type` + 加警示 |
| ④ | `docs/design/kb-agent.md:112` | 「正文写 `[[id]]` / `[[id\|显示文本]]` / **`[[id#extend]]`**」 | **历史设计记录** | ✅ **保留原文不改** + 紧随其后加「⚠️ 已废弃（2026-10-26）」时间戳警示 |

**4 份全部核实成立**（Lead 定位准确，无虚报）。

### 2.2 口径一致性（同一事实只有一种说法）

4 份现在统一为同一组事实，用词也统一：
1. **正文只写** `[[id]]` / `[[id|显示文本]]`；
2. **边类型只写 sidecar** `links[].edge_type` / `edges[].type`（唯一权威来源，指向 `edge_types.py:3-5`）；
3. **遗留写法会被剥离并回写正文**（`[[d#extend]]` → `[[d]]`），并给出两个后果：**静默改正文**、**预览期断链**；
4. **可用类型**：`reference` / `extend` / `contain`（`contain` 自动派生、禁止手标）。

规范/指南/提示词三份写**正面写法 + 警示**；历史设计记录写**时间戳警示、原文不动**。

---

## 3. 全仓排查（本任务的真正价值）

### 3.1 方法

`rglob("*.md")` 扫全仓，用 C3 的正则 `\[\[[^\[\]\n]*#([A-Za-z][A-Za-z0-9_-]*)\]\]` 抓 `[[…#xxx]]`，再按 `WIKILINK_HINT_ALIASES` 过滤出**真的是边类型片段**的；排除 `node_modules/.git/artifacts/src/tests/Package`（代码 + 打包产物 + 历史报告）。

> 说明：`]]#` 直搜**零命中** —— 因为这 4 份用的是表格里的 `[[id#type]]`（`#` 后不是 `]`），所以任务书建议的 `]]#` 抓法会漏。改用"`[[` … `#xxx` … `]]`"才对。

### 3.2 完整清单（13 处）

| # | 文件:行 | 文档定位 | 处置 |
|---|---|---|---|
| 1 | `docs/conventions/markdown-form-std.md:17` | 规范 | ✅ 已修 |
| 2 | `docs/conventions/markdown-form-std.md:19` | 规范 | ✅ 已修 |
| 3 | `docs/prompts/role-a-content-agent.md:98` | 提示词 | ✅ 已修 |
| 4 | `docs/prompts/role-a-content-agent.md:99` | 提示词 | ✅ 已修 |
| 5 | `docs/guides/usage-agent-workflow.md:159` | 指南 | ✅ 已修 |
| 6 | `docs/design/kb-agent.md:112` | **历史设计** | ✅ 加时间戳警示（原文保留） |
| 7 | `docs/example/AAA_KnowledgeBase/.memoria/agent/kb-spec.zh-CN.md:68` | **陈旧分发副本** | ⛔ **未改**（见 §3.3） |
| 8 | `docs/example/AAA_Vocab/.memoria/agent/kb-spec.zh-CN.md:68` | 陈旧分发副本 | ⛔ 未改（且**明令禁动**） |
| 9 | `docs/example/rich-content-test/.memoria/agent/kb-spec.zh-CN.md:68` | 陈旧分发副本 | ⛔ 未改 |
| 10 | `docs/example/showcase/.memoria/agent/kb-spec.zh-CN.md:68` | 陈旧分发副本 | ⛔ 未改 |
| 11 | `docs/example/行政法/.memoria/agent/kb-spec.zh-CN.md:68` | 陈旧分发副本 | ⛔ 未改 |
| 12 | `tests/probe-kb/.memoria/agent/kb-spec.zh-CN.md:68` | 陈旧分发副本（测试语料） | ⛔ 未改 |
| 13 | `resources/agent-prompts/kb-spec.zh-CN.md:68` | **源头**（prompt-owner 写域） | ✅ 已由 prompt-owner 修（L82 已写"不要用"） |

> `Package/resources/agent-prompts/kb-spec.zh-CN.md:68` 亦命中，属**打包产物**（`Package/**` 是人的权限，L4），同样未改。

### 3.3 为什么那 6 份副本我不改（关键判断）

**证据链**：
1. **全部 untracked**（`git ls-files --error-unmatch` 全失败）—— 它们不是仓库源文件。
2. **源头已修**：`resources/agent-prompts/kb-spec.zh-CN.md` 头部有 `<!-- spec-version: 1.1.0 -->` + `<!-- reviewed-on: 2026-10-26 -->`，且 L82 已写「**遗留写法** `[[kp-id#extend]]`：**不要用**」。
3. **副本是更旧的分发版本**：副本**没有版本戳**，且 L66-68 仍是「`[[kp-id|显示文本]]` / `[[kp-id#extend]]` 声明 `extend` 边」的**旧整篇结构**（连行号都不对应源头）——不是同一文件的局部差异。

⇒ **它们是陈旧的分发产物，不是文档源**。手改副本有三个问题：① 下次分发/构建会覆盖，改了等于没改；② 属生成物，改它违反"不手改产物"；③ `docs/example/AAA_Vocab/**` 是明令禁动的用户实时库。

**正确处置（要 Lead 决定）**：重新分发，即把 `.memoria/agent/kb-spec.zh-CN.md` 按 v1.1.0 源头刷新到各库/测试语料。这属于**分发/构建流程**（`kb_agent.py` 的 FILE_MAP → 安装器），不是文档编辑。

---

## 4. ③「文档教已废弃语法」能不能机检？—— **能，方案如下**

### 4.1 现状：C3 已经写好了判定逻辑，只差扫描根

读 `scripts/agent/prompt_drift_check.py:711-749`，C3 的判定是：

```python
for rel in prompt_doc_rels(ctx):              # ← 唯一限制在这里
    for lineno, line in enumerate(..., 1):
        for match in WIKILINK_TYPE.finditer(line):
            if hint not in aliases: continue
            if any(word in line for word in LEGACY_QUALIFIERS): continue   # 同行有限定词 ⇒ 豁免
            if not strip_active: continue
            ctx.add(check, FAIL, ...)
```

- `WIKILINK_TYPE`、`LEGACY_QUALIFIERS`、`aliases`（从 `edge_types.py` 动态读）、`strip_active`（从 `kb_build.py` + `link_md.py` 反证代码**真的**在剥）**全部可复用**；
- `prompt_doc_rels(ctx)` 只返回 `resources/agent-prompts/**`（由 `kb_agent.FILE_MAP` 推导）。

⇒ **扩展 = 加一个 C6（`docs_forbidden_syntax`），复用同一套正则/限定词/代码反证，只换扫描根**。改动量估计 30-40 行，不需要改 C3。

### 4.2 方案

```python
# 新增：docs/** 的扫描根（与 C3 共用判定逻辑）
DOCS_SCAN_ROOTS = ("docs",)
# 白名单：历史设计记录（原文必须保留，不能要求它不出现该写法）
DOCS_HISTORY_ALLOW = {
    "docs/design/kb-agent.md",          # 2026-10 上旬历史设计记录，已加时间戳警示
}
# 排除：陈旧分发副本 / 打包产物 / 用户实时库（属分发流程，不属文档源）
DOCS_SCAN_EXCLUDE = ("docs/example/", "Package/")

def check_docs_forbidden_syntax(ctx) -> None:
    check = "docs_forbidden_syntax"
    # 复用 C3 的 aliases / strip_active / WIKILINK_TYPE / LEGACY_QUALIFIERS
    ...
    for path in (ctx.repo / "docs").rglob("*.md"):
        rel = path.relative_to(ctx.repo).as_posix()
        if rel in DOCS_HISTORY_ALLOW or rel.startswith(DOCS_SCAN_EXCLUDE):
            continue
        for lineno, line in ...:   # 与 C3 完全相同的判定
            ctx.add(check, FAIL, f"文档把会被构建剥离的语法当推荐写法教：{token}", f"{rel}:{lineno}")
```

### 4.3 这个方案**已被实测验证**（不是纸上设计）

我把 C3 的判定逻辑原样套到 `docs/**` 跑了一遍：

| 时点 | FAIL 数 | 明细 |
|---|---|---|
| **修前** | **7** | 我改的 4 份里 2 处（跨行警示导致同行无限定词）+ 5 份副本 |
| **修后** | **6** | 1 处历史原文（白名单内）+ 5 份副本（排除） |

⇒ **加了白名单/排除之后，修复后的 `docs/**` 会 0 红**，说明方案可落地且不会产生噪声。

### 4.4 必须写进方案的**两个坑**（实测踩到）

1. **限定词是逐行判定**（`any(w in line)`）⇒ **跨行写的警示会误报**。我第一次写的警示块就是把 `[[d#extend]]` 放在第二行、限定词在第一行 ⇒ 被判 FAIL。**解法**：要么要求警示与 token 同行，要么把限定词判定扩成"当前行 + 前一行"。**我已在 `markdown-form-std.md` 就地改成同行**（更稳）。
2. **`]]#` 抓法会漏**。这批文档写的是表格里的 `[[id#type]]`，`#` 后不是 `]` ⇒ 必须用 `[[…]]` 内含 `#xxx` 的正则（即 C3 现成的 `WIKILINK_TYPE`），不能用 `]]#`。

### 4.5 结论

- **能扩，应当扩**。理由：这批危害是**会改用户正文**，比一般文档过期严重；而且判定逻辑已存在、代码反证已存在（`strip_active` 会在代码不再剥离时转 WARN，天然防腐）。
- **唯一真正需要人判断的是"历史 vs 教学"的边界**，而这不是靠算法猜，而是靠**一张显式白名单**（历史文件逐个人工登记 + 文件内时间戳警示）—— 我已在 `kb-agent.md` 建立了这种写法作为范式。

---

## 5. 门禁

| 项 | 结果 |
|---|---|
| `pytest -q tests` | ✅ **1485 passed**（基线 1485，未降） |
| `i18n_selftest.js` | ✅ PASS（5 项全绿） |
| `team_audit.py` | ⚠️ **FAIL=1**，但**与本任务无关**（见下），连跑 2 次稳定复现 |

**那个 FAIL 的实情**（如实报，不藏）：
```
[FAIL] deliberation_quality: dq6：1 个辩论产物未被 git 跟踪
       ['artifacts/agent/verify/debate/kgviz/PHASE2-UNION.md']
```
- `git check-ignore` 确认：`artifacts/` 被 `.gitignore:15` **整体忽略** ⇒ 该文件**必然**"未被 git 跟踪"；
- 我没碰过 `artifacts/agent/verify/debate/`（`git status` 为空）；
- ⇒ 这是**检查器与仓库约定（artifacts 被 gitignore）的结构性冲突**，属既有问题，需 Lead/该检查的 owner 处置（要么改检查器排除 gitignore 路径，要么把该产物移到受版本控制的目录）。**不在本任务写域**。

---

## 6. 未做 / 待 Lead 决定

1. **6 份陈旧分发副本**（`docs/example/*/.memoria/agent/kb-spec.zh-CN.md` + `tests/probe-kb/`，以及 `Package/resources/`）**未改** —— 它们是分发产物、其中一份还是明令禁动的用户实时库。**建议按 v1.1.0 源头重新分发**（属分发流程，非文档编辑）。
2. **③ 的 C6 检查我没有实现** —— `scripts/agent/**` 不在本任务写域（且 `prompt_drift_check.py` 是 prompt-owner 的文件）。**方案已在 §4 给全（含实测读数）**，建议派给 prompt-owner 落地，我可在其落地后负责 `docs/**` 的白名单维护。
3. **`docs/conventions/docs-management.md §4.2` 登记表**未更新（registrar 文件，不在写域）—— 建议补一行指向本报告。
