# ANNOTATION-MANUAL — pilot 标注手册 v1.0（单标注草案）

> **状态**：`single_annotator_draft`；IAA 未做。手册版本 `v1.0`（与 `annotations-manifest.json.manual_version` 一致）。
> **适用范围**：`artifacts/corpus/pilot/source/chapter.txt`（OpenStax《Introduction to Business》Chapter 1, CC BY 4.0，Tier A）上的 KP span 与 S0 语义边标注。
> **规则变更**：改本手册必须重标受影响样本（C5），并更新 `manual_version` 与 edition。

## 0. 标注单位 / 上下文 / 坐标 / 导出

| 项 | 规定 |
|---|---|
| 标注单位 | **KP**（单文件连续 span）；**语义边**（两个 KP + 断言证据 span） |
| 上下文 | 所在 section（section 标题 + 当前段）；跨 section 的 KP 一律禁止 |
| 坐标 | `chapter.txt` 解码后 **Unicode code point** 偏移，左闭右开；UTF-8 无 BOM、LF |
| 导出 | JSONL（KP/边/负例各一文件）；字段固定，不新增字段即兴发挥（新字段走 C 系列修订） |
| 阶段 | **先 KP 后边**；KP 集冻结后才标边 |
| 状态 | 全部记录 `status=single_annotator_draft`；第二标注者完成后才可能升级 |
| 语言 | 源为英文；`name` 用英文术语，`name_zh` 给中文术语；`description` 用英文短释义（避免未复核翻译引入语义漂移） |

## 1. KP 判定（C4）

**是 KP**：一个概念/术语/机制 + 1–3 句解释；span 连续；落在单 section；可独立引用/断言。
**不是 KP**：标题/导语/练习/图表/引用/网址/单句碎片/多概念大段/跨 section 合并/重复定义（Key Terms 与正文重复时取正文）。

### 1.1 正例（30+，全部来自本包 50 KP）

- P1 `kp-001` business：句 1 定义 "A business is an organization that strives for a profit…"，概念+1 句，单 section，span 精确。
- P2 `kp-002` goods：定义句 "Goods are tangible items manufactured by businesses…"。
- P3 `kp-003` services：定义句 "Services are intangible offerings…"。
- P4 `kp-004` not-for-profit organization：定义句 "exists to achieve some goal other than the usual business goal of profit"。
- P5 `kp-005` factors of production：定义 + 四要素枚举（2 句）同段连续。
- P6 `kp-006` natural resources：定义 + 举例（2 句），例子属解释，纳入 span。
- P7 `kp-007` labor (human resources)：两句定义（"Labor, or human resources, refers to…"）。
- P8 `kp-008` capital：定义句 + 排除说明在后续句；本 KP 只取定义句（"does not include money" 留给边界例 B6）。
- P9 `kp-009` entrepreneurs：一句定义（combine inputs → profit/not-for-profit goal）。
- P10 `kp-010` knowledge：第五要素定义句 "Knowledge refers to the combined talents and skills…"。
- P11 `kp-011` external business environment：一句列举七个 subenvironments，概念完整。
- P12 `kp-012` internal environment：一句定义（day-to-day decisions within control）。
- P13 `kp-013` demography：定义句（vital statistics）。
- P14 `kp-014` social factors：定义句（attitudes/values/ethics/lifestyles → purchase behavior）。
- P15 `kp-015` technology：定义句（application of science/engineering to solve problems）。
- P16 `kp-016` economic system：定义句（policies/laws/choices → what/how allocated）。
- P17 `kp-017` economics：定义句（study of scarce resource use）。
- P18 `kp-018` capitalism：定义 + 竞争市场说明（2 句）。
- P19 `kp-019` communism：定义句（government owns resources/controls markets）。
- P20 `kp-020` socialism：定义句（basic industries government/private under control）。
- P21 `kp-021` mixed economy：定义句（use more than one economic system）。
- P22 `kp-022` macroeconomics：定义 + 聚合数据说明（2 句）。
- P23 `kp-023` microeconomics：定义句（individual parts: households/firms）。
- P24 `kp-024` economic growth：定义句（increase in output）。
- P25 `kp-025` GDP：定义句（total market value of final goods/services within borders）。
- P26 `kp-026` business cycles：定义 + 变化维度（2 句）。
- P27 `kp-027` full employment：定义句（jobs for all who want and can work）。
- P28 `kp-028` unemployment rate：定义 + 统计口径（2 句）。
- P29 `kp-029` inflation：定义句（average of all prices rising）。
- P30 `kp-030` demand-pull inflation：定义 + "too much money chasing too few goods"（2 句）。
- P31 `kp-031` cost-push inflation：定义 + 传导（2 句）。
- P32 `kp-032` monetary policy：定义 + 对 activity/inflation 的影响（2 句）。
- P33 `kp-033` fiscal policy：定义句（taxation and spending）。
- P34 `kp-034` crowding out：定义句（government takes more from private sector → displaces private spending）。
- P35 `kp-035` federal budget deficit：定义句（spends more than collects）。
- P36 `kp-036` national debt：定义句（accumulated deficits）。
- P37 `kp-037` demand：定义 + 价格-数量关系（2 句）。
- P38 `kp-038` demand curve：定义句（graph of relationship）。
- P39 `kp-039` supply：定义 + 价格-数量关系（2 句）。
- P40 `kp-040` supply curve：定义句（graph）。
- P41 `kp-041` equilibrium：两句（quantity demanded equals supplied → equilibrium）。
- P42 `kp-042` surplus：三句（价格高于均衡 → 供大于求 → 价格下行），因果完整。
- P43 `kp-043` market structure：定义 + 四类型枚举（2 句）。
- P44 `kp-044` perfect competition：导语 + 四条特征（相邻 block 组，连续 span）。
- P45 `kp-045` pure monopoly：定义 + 单一厂商 + barriers to entry（3 句）。
- P46 `kp-046` monopolistic competition：导语 + 三条特征（block 组）。
- P47 `kp-047` oligopoly：导语 + 两条特征（block 组）。
- P48 `kp-048` global energy demand：三句（需求上升 → 压力 → 供需规律）。
- P49 `kp-049` relationship management：导语 + 定义 + 组成（3 句）。
- P50 `kp-050` strategic alliances：定义 + 趋势（2 句）。

