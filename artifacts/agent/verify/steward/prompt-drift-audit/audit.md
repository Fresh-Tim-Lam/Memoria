# prompt_drift_check.py 守卫强度审计（C1–C5）

> **执行**：steward（纯审计，**未改 `prompt_drift_check.py` / `src/**`**）；**时间**：2026-10-26T09:1x+08:00
> **触发**：Lead 观察——"prompt_drift_check.py 已成门禁，但它的 C1–C5 判据本身是否也有『看起来有守卫其实没有』的形态？"
> **方法**：① 逐检查读实现（`scripts/agent/prompt_drift_check.py`，1517 行）；② **探针实测**（`probe.py`：import 模块 +
> monkeypatch 提示词文本，验证"应当 FAIL 的东西是否真的 FAIL"）；③ 与 `team_audit.check_prompt_drift` 的门禁语义对齐
> （**WARN 不算 fail**：门禁只在 `FAIL>0` 或 `exit≠0/1/输出不可解析` 时红）。
> **结论**：C2–C4 的**主路径**确实会红（探针对照组全 FAIL），但存在 **5 个"静默放行"面**；
> 其中**最严重的是 PD-1**：检查"没能执行"时只报 WARN ⇒ 门禁仍绿（正是「看起来成功其实没做」）。

## 1. 逐检查判定

| 检查 | 它声称守什么 | 主路径是否真会红 | 发现 |
|---|---|---|---|
| C1 distribution_integrity | 分发源齐全/可解析、README↔分发双向、引用落点真实、打包白名单覆盖 | ✅（缺文件/缺 README/孤儿/打包漏登均 FAIL） | **PD-3 隐藏扫描旁路**、**PD-4 嵌套孤儿漏检** |
| C2 symbol_reference | 提示词反引号里的工具/RPC/字段/路径/枚举必须真实存在 | ✅（snake 字段、路径、文件名、§章节、fsrs flag 对照组均 FAIL） | **PD-2 camelCase 点分字段静默无 finding** |
| C3 forbidden_syntax | 不得教"会被 kb_build 剥离"的 wikilink 边类型语法 | ✅（对照组 FAIL） | **PD-5 同行任意限定词→整行豁免**、**PD-1 输入不可读→WARN 跳过** |
| C4 version_stamp | spec-version=SPEC_VERSION、reviewed-on、spec-deps sha12 锁 | ✅（缺戳/不一致/依赖变更均 FAIL；`--resign` 拒绝漏签） | 未发现静默放行（强） |
| C5 staleness | reviewed-on 过旧 / 依赖比 reviewed-on 新 → WARN | 设计即 WARN（合理） | 无（WARN 属警告语义） |

## 2. 五个"静默放行"面（探针证据）

### PD-1（最严重）检查"没执行"时只 WARN ⇒ 门禁仍绿
- 代码：`check_forbidden_syntax` 读不到 `edge_types.py` 时 `WARN "无法从…读取，跳过"` 后 `return`（`prompt_drift_check.py:715-717`）。
- 探针 C（`probe.py`）：把 `ctx._edge_types` 置空 ⇒ 输出 **只有 1 条 WARN、FAIL=0、exit=0**；
  `team_audit.check_prompt_drift` 只在 `summary.FAIL>0` 时红 ⇒ **整道门禁在这条路径上等于没跑，但看起来是绿的**。
- 影响：`edge_types.py` 改名/语法坏/被移动时，C3 全部失效且无人报警；同样形态还有 C1 `packaging` 缺失 WARN、C1 README 源缺失 WARN、
  C2 `kb-spec` 缺失时跳过 §章节校验、C5 无 `reviewed-on` 时跳过（C4 会补 FAIL）。
- **建议**：把"检查未能执行"与"内容有问题"分开：前者必须 **FAIL/exit 2**（或带 `check_status: not_run` 字段），
  门禁把 `not_run` 当红；只有"内容确实没问题"才允许绿。这是 AGENTS **L6**（让失败可见）在检查器自身的应用。

### PD-2 C2 点分字段：camelCase 段静默无 finding（连 INFO 都没有）
- 代码：`. ` 分支 `bad = [seg for seg in segs if SNAKE.match(seg) and seg not in code]`（`:636-641`）——
  不匹配 SNAKE 的段（camelCase/大写/数字开头）既不校验也**不进 `unclassified`**。
- 探针 A：
  - `` `range.fake_snake_field` `` ⇒ **FAIL**（对照组，说明检查在跑）；
  - `` `range.fakeCamelField` `` ⇒ **findings 为 none**（伪造字段完全隐形）。
