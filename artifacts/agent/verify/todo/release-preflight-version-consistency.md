# task-167：release_preflight 补卫 —— version.md「说明」行「最近已发布版本」vs 实际 tag

> **来源**：`doc-consistency` 修 `version.md` L12 时发现，`release_preflight.py` 只解析「当前版本」行，
> 「说明」行**不进任何机检** ⇒ 「说明行写旧版本、实际已发新版」这类漂移永远不会被门禁抓到，
> 只能靠人读；而它今天已经真实误导过一次排期（todo-owner 按 L12 误判「上一版」）。
> **作者**：release-manager（2026-10-26）。**未 commit**（Lead 统一提交）。
> **判定标准**：如果「说明行」再写错，`release_preflight --verify-published` 必须 **exit 1**；
> 解析失败也必须 exit 1，不许静默跳过。

---

## 0. 一句话结论

新增检查 **`VERSION-NOTE-PUBLISHED`**（只在 `--verify-published` 跑）：
`version.md §1「说明」行` 的「最近已发布 = X.Y.Z」必须**严格等于**本次 tag 的版本；
**不一致 ⇒ FAIL（给出两侧实际值）/ 无法解析 ⇒ FAIL（不是 WARN/SKIP）**。
三组 fixture 已**实跑**：正常绿、写旧版本红、不可解析红；pytest 1516 不降、team_audit FAIL=0。

---

## 1. 实现

### 1.1 检查项（`scripts/agent/release_preflight.py`）

```python
NOTE_ROW = re.compile(r"^\|\s*说明\s*\|\s*(.*?)\s*\|\s*$", re.M)
NOTE_PUBLISHED = re.compile(
    r"最近已发布\s*[=＝:：]\s*\**\s*v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)")
```

- `_parse_docs_note_version()`：返回 `(version, 行原文, 失败原因)`。
  **只返回「解析到」或「为什么解析不到」**，不返回"跳过/未知" —— 避免上层静默放过。
- `eval_version_note_published(tag, root)`：`VERSION-NOTE-PUBLISHED`，仅 audit 模式接入
  `run_release_checks()`（`mode == "audit"`），即 `--verify-published`。
- 三种结果：
  - 相等 ⇒ `PASS`（detail 写明 `最近已发布 = X == tag vX`）；
  - 不等 ⇒ `FAIL`（detail 同时给出 `文档值`、`tag`、`行原文`，并说明会误导排期/核对）；
  - 行缺失/读不到/措辞改变/无版本号 ⇒ `FAIL`（detail 明确写「无法解析」+ 行原文，**不是 SKIP**）。

### 1.2 读哪份 version.md：**工作区**，不是 tag 提交（关键决定）

用实际数据验证过为什么不能读 tag 提交：

```
$ git show v0.4.9:docs/conventions/version.md | grep 说明
| 说明 | 0.4.9 = 开发中（未发布）；最近已发布 = 0.4.8（0.5.0 已撤回，见 §2） |
```

⇒ v0.4.9 的 **tag 提交里写的是「最近已发布 = 0.4.8」** —— 那正是今天要抓的错误本身。
若读 tag 提交，等于把「发布当时就错的文档」当作正确基准，会放过本次缺陷。
⇒ 改读**工作区** version.md：它才是人（todo-owner）实际读到、会据此排期的那份文档。
（selftest 里有一条专门证明这一点：tag 提交写旧值、只修工作区 ⇒ 变绿。）

### 1.3 接入点理由：为什么是 `--verify-published`，不是 `--phase pre` / `--phase post`

| 阶段 | 能拿到什么 | 为何不适合本条检查 |
|---|---|---|
| `--phase pre`（tag push 前） | 准备发布的 tag 版本 | 「最近已发布」按定义还是**上一版**（本次尚未发布）⇒ 断言必然误红 |
| `--phase post`（tag push 后、建 Release 前） | 真实 tag 存在 | GitHub Release 尚未创建；且发布流程中间态，文档可能尚未随发布收口 |
| `--verify-published`（建 Release 后） | **真实 tag + 真实发布状态 + 发布后的文档** | 三者同时可得，才能判断「文档说最近已发布的是谁」与「实际发的是谁」是否一致 |

