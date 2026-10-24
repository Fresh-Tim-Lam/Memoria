# 静默默认缺陷的机检提案（T1/T2/T3）

> **任务**：task-127（**只提案，不实现**）。**作者**：steward；**时间**：2026-10-25T01:5x+08:00
> **写域**：本文件（`artifacts/agent/verify/debate/PROPOSAL-silent-default-check.md`）。
> **我未做**：未改 `src/**`、未写任何检查代码、未 commit。
> **一句话结论**：三型都**指不到现行条款**（L10 ⇒ 只能提案）；**T1 可以做"报告型候选扫描"**（WARN+白名单+人工 triage），
> **T2 只做白名单 selector**（否则噪声不可用：全仓 155 个 `if X is None: return ...` 几乎全是合法 null-guard），
> **T3 不建议做静态检查**（改为契约测试矩阵，归 arch-contract）。若不愿立条款：**只写 lessons L9.8，不建检查**。

---

## 0. 先给判断（TL;DR）

| 型 | 该不该做机检 | 形态 | 优先级 | 前置条件 |
|---|---|---|---|---|
| **T1 存在但从不被读** | **该做，但只能做"候选清单报告"** | 一次性 + 定期 `WARN` 报告（非阻断），人工 triage + allowlist | **P1**（已咬人一次：gate） | 新条款（L11-1：声明字段必须有消费点或显式标 inert） |
| **T2 选择器 None 走默认** | **只做白名单内的 selector** | `WARN`（两周后 FAIL），白名单由 arch-contract 维护 | **P2** | 新条款（L11-2：返回对象的选择器不得静默默认） |
| **T3 修饰符被忽略** | **不建议静态机检** | 改为**契约测试矩阵**（selector 组合 → 结果身份断言），arch-contract 负责 | **P3** | 不阻塞；可作为未来"测试存在性"检查 |
| 兜底（不立条款时） | **只写 lessons L9.8** | 文档 + 两案例 + 判定口径 | 立即 | 无 |

---

## 1. 三型定义 / 可机检特征 / 误报风险 / 反例

### T1｜存在但从不被读（write-only declaration）
- **定义**：字段被**解析、校验、存储**，但没有任何**消费点**读取它（或消费点读了另一个字段，导致该字段语义未实现）。
- **本轮证据（已逐行核对）**：
  - `src/memoria/services/agent/plugins.py:65` `GATE_VALUES`（声明）→ `:247` 解析 `gate` → `:248` 校验 → `:258` 存入 `ToolDeclaration.gate`（`:121` 字段）；
  - 全仓 `gate` 在 `src/**` 共 24 处命中，其中 `plugins.py` 之外只有：`observation.py:47/139`（同名无关：`gate_ops`）、`presentation/api/ui.py`（`gate_message`，视觉模型门控，无关）；
    **`op_available()`（`plugins.py:536-541`）只读 `OP_TOOL_IDS` + `self.tool_ids`，不读 `gate`**；`kb.py:486 build_kb_tools()` 243 行内 `gate` 零命中；
  - 同类可疑：`constrain`（`:122` 字段 / `:251-258` 解析存储），`src/**` 仅 `plugins.py` 内 7 处，**也无消费点**（注释声称应用点在 `validate_plan`，但全仓未找到）。
  - 对照组（证明扫描有判别力）：`ToolDeclaration.primitive` 在同仓有消费（`apply.py` 多处读 `call.get("primitive")` 语义链），所以"有读点"与"无读点"可区分。
- **可机检特征**：
  1. 收集 **声明字段**：`@dataclass`/`NamedTuple`/`TypedDict`/显式 schema 字典；
  2. 收集 **读点**：`Attribute` 节点（`tool.gate`）、`getattr(obj, "gate")` 字符串常量、`item["gate"]`（视声明类型）；
  3. **跨模块**：按字段名 + 声明类名在全仓索引读点（Python 无类型信息，用"字段名 + 类型注解/构造点"近似）；
  4. 输出候选：**声明处 file:line + 全仓读点数=0 或仅"解析/校验/存储"点**；
  5. **逃逸检测（必须做，否则假红灾难）**：`dataclasses.asdict/fields`、`vars()`、`__dict__`、`getattr` 动态名、序列化/JSON dump、pytest 反射 → 标 `uncertain`，不计 FAIL。
