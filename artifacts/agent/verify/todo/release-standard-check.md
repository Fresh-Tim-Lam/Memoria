# 发版门禁机检落地报告（release-standard-check）

> **任务**：把「标题只允许 `Memoria vX.Y.Z`、正文双语英语在前、必须含造价段」从文档约定变成**命令拒绝**。
> **判定标准**：如果有人再写一个带副标题的 release，`release_preflight.py` 必须 exit 1。
> **作者**：release-manager（2026-10-25）
> **写域**：`scripts/agent/release_preflight.py`（已实现）、`docs/conventions/version.md §6`（接入）、
> `docs/conventions/release-copy.md`（口径基线）、本目录报告与夹具。
> **未 commit**（由 Lead 统一提交）。

---

## 1. 一句话结论

- **检查器已生效**：6 类检查 + supervisor review 提示；任一硬规则不过 **exit 1**；用法错误 exit 2。
- **必红是真的**：`--selftest` **36 项 PASS**；用**真实已发布 body** 做的必红证明 **32/32 PASS**
  （v0.4.7/0.4.8/0.5.0 × 9 种违规形态全部 exit 1，还原后 exit 0）。
- **离线可跑**：联网项显式 `SKIP`（不算通过）；本机 `git ls-remote` 被网络策略阻断，已加 GitHub API 兜底。
- **已接入 §6 三步**：0a tag push 前（pre）/ 0b tag push 后建 Release 前（post）/ 0c 建 Release 后（verify-published）。

---

## 2. 交付物

| 文件 | 作用 |
|---|---|
| `scripts/agent/release_preflight.py` | 机检主程序（① review artifact 语义保留 + ② 三条硬规则/版本三查/tag/资产） |
| `docs/conventions/version.md §6` | 发版流程第 0 步（0a/0b/0c）+ supervisor WARN 级与翻转条件 |
| `docs/conventions/release-copy.md` | 宣传口径基线（标题理由 / 双语骨架 / 造价模板 / 16 条反例 / 固定术语表） |
| `artifacts/agent/verify/todo/release-standard-audit.md` | 三个已发布 release 的独立核验报告 |
| `artifacts/agent/verify/todo/release-standard-must-red.md` | 必红证明方法与结果 |
| `.../release-standard-fixtures/run_must_red.py` | 用真实 body 做必红证明的 runner（可重跑） |
| `.../release-standard-releases/*.json` | GitHub API 抓取的 v0.4.7/0.4.8/0.5.0 实际 Release 数据（含 sha256） |
| `.../release-standard-fixtures/{selftest,must-red,audit-offline,pytest}.log` | 实跑日志 |

---

## 3. CLI（最终形态，已实测 exit code）

```
python scripts/agent/release_preflight.py --tag vX.Y.Z --title "Memoria vX.Y.Z" \
    --body-file <path> [--phase pre|post] [--offline] [--require-review] [--json]

python scripts/agent/release_preflight.py --tag vX.Y.Z --verify-published \
    [--release-json <captured.json>] [--offline]

python scripts/agent/release_preflight.py --selftest        # 36 项红/绿自证
python scripts/agent/release_preflight.py --version X.Y.Z   # legacy：① review artifact 检查（语义不变）
```

| 退出码 | 含义 | 实测 |
|---|---|---|
| 0 | 无 FAIL（可能含 SKIP；**SKIP 不算通过**，输出显式列出） | `--selftest`、三个已修复 release 审计 |
| 1 | 有 FAIL（任一硬规则不过） | 32 个必红 fixture 全部命中 |
| 2 | 用法错误 | 缺 `--body-file` / 读不到 body 文件 / 非法 tag / `--verify-published --offline` 无 JSON |

**参数裁决（Lead 2026-10-25）**：`--tag` 是发布事实、`--version` 是代码事实，二者必须相等；
未传 `--tag` 时用 `v` + `--version` 合成 tag 并在输出标 `TAG-SYNTHESIZED WARN`。
`--phase pre` 要求远端 tag **不存在**（防覆盖），`--phase post`（默认）要求**存在**——两个方向相反，不塞进同一检查。

---

## 4. 检查项与判定口径