补充：只有这个阶段是**发布后审计**语义 —— 断言的是"发布已经发生，文档必须如实记录它"。
pre/post 是"准备发布"语义，此时「最近已发布」本就该指向上一版。

---

## 2. 三组 fixture（**实跑**，不是"应该会红"）

### 2.1 `--selftest`：47 项 PASS（原有 36 + 新增 11）

新增 11 项（全部实际执行 `run_release_checks(mode="audit")`）：

```
[PASS] ② 检查7 正常态（说明行=tag）必绿
[PASS] ② 检查7 发布模式不含该检查
[PASS] ② 检查7 说明行写旧版本必红
[PASS] ② 检查7 必红 detail 同时给出两侧实际值
[PASS] ② 检查7 不一致后还原必绿
[PASS] ② 检查7 说明行不可解析必红
[PASS] ② 检查7 不可解析 detail 明确写「无法解析」
[PASS] ② 检查7 不可解析后还原必绿
[PASS] ② 检查7 缺「说明」行必红
[PASS] ② 检查7 基线（tag 提交旧值）必红
[PASS] ② 检查7 只修工作区即可绿（证明读工作区，不读 tag 提交）
SELFTEST PASS（47 项）
```

### 2.2 独立 pytest：15 passed（`scripts/agent/test_release_preflight.py`）

默认 `testpaths=["tests"]` 不收集 `scripts/agent/**` ⇒ **不影响主门禁基线 1516**；
显式运行：`python -m pytest -q scripts/agent/test_release_preflight.py` → **15 passed**。
覆盖：正常/旧版本/更新版本（严格相等）/不可解析/缺行/缺文件/7 种格式变体/发布模式不含/审计端到端。

### 2.3 CLI 级三组 fixture（真实 v0.4.9 Release 数据 + 临时 repo-root）

命令形如：
```
python scripts/agent/release_preflight.py --tag v0.4.9 --verify-published --offline \
    --release-json <v0.4.9.json> --repo-root <三个临时目录之一>
```

| fixture | 构造 | 实测输出 | exit |
|---|---|---|---|
| 正常态 | 说明行 `最近已发布 = **0.4.9**` | `[PASS] VERSION-NOTE-PUBLISHED: … '0.4.9' == tag 'v0.4.9'`；结论 PASS-WITH-SKIPS（VERSION-THREE-WAY/TAG-REMOTE 因临时 repo 无 tag 而 SKIP） | **0** |
| 写旧版本 | 说明行 `最近已发布 = **0.4.8**` | `[FAIL] VERSION-NOTE-PUBLISHED: … 写 '0.4.8'，但本次 tag = 'v0.4.9' … 行原文：'最近已发布 = **0.4.8**（旧版本）'` | **1** |
| 不可解析 | 说明行 `最近发布：见变更记录` | `[FAIL] VERSION-NOTE-PUBLISHED: 「说明」行里无法解析「最近已发布 = X.Y.Z」… 解析失败按 FAIL 处理` | **1** |

### 2.4 真实仓库 `--verify-published --tag v0.4.9`（线上实际状态）

```
[PASS] TITLE-EXACT / BODY-BILINGUAL / COST-SECTION / ASSETS-COUNT
[PASS] VERSION-THREE-WAY: tag 提交内 __version__.py='0.4.9'、version.md §1='0.4.9'
[PASS] VERSION-NOTE-PUBLISHED: version.md §1「说明」行：最近已发布 = '0.4.9' == tag 'v0.4.9'
[PASS] TAG-REMOTE: ls-remote 可见 v0.4.9 → 0d1c37a2…
结论：PASS（7 项全过）
exit=0
```

---

## 3. 现有发版流程不回归（实测）