- **误报风险（估计 25–40%）**：
  - 合法"存在但从不被读"：① **schema 先行、消费后置**（字段先声明，功能在后续版本；本轮 `gate/constrain` 就可能属于此，**但注释声称已实现**，所以仍是缺陷候选而非合法）；② 只写字段（审计/遥测/序列化输出被外部客户端读）；③ 文档生成/DTO 导出；④ 动态读取（`asdict`/`getattr`）。
  - 误报率来源：动态语言无类型；同名不同物（本轮 `gate` 与 `gate_ops` 同名不同义，按字段名匹配会误连）。
- **反例（应判"不是缺陷"）**：
  - `dataclass` 里 `_schema_version: int = 1` 只被 `asdict()` 动态读 ⇒ 扫描器若不识别逃逸会误报；
  - 插件清单的 `gate` 若被**外部插件作者**按 `agent-plugin-design.md` 语义依赖，但本仓未实现 ⇒ 是"对外契约违约"，仍应报，但性质与"内部字段未用"不同（要分两个 disposition）。
- **结论**：可做**候选报告**（不阻断），必须 allowlist + 人工 triage；**不能做成 FAIL**。

### T2｜选择器为 None 走默认
- **定义**：函数把"未指定"（`None`）当作"用默认"，**且调用方无法区分**"我指定了 → 返回 A" 与 "我没指定 → 返回 B"。
- **本轮证据（已核对）**：
  - `src/memoria/services/agent/section_index.py:326-328`：`if heading is None: return sections[0], None` —— 该分支**先于** `near_line/path/level` 的使用（`:330+`），
    所以单独给 `near_line` 时：`kb.py:727-745` 各 selector 独立拼装（无互斥校验）→ `get_section(near_line=215)` 走 `heading=None` 分支 → 返回**首节/整篇**，零错误信号。
- **可机检特征**：
  - AST：`if <param> is None:` 后**直接 return 默认对象**（而非抛错/返回错误）；
  - 且该 `<param>` 属于**返回对象身份选择器**（`heading/line/near_line/path/id/name/index/offset/limit/page/section` 词表）；
  - 且函数**没有** `default_used`/`selection` 字段或 `allow_default=True` 参数让调用方感知；
  - 且调用方有传 `None` 或省略的路径（可选：数据流）。
- **误报风险（**极高**）**：全仓实测 `if X is None:` 共 **257 处**，其中 `if X is None: return ...` **155 处**（`src/**/135` 个 py 文件），
  绝大多数是合法 null-guard（`hwnd is None: return False`、`raw is None: return None`、`s is None: return 0`）。
  ⇒ **全量 T2 检查 = 155 条噪声，必被人关掉**（这正是"检查写了但没人看"的死法）。
- **反例（合法默认，不应报）**：`dict.get(k, default)`；分页 `page=1`；`max_tokens=None` 取服务端默认；`sorted(key=None)`；`timeout=None` 取默认；可选配置项。
- **结论**：**只做白名单 selector**（见 §4.1），且首两周 WARN；不做全量。

### T3｜修饰符被忽略
- **定义**：某个"修饰/消歧参数"在特定组合下**无效果**，且不报错（调用方以为生效）。
- **本轮证据**：`kb.py:733-742` 五个 selector 各自独立组装；`section_index.py:330+` 中 `near_line` 只在"heading 命中多个候选"时才用于消歧（`:345`），
  而 `path`/`level` 也只在特定分支生效 ⇒ 单独给出这些参数时**静默无效**。`src/**` 135 个 py 文件中 **0 个测试引用 `near_line`/`get_section` 选择器组合**（`tests/*.py` grep 为空串）。
