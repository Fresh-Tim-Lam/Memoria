# Tag 与 Release 机制清单（GitHub 发版 SOP）

> **用途**：每次打 tag / 建 GitHub Release 的**可勾选清单**——标题、双语正文、造价段、资产命名、
> 三步机检、发布后复核。规则本体在 [docs/conventions/version.md §6](../../docs/conventions/version.md) 与
> [docs/conventions/release-copy.md](../../docs/conventions/release-copy.md)；**本文是面向执行者的操作清单，不新增规则**；
> 冲突时以 `version.md` + `release_preflight.py` 机器检查为准。
> **状态**：生效中（2026-10-26，task-182）。**执行者**：release-manager / 发布 Owner。
> **关联**：[claims.md](./claims.md)（Release 正文里的能力断言同样受约束）、
> [repo-metadata.md](./repo-metadata.md)、`scripts/agent/release_preflight.py`（机器门禁）。

---

## 0. 一句话

> **tag 只写 `vX.Y.Z`；Release 标题恰好 `Memoria vX.Y.Z`；正文英文在前、中文在后、两段都完整；
> 必带中英双份造价段；资产名 canonical；三步机检一步不能省；建完必须核对线上实际状态。**

---

## 1. 发版前 0a/0b/0c 三步机检（缺一不可，exit 1 不得继续）

```powershell
# 0a) tag push 之前：远端 tag 必须【不存在】（防覆盖已发布版本）
python scripts/agent/release_preflight.py --tag vX.Y.Z --phase pre `
    --title "Memoria vX.Y.Z" --body-file artifacts/release-body-vX.Y.Z.md

# 0b) tag push 之后、创建 Release 之前：标题严格相等 + 双语顺序 + 造价段 + 版本三查
python scripts/agent/release_preflight.py --tag vX.Y.Z --phase post `
    --title "Memoria vX.Y.Z" --body-file artifacts/release-body-vX.Y.Z.md

# 0c) 创建 Release 并上传资产之后：用 GitHub 上【实际】name/body/assets 复核
python scripts/agent/release_preflight.py --tag vX.Y.Z --verify-published
```

- `exit 1` = **不得继续**（看 FAIL 项逐条修）。
- `SKIP`（离线/网络不可达）**不算通过**：必须在发版报告里写明并人工确认。
- 0c 防「本地 body 改好了、GitHub 上还是旧的」的假绿（v0.4.7 / v0.4.8 / 0.5.0 三次真实教训）。
- `SUPERVISOR-REVIEW` 当前是 **WARN**（supervisor 角色未投入运行；翻转条件见 `version.md:178-182`）。

## 2. 版本号与 tag

| 项 | 规则 | 证据 |
|---|---|---|
| 版本唯一事实源 | `src/memoria/__version__.py`（当前 **0.4.9**） | `version.md §3` |
| 递增规则 | 0.x 阶段按人裁决（`version.md §2`）；MINOR/MAJOR 门禁以文档为准 | `version.md:26-44` |
| tag 名 | **`vX.Y.Z`**（与 `__version__.py` 一致；不带前缀 v 以外的内容） | `version.md:186-195` |
| 版本三查 | `__version__.py` / `version.md §1` / `Package/VERSION` 三处一致（+ tag） | `version.md:289-300` |
| 版本说明行 | `version.md §1` 的「说明」行必须写 `最近已发布 = 新版本号`（0c 会严格比对） | `version.md:187-190` |

## 3. 资产命名（canonical，历史漂移过，必须对照本表）

| 资产 | canonical 名 | 说明 |
|---|---|---|
| 完整包 | `Memoria-vX.Y.Z-win64.zip` | Windows x64 |
| 轻量包 | `Memoria-vX.Y.Z-win64-lite.zip` | **必须带 `win64-` 段** |

**历史教训**：v0.4.7 / v0.4.8 两版用了 `Memoria-vX.Y.Z-lite.zip`（缺 `win64-` 段）；
**已发布资产不改名**（外部链接可能已存），**新发布一律用 canonical 名**。
机检 `ASSETS-COUNT` 对 `-lite.zip` 只 WARN、对"数量≠2 / 两包不同版本"是 FAIL。
（依据：`version.md:197-201`；`operations.md §5.1`）

## 4. Release 标题（严格相等，不是包含）

```
✅ Memoria v0.4.9
❌ Memoria v0.4.9 —— 数据完整性 + 滚动定位
❌ Memoria v0.4.9 (数据完整性)
```

- 判定式：`title == "Memoria " + tag`（字符串严格相等）。机检 `TITLE-EXACT`。
- 亮点写在**正文**，不写标题（依据：`version.md:235-246`；`release-copy.md:23-42`）。