- 影响：提示词若用 camelCase 字段名（如前端字段/JSON 字段），伪造/改名都不会被 C2 抓到。
- **建议**：非 SNAKE 段也进 `unclassified`（至少 INFO），或对点分路径做"字段白名单/代码字面量"校验。

### PD-3 C1 隐藏分发路径探测：显式跳过最可能的文件
- 代码：`:464` `if "agent-prompts" not in text or "kb_agent" in str(path) or "ui.py" in str(path) or "build.py" in str(path): continue`
  ⇒ 若**目录扫描复制**逻辑恰好写在 `kb_agent.py` / `ui.py` / `packaging/build.py` 里（最可能的位置），这一探测**永远不会报**。
- 影响：多一条"按目录全量复制"的分发路径时，C1 的"分发清单"覆盖口径会失真（发布态可能多/少文件）。
- **建议**：不要用"路径含这些名字"做跳过条件；应改为"只对已知权威实现位置做精确 pattern 检查"并在发现
  `iterdir/glob/rglob + agent-prompts` 时输出 WARN（哪怕它在这些文件里）。

### PD-4 C1 孤儿检测只看顶层文件
- 代码：`:441` `on_disk = {p.name for p in src_dir.iterdir() if p.is_file()}` ⇒ `resources/agent-prompts/**` 子目录里的孤儿文件不报。
- 影响：嵌套资源（子目录）既不分发也不登记时静默存在。
- **建议**：`rglob("*")` + 相对路径；对目录内所有非分发文件报 WARN（保留 `APP_INTERNAL_ASSETS` 白名单）。

### PD-5 C3 同行限定词豁免过宽
- 代码：`:739-740` `if any(word in line for word in LEGACY_QUALIFIERS): continue` —— **同一行任意位置**出现
  "不要/禁止/遗留/剥离…" 就整行豁免。
- 探针 B：
  - `推荐写法：… [[某#contain]] …` ⇒ **FAIL**（对照）；
  - `推荐写法：… [[某#contain]] …，不要写错别字` ⇒ **无 finding**（"不要写错别字"这个无关限定词把推荐式豁免了）。
- **建议**：限定词必须**紧邻** wikilink（如匹配 `(不要|禁止|遗留|…)\s*[^。\n]{0,12}\[\[`），而不是整行 includes。

## 3. 正面结论（避免只报坏消息）
- C2 主路径（snake 字段/仓库路径/KB 路径/文件名/§章节/fsrs flag）对照组**全部按预期 FAIL**；
- C4 版本戳 + 依赖指纹锁 + `--resign` 拒绝漏签/拒绝空 note，是**真正有强制力**的检查（本轮未发现绕过面）；
- `--selftest` 10 个红 fixture 覆盖了主路径（但**未覆盖** PD-2/PD-5 两个绕过形态——已用探针补证）。

## 4. 建议优先级
| id | 严重度 | 建议 | 归属 |
|---|---|---|---|
| PD-1 | **高（门禁可能整体失效而显示绿）** | "未执行"→FAIL/exit 2；门禁把 not_run 当红 | prompt-owner（写域 `prompt_drift_check.py` + `team_audit.py` 接线） |
| PD-2 | 中 | 非 SNAKE 点分段进 unclassified 或字段白名单 | prompt-owner |
| PD-3 | 中 | 去掉路径名跳过条件，改精确 pattern | prompt-owner |
| PD-4 | 低 | `rglob` 检测嵌套孤儿 | prompt-owner |
| PD-5 | 低 | 限定词邻近窗口，不用整行 includes | prompt-owner |

> 以上均为 **proposal/report**（我未改 `prompt_drift_check.py`，不越写域）。已按 B4 生命周期登记进
> `team/steward/findings.jsonl`（SF-20261026-037..041，rule_ref=AGENTS.md §0.5 L6）。

## 5. 复跑
```powershell
python artifacts/agent/verify/steward/prompt-drift-audit/probe.py
python scripts/agent/prompt_drift_check.py --json   # 基线：FAIL=0 / INFO=4
```

## blind_spots
- 未做"真实提示词被改坏后门禁是否红"的端到端注入（需要临时改 `resources/agent-prompts/**`，不在我写域；探针改用 monkeypatch 等价验证）；
- C2 的符号分类正则边界（camelCase/大写）只测了点分字段分支，其他分支仍可能有同类静默面；
- 未审计 `--recheck-deps/--resign` 的写路径安全性（只读过实现，未做并发/恶意输入测试）。