- **可机检特征**：需要"参数组合语义"分析（数据流 + 分支覆盖），静态可近似但**无法判定语义正确性**；最实用的是**契约测试矩阵**：
  `{heading, line, near_line, path, level} × {单给, 两两组合} → 断言返回节的身份（首行/末行/标题）`。
- **误报风险**：高。很多"修饰符在特定组合才生效"是**合法设计**（`near_line` 本义就是"在候选歧义时消歧"）；
  真正的问题是**组合语义未定义 + 调用方无法判断是否生效**，不是"忽略"本身。
- **反例**：`near_line` 单独给时若文档只有 1 个 h1 ⇒ 返回首节恰好正确，无法区分"生效"与"忽略"——这正是 T2/T3 的交叉点。
- **结论**：**不做静态机检**；改契约测试（arch-contract），机检最多做"测试矩阵是否存在/覆盖组合"（P3，未来）。

---

## 2. 逐条尝试指到现行条款（指不到就明说）

> 规则：找不到直接条款 ⇒ 只能提案（AGENTS.md §0.5 **L10**）。下面每条都写"近邻但为什么不算"。

| 候选条款 | 原文/位置 | 能指到吗 | 判定与理由 |
|---|---|---|---|
| **AGENTS.md L6** | 「任何"看起来成功其实没做"的路径，修法是【让失败可见】」 | **近邻但不算** | L6 的方向是"**失败被隐藏** ⇒ 让失败可见"；本问题是"**成功被冒充**"（默认值返回了一个看起来对的结果）。L6 的修法（加断言/让失败可见）**不覆盖"错误结果没有错误信号"**。若强行引用＝把条款读宽（L10 禁止）。 |
| **AGENTS.md L10** | 无条款的发现只能作为建议新增 | **间接支持** | 它规定的是**本次处置形式**（只能提案），不是缺陷规范本身。 |
| **PROTOCOL E4** | 可复现才有效（`ev:bench:<id>`） | **仅在证据层兜底** | 案例二的后果是"A/B 测错两轮"——E4 会在**引用该测量当证据时**要求复现，可能抓住污染；但它不约束 API 语义，**不能预防**。 |
| **PROTOCOL E3** | 共享假设单列 + 指派检验者 | **指不到** | E3 管"辩论结论依赖的未验证前提"，不管"代码 API 默认行为"。 |
| **PROTOCOL "C3"（你任务描述里的「不得取首个」）** | —— | **不存在** | 全仓检索：`PROTOCOL.md` 无 `C3` 条款（只有裁决编号 `R-C3`，内容是 CONFLICT-3「不得要求缺席证明」的裁决）；`docs/design/design.md:193` 的 C3 是「知识点 id 冲突处理」，`docs/design/agent-capabilities.md` 的 C3 是上游契约编号——**都与"不得取首个"无关**。即："不得取首个"目前**只存在于你的任务描述里，不是现行条款** ⇒ 无法指到，只能作为建议新增（正是 L11-2 要补的东西）。 |
| **现有 `team_audit::silent_failure`** | S1–S5（dispatch-log 的完成声明必须绑定产物） | **指不到** | 它只校验"派发/完成声明→磁盘产物"的绑定；被检对象是**记录**，不是**代码 API 行为**。 |
| **现有 `deliberation_quality` / `commit_hygiene` 等** | —— | **指不到** | 都是过程/提交层，不触代码语义。 |
| **lessons L9.6/L9.7** | git add 陷阱 / 门禁确定性 | **指不到** | 主题不同。 |

**§2 结论：T1/T2/T3 均无法直接指到现行条款。** 按 L10，**不得直接变成检查**；只能：
（a）建议新增条款（下方 §4 给条款文本）；或（b）只写进 `agent-team-lessons.md`（不建检查）。
**我没有把"L6 的精神"当条款用**——那是把偏好当规范。

---

## 3. 可行性与误报估计（允许结论是"不做"）