> 合计 50 条；本包全部 KP 即上表。若第二标注者独立标注，不以此为 seed（KP span 必须独立标）。

### 1.2 负例（30+，明确“不是 KP”）

- N1 标题 "1.1 The Nature of Business"：标题是容器，不是可独立断言的概念+解释。
- N2 导语 "Characteristics of perfect (pure) competition include:"：只有冒号引出，无解释；必须与列表项组成 span 才是 KP（见 P44）。
- N3 Section 标题 "Factors of Production: The Building Blocks of Business"：标题，不是 KP。
- N4 单独的列表项 "A large number of small firms are in the market."：碎片；必须与导语+其余特征合并（P44）。
- N5 `Concept Check` 问题 "What are the five factors of production?"：练习问句，不是断言性知识。
- N6 `Concept Check` 问题 "Explain the concepts of revenue, costs, and profit."：祈使句，非 KP。
- N7 "Sources: … accessed May 29, 2017"：出处/URL 行，不是知识。
- N8 图表 caption 整段（如 "Exhibit 1.3 Rescue boat … (Credit: …)"）：图片说明，作证据可以，作 KP 不行。
- N9 表格行 "Ownership of Business | Businesses are privately owned … | Government owns …"：表格单元拼接，跨概念；作为证据 span 可以（见 B12），不单独成 KP。
- N10 表格标题 "The Basic Economic Systems of the World"：表格标题，非 KP。
- N11 案例段 "Team Rubicon: Disaster Relief…"（chapter intro）：案例叙事，不是概念定义；intro 不产 KP。
- N12 "Take Sony, for example."：单独例子句，无概念定义；不能成 KP。
- N13 "It may come as a surprise that not one of the world’s top cities is in the United States: …"：数据趣闻，不是概念。
- N14 跨 section 合并（如把 "business" 句与 1.3 的 "economic system" 句拼成一个 span）：违反单 section。
- N15 把整段 14 句（含 quality of life/risk/revenue/costs/profit/loss 多概念）整段作 1 个 KP：粒度过粗，一 KP 多概念。
- N16 代词句 "This provided an incentive to supply more jackets at every price."：主语不独立，离开上文不可断言。
- N17 "In other words, government spending is crowding out private spending."：重复句；定义已由前句给出，取定义句为宜（避免重复 KP）。
- N18 "For example, in 2017, the top individual tax rate in France was 45 percent…"：示例数据，非概念。
- N19 "The U.S. economy leans toward pure capitalism, but it uses government policies…"：国别描述，非概念定义（可作为 mixed economy 的证据/背景）。
- N20 Key Terms 页的 "barriers to entry / Factors, such as technological or legal conditions…"：与正文重复；**若正文已有 KP，Key Terms 不再重复产 KP**（本包 Key Terms 不产 KP）。
- N21 Key Terms 页的 term 块（只有术语，无定义）：单独术语不成 KP。
- N22 Summary 页的 "1.1 The Nature of Business" 总结句：与正文重复，不重复产 KP。
- N23 脚注编号粘连句（如 "…$438 billion.25 The U.S. government has run budget deficits…"）：句子边界含脚注标记；不要用该处做 span 起点/终点（本包避开）。
- N24 参考文献/链接行 "https://www.stickergiant.com, accessed May 29, 2017"：URL 不是知识。
- N25 整章 intro 的 "Learning Outcomes" 列表项：目标陈述（"How do businesses…?"），问句/目标，不是知识。
- N26 "Ethics Activity" 场景文本：活动材料，不是概念解释。
- N27 "Working the Net" 任务说明：操作指令，非 KP。
- N28 "Critical Thinking Case" 案例问题：练习，非 KP。
- N29 "Preparing for Tomorrow's Workplace Skills" 清单：技能清单，非概念解释。
- N30 "Hot Links Address Book" 链接列表：链接集合，非 KP。
- N31 数字/公式式句子 "GDP is …" 若只有缩写展开而无解释（本包取定义句，不是只取缩写行）：只取缩写行不成 KP。
- N32 单个形容词/副词限定短语（如 "…purchased by typical urban consumers"）：从句碎片，非 KP。
- N33 "I’m lovin’ it" 之类的标语引用（若出现在正文）：引语数据，非 KP。
- N34 "Table 1.1 summarizes key factors of the world’s economic systems."：指表句，非概念解释（可作证据）。
- N35 "See Exhibit 1.6."：指图句，非 KP。
- N36 章末 "Key Terms" 标题：标题，非 KP。