| 命令 | 结果 | 说明 |
|---|---|---|
| `--phase post --tag v0.4.9 --title "Memoria v0.4.9" --body-file <线上 body>` | **exit 0** | 8 项检查（ASSETS SKIP、SUPERVISOR WARN）；标题/双语/造价/四查/tag 全 PASS |
| `--phase pre --tag v0.4.9 …` | **exit 1** | 正确报 `TAG-NOT-EXISTS: 发版前远端 tag v0.4.9 已存在 —— 覆盖危险`（预期内：该 tag 已发布） |
| `--verify-published --tag v0.4.9` | **exit 0** | 见 §2.4，含新检查 |
| `--selftest` | **exit 0（47 项）** | 原有 36 项全部保留且 PASS |

---

## 4. 可选加固：**不加机器标记**（给理由）

判断：**version.md §1 表格已足够稳定，不加隐藏机器标记**。理由：

1. **失败是响亮的**：格式漂移 ⇒ 解析失败 ⇒ `FAIL`（detail 直接给行原文），不是静默跳过。
   这已消除「改措辞就回到没人检查」的风险 —— 加标记解决的是"怕解析不到"，而该风险已被 FAIL 覆盖。
2. **标记会引入第二事实源**：隐藏标记（HTML 注释/固定列名）需要人与版本号一起维护；
   一旦忘了同步，会出现「表格写 0.4.9、标记写 0.4.8」的新歧义，比现在更难查。
3. **现有结构稳定且已被 7 种格式变体测试覆盖**：行键 `| 说明 |` + 短语「最近已发布」+
   `= / ： / 全角＝`、`v` 前缀、加粗、无空格均能解析；过度收紧反而让正常编辑也红。
4. 若要加标记需改 `docs/conventions/version.md`（本任务写域外，需 Lead 批准）；
   当前收益/维护成本比不划算 ⇒ 建议暂不加，保留「解析失败 ⇒ FAIL」作为漂移兜底。
   （如果 Lead 坚持要标记，建议用表格固定行 `| 最近已发布 | 0.4.9 |`，但需同步 §6 更新步骤。）

---

## 5. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1516 passed / 0 failed**（基线 1516，未降） |
| `team_audit.py` | **FAIL=0**（WARN=52 / INFO=29，exit 0） |
| `python -m pytest -q scripts/agent/test_release_preflight.py` | **15 passed** |
| `python scripts/agent/release_preflight.py --selftest` | **47 项 PASS** |

---

## 6. 改动清单

```
M scripts/agent/release_preflight.py          +157 行（检查 7 + 解析器 + selftest 11 项 + 头部说明）
?? scripts/agent/test_release_preflight.py    新文件 157 行（pytest 专项，默认不进 testpaths）
?? artifacts/agent/verify/todo/release-preflight-version-consistency.md（本报告，artifacts/ 被 gitignore）
未动：src/memoria/__version__.py、Package/**、docs/example/**、docs/conventions/version.md
```

---

## 7. 遗留 / 建议（如实登记）

1. **流程文档缺口（需 Lead 定）**：`version.md §6 第 2 步` 现在只要求更新「当前版本」与「变更记录」，
   没有写「说明」行。新检查会让漏更新在 0c 变红，但更好的做法是流程里明写。
   ⚠️ 本任务不得动 version.md（写域限制），故**仅建议**：在第 2 步补一句
   「更新 §1『说明』行的『最近已发布 = x.y.z』（`--verify-published` 会机检）」。
2. **历史 tag 复核会红**：检查是严格相等语义，用于「刚发布完的 0c 审计」。
   若拿它去复核旧 tag（如当前工作区写 0.4.9、审计 v0.4.7），会 FAIL —— 这是预期，
   历史复核请勿用本条断言（或另开"允许文档版本新于被审计 tag"的模式，本轮不做）。
3. `artifacts/` 被 `.gitignore` 忽略：本报告与其他 verify 产物默认不进 commit，
   如需入库请 `git add -f`。