| 维度 | T1 字段零消费 | T2 选择器默认 | T3 修饰符忽略 |
|---|---|---|---|
| 静态可检测性 | **中**：字段/读点用 AST + 名字索引可做；跨模块靠"字段名+类名+构造点"近似；动态读取需标 uncertain | **高（结构）但低（语义）**：模式识别容易，**判断"该不该默认"需要白名单** | **低**：需要组合语义/数据流；静态几乎必假阳 |
| 实测噪声量 | 预估 **3–8 个候选/次**（76 个 dataclass，多数字段有消费） | 全量 **155 条**（不可用）；白名单内预估 **≤5 条** | 无法估，做得好的话 0 检查、靠测试 |
| 误报率估计 | **25–40%**（含"schema 先行/后置消费"与动态读） | 白名单内 **10–20%**（选择器词表误纳） | —（不建） |
| 实现成本 | **2–4h**（一次脚本 + allowlist + 报告） | **1–2h**（白名单 + AST 模式 + 两周 WARN） | 契约测试 **1–2d**（arch-contract，非机检） |
| 是否阻断 | **否**（报告型，WARN） | **否**（WARN 起步） | — |
| 优先级 | **P1**（已咬人：gate 被用来主张"不省 schema token"） | **P2**（尚未在真实裁决中造成错误结论，但案例二同源） | **P3** |
| 结论 | **做（报告型）** | **做（白名单）** | **不做机检，改契约测试** |

**跨模块难点（你特别问的 T1）**：静态分析**能**检出"字段从未被 read"这一现象，但**不能可靠区分**：
①真未实现（gate）；②schema 先行/后置消费（合法但需标注）；③动态读取（`asdict/getattr`）；④外部契约字段（插件作者依赖）。
所以 T1 的机器产出只能是**候选清单**：`{声明 file:line, 字段名, 全仓读点列表, 逃逸标记, 建议 disposition}`，
由人/owner 逐条判定；**做成 FAIL 一定会在第一周被误报淹没**。

---

## 4. 建议（含"不建议机检化，只写 lessons"选项）

### 4.1 主推荐：立一条新条款，然后**两步走**（T1→T2；T3 永不做静态）

**条款建议（新增 `AGENTS.md §0.5 L11`，或 `lead-dispatch-rules §5.5`；Lead 决定落点）**：
```
L11 静默默认可接受性：
L11-1（T1）声明字段必须可追消费点：字段被解析/校验/存储后，必须至少有一个消费点读取；
      若暂不消费，必须在声明处标 `silent-ok: <reason> owner=<id> due=<date>`，否则视为遗留缺陷。
L11-2（T2）返回对象身份的选择器参数不得静默走默认：未指定时必须 (a) 明确报错，或
      (b) 返回值带 `default_used=true`/`selection` 显式标记；调用方必须能区分"显式指定"与"未指定"。
L11-3（T3）选择器组合语义必须在契约文档定义，并由契约测试矩阵覆盖（测试归 arch-contract，不是机检）。
```
（L11 只在"条款批准后"才有检查；当前只提案。）

**阶段 1（P1，T1）**：一次性审计脚本/报告（不进 `team_audit` 主检查、不阻断）：
- 产出候选清单；每条必须由 owner 判 `fixed / inert-ok(白名单) / external-contract`；
- 白名单文件：`scripts/agent/silent_default_allowlist.json`，**owner = arch-contract**（契约语义归它），**Lead 批准变更**；
- 条目字段：`{file, symbol, kind: "inert-field"|"selector-default", reason, rule_ref|task, owner, expires}`；**expires 到期自动重新入候选**；
- 退出条件（kill criteria）：候选 >20 条/次 或 triage >30min/周 ⇒ **放弃检查，改 lessons**（防"检查写了没人看"）。