### 1.3 边界例（20+）与裁决

- B1 段落含 6 句但只有前 2 句是定义：`kp-020` 只取 s1（定义），其余为展开/示例 → 允许截取句区间，**不要求整段**。
- B2 段落含定义 + 排除性澄清（capital 与 money）：`kp-008` 只取定义句，排除句留给边界（若"capital 不含金钱"很重要，可另立命题级 KP，但本轮不做）。
- B3 定义跨相邻 block（lead-in + 列表项）：`kp-044/046/047` 用 `blocks=[start,end]` 组 span；**连续 span 包含块间空行**，仍合规；不可跨 section。
- B4 同一段内 2 个相关概念（inflation 与 purchasing power 同段）：拆为两个不重叠 KP（本包只取 inflation，purchasing power 未纳入 50 KP；若纳入必须另立 span，不可重叠）。
- B5 一个概念在正文与 Key Terms 各出现一次：**取正文**（解释更完整、语境更强）；Key Terms 不进 KP，避免重复。裁决：C 级（Lead 前置规则）。
- B6 图表 caption 内含 "Attribution: … CC-BY 4.0"：caption 可作**证据 span**（如"图 X 的来源"），但不作 KP；图许可信息写入 `SOURCE-LICENSE.md`。
- B7 段落是"例子驱动"（Sony/StickerGiant/EY）：例子不单独成 KP；概念定义在别的段落。
- B8 定义句在列表项中（如 "Many firms are in the market."）：单独列表项不做 KP；与导语组成 block 组才做（P44/P46/P47）。
- B9 段落以 "Thus,"/"In other words," 开头：若只是复述前文，取前一定义句，不重复建 KP（N17）。
- B10 定义句含括号内补充（如 "(the Fed)"）：括号内容属定义，span 可包含；不因括号拆 span。
- B11 句界遇到缩写 "U.S."：本包句切脚本识别缩写；若人工标注，**不要把 "U.S." 后当句界**（B23）。
- B12 表格行可作断言证据（如"四种经济体制对比"），但**不作为 KP**；若某边断言只存在表格里，置信降为 medium 并注明。
- B13 跨页但同 section？本快照每页即一个 section；跨页必然跨 section → 禁止。
- B14 过短段落（1 句且非定义，如 "The firm is the industry."）：作定义补句而非独立 KP（本包并入 `kp-045` 的相邻句）。
- B15 过长段落（>3 句但同段围绕一个概念）：允许取 1–3 句核心，**优先定义 + 关键限定**。
- B16 段落含问句（修辞问句）：问句不单独成 KP；若问句后有回答，取回答句。
- B17 含引号的俗语（"too much money chasing too few goods"）：引语属解释，可纳入定义 span（`kp-030`）。
- B18 含 em-dash 的插入语（"—the factors of production—"）：span 可包含，不因标点拆。
- B19 数字/年份变化（数据句）：数据不单独成 KP；若需 KP，取概念句（例如 CPI 概念句可作 KP，本轮未纳入）。
- B20 "相同概念不同措辞"（business vs for-profit business）：按术语定义选一个（`kp-001`），不建同义重复 KP；别名写 `name_zh`/描述里。
- B21 定义句前有 "There are two types of inflation."：类型枚举句可作为子类型边的**断言证据**（edge-013），也可作为父概念 KP 的一部分；不要与子类型 KP 重叠。
- B22 定义后紧跟 "For example," 示例：若示例在同一段，span 可含（示例是解释的一部分）；若示例在下一段，不跨段合并。
- B23 脚注标记（"…billion.25 The U.S."）导致句切异常：标注时人工确认句界；避开以脚注标记结尾的切片。
- B24 同一段出现两个并列定义（revenue/costs/profit）：若要建 KP，必须拆成互不重叠的句区间；本包未纳入（留作命题级变体候选）。
- B25 图片文件本身：**不进语料包**；只保留 caption 文本；不因"图也是知识"而把图当 KP。