| ID | 规则 | 判定（机检） | 级别 |
|---|---|---|---|
| `TITLE-EXACT` | 标题只允许 `Memoria vX.Y.Z` | `title == "Memoria " + tag` **严格字符串相等**（禁 startswith/in/宽松正则）；失败时提示是否副标题/后缀/破折号 | FAIL |
| `BODY-BILINGUAL` | 双语、英语在前、两段完整 | `## English` 与 `## 中文` 都存在且 English 行号更小；两段「语言主内容」（剔除标题/分隔线/空行/**造价段**）各 >200 字符 | FAIL |
| `COST-SECTION` | 必须含造价段 | 中文 `## 造价（Agent 算力）`（全角）+ 英文 `## Cost (Agent compute)`（半角）；中文段含量级关键词（元/人民币/CNY/USD/RMB/花费）+ 统计口径（统计口径/合并统计）；英文段含量级关键词；成本结构关键词缺失仅 WARN | FAIL（结构/量级/口径）/ WARN（成本结构） |
| `ASSETS-COUNT` | 发布资产 = 2 且成对 | `win64.zip` + `win64-lite.zip`（兼容历史 `-lite.zip`，仅 WARN）；数量≠2 或不成对 FAIL；发布前无数据 `SKIP` | FAIL / WARN / SKIP |
| `VERSION-THREE-WAY` | 版本三查 | tag 去 v == `__version__.py` == `Package/VERSION` == `version.md §1`；审计模式改从 `git show <tag>:...` 读已跟踪文件（`Package/VERSION` 未入库，显式说明） | FAIL |
| `TAG-REMOTE` / `TAG-NOT-EXISTS` | 远端 tag | post：`git ls-remote` 可见（不可用时回退 GitHub API refs）；pre：必须不可见；`--offline` ⇒ SKIP | FAIL / SKIP |
| `SUPERVISOR-REVIEW` | 发版前 supervisor 审查 | 复用 ① 语义；release 模式默认 **WARN**，`--require-review` 升级 FAIL；legacy 模式仍 FAIL | WARN / FAIL |
| `DECISION-TRAIL` | 发版决策索引 | 复用 ① 语义，仅提示 | WARN |

**离线语义**：`--offline` 时 `ASSETS-COUNT`、`TAG-REMOTE` 标 `SKIP`；输出结尾写
`PASS-WITH-SKIPS … SKIP 不算通过，需人工确认`，**不会**把 SKIP 计入通过。

---

## 5. 必须红的证据（不是推论）

### 5.1 `--selftest`：36 项 PASS（日志 `release-standard-fixtures/selftest.log`）

```
① 原 4 项（todo-owner，语义未动）：no-artifact / wrong-version / verdict-fail 全红、valid 绿
② 合规基线 7 项：exit 0 + 六类检查全 PASS
② 检查1：真实副标题形态（—— 收摊 / 英文副标题 / 后缀）全红；还原绿
② 检查2：中文在前必红 / 英文 stub 必红 / 缺英文段必红；还原绿
② 检查3：缺中文造价段 / 无量级 / 无统计口径 / 缺英文造价段 全红；还原绿
② 检查5：__version__.py 不符 / Package/VERSION 不符 全红；还原绿
② 检查4：资产数量=1 / 资产名不符 全红；无数据 SKIP 且 summary.ok=True
② 检查6：post 无 tag 红 / post 有 tag 绿 / pre 有 tag 红 / offline SKIP（≠ PASS）
② 汇总：FAIL 时 summary.ok=False 且 failed 精确含 TITLE-EXACT
```

### 5.2 真实历史违规必红：32/32 PASS（见 `release-standard-must-red.md`）

不是编造 fixture：直接取 v0.4.7/0.4.8/0.5.0 **已发布 body**，把标题换回 Lead 记录的**真实旧标题**，
或按历史违规形态改坏，喂给 CLI；每条都必须 exit 1 + 命中预期检查项，还原后 exit 0。
运行方式：`python artifacts/agent/verify/todo/release-standard-fixtures/run_must_red.py`。

---

## 6. 本轮裁决与状态（写进 §6，防止半年后没人知道为什么）

| 事项 | 当前状态 | 目标 / 翻转条件 |
|---|---|---|
| supervisor review | **WARN**（`--require-review` 才 FAIL）；legacy 模式仍 FAIL | 目标硬 FAIL；翻转条件 = supervisor 角色投入运行（`docs/design/team-plugin-roadmap.md` P2）+ 至少 1 份合格 review artifact；翻转后默认 FAIL、`--allow-missing-review` 降级 |
| 资产命名 | canonical `Memoria-vX.Y.Z-win64-lite.zip`；历史三种 `-lite.zip` 只 WARN | 已发布资产**不改名**（外部链接风险）；新发布一律 canonical；文档已补历史漂移说明 |
| EN/ZH 字符口径 | 报告采用「`## English` 行首 → `## 中文` 行首」= 6204/5752/7122 | Lead 原数字 6198/5746/7116 是「剔除末尾 `\n\n---\n\n`」口径；差 6 字符仅口径，不是内容差异 |
| operations.md §5.2 | 原写「中文在前、英文在后」，与 version.md 规则 2 **相反** | 已改为「English 在前」并声明 version.md 为单一事实源（跨域编辑已报 Lead） |

---

## 7. 已知缺口（如实登记，不假装关闭）

1. **英文/中文段内容对等性**：机检只判「主内容 >200 字符」，无法判「英文不是中文摘要」；
   仍需人按 `release-copy.md` 核对（规则 2 的完整要求）。
2. **成本结构**：规范要求一句话成本结构，机检仅 WARN（避免把自由表达误判成违规）；由人复核。
3. **supervisor review** 尚未硬门禁（见上表翻转条件）。
4. **`docs/README.md` 索引登记**：`release-copy.md` 需 registrar 登记进约定文档索引（不在本任务写域）。
5. **`git ls-remote` 本机不可用**：本会话 `github.com:443` 连接被重置；检查器回退 GitHub API refs，
   已在真实 tag 上验证（v0.4.7/0.4.8/0.5.0 远端 tag 对象 sha 与本地一致）。