## 5. 正文结构（顺序不可反、两段都要完整）

```markdown
# Memoria vX.Y.Z

## English

### Theme
<one paragraph: what changed and why it matters>

### Highlights
- **<feature>** — <what it does; measured evidence if available (claims.md 编号可写进内部记录，不必对外)>

### Known debts
- <registered limitation, explicitly not closed>

## Cost (Agent compute)

- **Magnitude**: roughly **CNY XXX–XXX** (estimate; not itemised).
- **Accounting basis**: <which versions are merged, or why it cannot be split>.
- **Cost structure (one line)**: <where the spend went>.

---

## 中文

### 主题
<一段话：改了什么、为什么重要>

### 版本亮点
- **<功能>** —— <做什么；有实测数字就写口径>

### 已知债务
- <已登记、不假装关闭的限制>

## 造价（Agent 算力）

- **量级**：约 **XXX–XXX 元人民币**（估算，非逐项计量）。
- **统计口径**：<合并统计了哪几版；为什么不能诚实切分；是估算还是计量值>。
- **成本结构（一句话）**：<钱主要花在哪>。
```

**硬要求（机检口径）**

| 项 | 要求 |
|---|---|
| `## English` / `## 中文` | 两个二级标题都存在，且 English 行号更小；两段剔除标题/分隔线/**造价段**后的主内容均 **>200 字符**（≤200 判 stub） |
| 代码/文件名/`file:line`/commit sha/命令 | 两种语言**保持原样**，不翻译 |
| 造价段标题 | 英文 **`## Cost (Agent compute)`**（半角括号）；中文 **`## 造价（Agent 算力）`**（全角括号，精确匹配） |
| 造价内容 | 量级 + 统计口径 + 成本结构一句话；**造价与收益成对出现**，禁止只写"优化了多少" |
| 能力断言 | 必须只写 `claims.md` 中 implemented / bounded（带条件）/ design-intent（带标注）的表述；**禁止词条见 claims.md §9** |

完整模板与真实反例见 `release-copy.md:74-122`、`:184-206`；固定术语译法见 `release-copy.md:209-254`（新增概念**先补术语表再发版**）。

## 6. 发布包内容与完整性（如实边界）

- 发布包若带 `release-manifest.json`，安装/更新侧做：逐文件 sha256/bytes 核对、zip 条目集合、重复条目、路径穿越、EOCD 尾随数据检查。
- **不做数字签名**（人已明确放弃签名）⇒ UI 只能写「已校验包结构与完整性（不含数字签名）」；
  **禁止**出现「防篡改 / 安全 / 已签名」这类会制造假安全感的措辞。
- 依据：`src/memoria/services/update.py:1-18`（三条硬纪律 + 完整性边界）、`docs/design/release-format.md`；对应 claims：CLM-52。

## 7. 发布后核对清单（release-manager 逐条打勾）

```
□ tag 已 push 且 `git ls-remote` 可见；远端 tag 与本地 commit 一致
□ Release 标题 == "Memoria vX.Y.Z"（严格相等）
□ 正文英文在前、中文在后；两段均 >200 字符（非 stub）
□ 含 ## Cost (Agent compute) 与 ## 造价（Agent 算力）；量级 + 统计口径 + 成本结构齐全
□ 正文未出现 claims.md §9 禁止词条（抽查「图谱赋能 agent / 掌握程度 / 防篡改 / 已签名 / 最快」）
□ 资产：Memoria-vX.Y.Z-win64.zip + Memoria-vX.Y.Z-win64-lite.zip（各 1 个，同版本）
□ 版本三查一致；version.md §1「说明」行 = 最近已发布版本
□ 0c `--verify-published` 通过（或 SKIP 已人工确认并记录）
□ README 顶部版本 badge / 「当前版本」与本次 tag 一致（若本次有 README 变更）
```

## 8. 与本任务（task-182）的接口

- **README 与 Release 使用同一套断言语义**：改 Release 文案时先看 `claims.md`；新增能力先登记再写。
- Release 正文里的**性能数字**必须带版本与口径（例："measured at v0.3.4; protocol in docs/design/graph-benchmark.md"），
  不允许写"当前版本更快"（无当版实测就不写数字）。
- 若本次 Release 涉及图谱/agent 能力表述，优先引用 `claims.md` CLM-10（design-intent）/ CLM-16（roadmap）的措辞。

## 9. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-10-26 | 初版（task-182）：0a/0b/0c、tag/版本三查、canonical 资产名、标题严格相等、双语+造价结构、完整性边界、发布后核对清单 |