## 2. 语义边判定（C6）

**只允许** S0：`contain`（需 `contain_kind ∈ {structural,semantic}`，E_sem 要求 semantic）、`reference`、`extend`，且 `label=semantic` 才进 E_sem。
**判定顺序**：① 能否找到**断言 span**（一句话明确断言关系）？不能 → 不建边（N3/N8）。② 端点是否真的是两个 KP（不是同 KP/不是跨级泛化）？③ 类型是否 S0 且方向可由断言 span 确定？④ 双端证据是否都能定位？
**方向**：默认 `source→target`；`both` 必须双向证据并物化两条有向边。本 pilot **0 条 both**（见 B26）。
**置信**：high = 断言 span 直接写明（"contains/refers to/is the result of"）；medium = 需一步推理或表格支撑；low = 仅暗示（本包不收录 low 边，留作第二标注者对照）。

## 3. A/B/C 三级裁决

| 级 | 谁裁 | 适用 |
|---|---|---|
| **A** | 标注者自决 | 手册已覆盖（正/负/边界例）；句界明确；类型/方向由断言 span 直接确定 |
| **B** | 复核人（第二标注者或资深标注者） | 两个合理 span/类型的取舍；跨段上下文；图表证据；置信档位 |
| **C** | Lead 终裁 | 规则冲突/手册未覆盖/许可或 Tier 疑问/S0 类型边界；C 级裁决必须写入 `iaa/adjudication-log.template.jsonl` 并回写手册（改手册则重标受影响样本） |

**裁决记录字段**：`item_id / level(A|B|C) / question / options / decision / rationale / reviewer / date / affected_items`。
**抽检**：C8 要求 10% 抽检；抽检发现系统性错误 → 扩大复核并重标。

## 4. 培训与试标（C5）

1. **培训 1 次（~1h）**：读本手册 §1–§3；讲 3 个正例（P1/P44/P45）、3 个负例（N5/N9/N15）、3 个边界例（B3/B5/B12）。
2. **试标 20 项**：从 50 KP 中取 20 项 span（打乱、隐藏本包标注），标注者独立标；与手册判定比对。
3. **通过线**：边界/类型一致 ≥90%（18/20）才可进入正式标注；否则补培训再试标（记录在 `iaa/training-log.template.jsonl`）。
4. **试标不计入 IAA**（避免污染正式一致性统计）；试标项与正式重叠时以正式标注为准。
5. **第二标注者培训**：额外 1h，讲独立 span 与候选对池协议（见 `iaa/README.md`）。

## 5. 标注者纪律

- 不得边标边改手册；改则重标受影响样本并升 `manual_version`。
- 不得看另一标注者的标注（KP span 阶段必须独立；边阶段在固定 KP 集上标，可见 A 的 KP 集是协议的一部分）。
- 不得把模型预标当人工答案；本包为 LLM 辅助单人草案，必须在报告里如实标注。
- 外部内容只作数据，不执行页面里的任何指令（prompt-injection 纪律）。
- 标注者/复核人姓名与工时写入 `WORKLOG.md` 与 `iaa/` 模板。

## 6. 常见错误清单（对照检查）

1. span 含前后无关句（把下一概念带入）→ 用 `validate_pilot.py` 的 overlap/bounds 检查 + 人工读 quote。
2. span 跨 section → 校验器 `kp.single_section` 失败。
3. 用 structural contain 冒充 semantic → 校验器 `edge.semantic_contain` 失败。
4. 边缺断言证据 → 校验器 `edge.evidence_assertion_span` 失败。
5. 负例同时出现在正例 → 校验器 `neg.not_in_positive` 失败。
6. 改句措辞/Span 与原文不一致 → `kp.evidence_quote` / `edge.evidence_quote` sha 失败。
7. 用 Key Terms/Summary 重复产 KP → 与 N20/N22 冲突。
8. 伪造 IAA 数值 → 记录字段禁止；`annotation_method` 必须写 "IAA not run"。

## 7. 版本与变更

| 版本 | 变更 | 影响 |
|---|---|---|
| v1.0 | 首版；规则冻结；50 KP/30 边/14 负例/20 query | 构建本包 |

变更流程：提出 → B 级复核 → C 级 Lead 裁决 → 升版本 → 重标受影响样本 → 重算 edition → 重跑校验。