**阶段 2（P2，T2）**：只对**白名单 selector 词表**（首版建议 `heading/line/near_line/section/id/name/index/offset/limit`，
由 arch-contract 结合"返回对象身份"定义增删）扫 `if <selector> is None: return <default>`；
首两周 WARN（宽限期同 §5.4/§6.5 先例），之后 FAIL；**全仓 155 条默认分支不在范围内**（这是本提案最重要的边界）。

**T3**：不写检查。由 arch-contract 建 `tests/` 选择器矩阵（组合 → 结果身份断言），steward 未来最多检查"矩阵文件存在 + 组合数 ≥ N"（P3）。

### 4.2 备选（若你不愿现在立条款）：**只写 lessons L9.8，不建检查**
- 内容：三型定义 + 两个案例（gate 字段 write-only / `heading=None` 静默首节）+ 判定口径（"看起来能用的默认值，让错误看起来像结果"）；
- 成本≈15 分钟；**零误报**；缺点 = 靠人记住（但 L10 正是为此设的：没条款前只能这样）。
- **我推荐先做 4.2（立即）**，等架构辩论收尾、L11 条款批了再做 4.1。

### 4.3 我不建议做的
1. **不做全量 T2 扫描**（155 条噪声 ⇒ 必被关掉 ⇒ 反而让"检查"这个词贬值）；
2. **不做 T1 的 FAIL 门禁**（动态读取/后置消费会假红；且 gate 的性质需人判断"是缺陷还是未接线"）；
3. **不把 L6 读宽成 L11**（"让失败可见"≠"禁止静默成功"，混用会让两条规则都失去边界）；
4. **不在 `src/**` 加运行时断言来"修"**（那是实现选择，属 arch/team 裁决，不是 steward 的写域）。

---

## 5. 误报控制与"检查被关掉"的治理（附）

- 任何新增检查先 **WARN 两周**，并公布**实测噪声量**（本提案已给 T2 全量=155 的证据）；
- 白名单**只能由 arch-contract 增改、Lead 批准**；每次新增必须引用条款或 task id，**不得以"太吵"为由整体关闭**（关闭需 Lead 记决定）；
- 检查输出**必须带"为什么"**（声明处 file:line + 读点列表），否则 triage 成本 > 收益；
- **季度复核**：白名单过期项自动回收；若某检查连续两季零命中真缺陷 ⇒ 提出删除（检查也要被审计，同 `steward_self_audit` 精神）。

---

## 6. 证据与复跑（本提案所有 file:line 均已核对）

```powershell
# T1：gate 全仓出现点（声明/解析/校验/存储；无消费）
Select-String -Path src/**/*.py -Pattern '\bgate\b'          # 24 处，plugins.py 外均为同名无关项
Select-String -Path src/memoria/services/agent/plugins.py -Pattern 'gate|op_available|tool_ids'
Select-String -Path src/memoria/services/agent/tools/kb.py -Pattern 'gate'   # build_kb_tools 零命中
# T2/T3：选择器默认分支
Select-String -Path src/memoria/services/agent/section_index.py -Pattern 'is None|near_line|path|level'
Select-String -Path src/memoria/services/agent/tools/kb.py -Pattern 'heading|near_line|selector'
# 噪声量（T2 全量）
python -c "import pathlib,re;print(sum(1 for p in pathlib.Path('src').rglob('*.py') for l in p.read_text(encoding='utf-8',errors='replace').splitlines() if re.search(r'if \w+ is None:', l)))"  # 257
```

---

## 7. 交付边界声明

- 本文件是**提案**：按 AGENTS.md §0.5 **L10**，它指不到现行条款的部分只能作为建议新增，**不得直接变成检查**；
- 我**没有**写实现、没有改 `src/**`、**没有 commit**（按 task-127 要求）；
- **副作用提醒**：本文件位于 `artifacts/agent/verify/debate/` 下且未提交，`deliberation_quality::dq6`（J6'：辩论产物必须 git tracked）
  会在下一次审计把它报为 FAIL。这是 dq6 的设计行为，**请 Lead 在收口时提交本文件**（我不越权 commit）。
