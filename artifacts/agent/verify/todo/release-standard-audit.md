# 已发布 Release 独立核验报告（v0.4.7 / v0.4.8 / v0.5.0）

> **目的**：不采信 Lead 自报的「三个 release 已修好」，用 GitHub 实际数据 + 本地 git tag 对象独立核验。
> **方法**：GitHub REST API `releases/tags/<tag>` 抓取实际 `name` / `body` / `assets`（公开数据），
> 存为 `release-standard-releases/*.json`；用 `release_preflight.py --verify-published --release-json` 离线重放判定；
> 版本三查改用 `git show <tag>:<path>` 读发布提交内的版本文件；tag 存在性用 `git ls-remote`（不可用时 GitHub API refs 兜底）。
> **作者**：release-manager（2026-10-25）。**未 commit**。

---

## 0. 一句话结论

三个 Release 的**标题严格相等、双语顺序、造价段**均**实际合规**（不是 Lead 自报），版本三查在 tag 提交内一致，
远端 tag 与本 tag 对象 sha 一致；**唯一发现是资产命名历史漂移**（v0.4.7–v0.5.0 用 `-lite.zip`，而 canonical 与
v0.3.x–v0.4.6 是 `-win64-lite.zip`），已按 Lead 裁决：**不改已发布资产，改文档 + 机检 WARN**。

---

## 1. 数据来源与可复现性

| 项 | 值 |
|---|---|
| API | `https://api.github.com/repos/Fresh-Tim-Lam/Memoria/releases/tags/vX.Y.Z` |
| 抓取时间 | 2026-10-25（本会话，Asia/Shanghai） |
| 捕获文件 | `artifacts/agent/verify/todo/release-standard-releases/v0.4.7.json` 等 |
| sha256 | v0.4.7 `a6ced47b94e2…ffbbcb49f5`；v0.4.8 `b5bb3619b1a5…113b5cbfc`；v0.5.0 `49bbdf8bed53…5e9debacf6ff` |
| 重放命令 | `python scripts/agent/release_preflight.py --tag vX.Y.Z --verify-published --offline --release-json <file>` |
| 日志 | `release-standard-fixtures/audit-offline.log` |

> 注意：这些 JSON 是**外部数据**，只作为证据快照；判定逻辑仍由本地检查器执行，可在断网时重放。

---

## 2. 三条硬规则核验（实际 GitHub 状态）

| tag | 实际标题 `name` | 标题严格相等 | `## English` 行 | `## 中文` 行 | EN 在前 | 常见造价段标题 | 中文造价段量级/口径 | 英文造价段量级 | 判定 |
|---|---|---|---|---|---|---|---|---|---|
| v0.4.7 | `Memoria v0.4.7` | ✅ | 1 | 92 | ✅ | ✅ 全角/半角各一 | ✅ 元人民币 / 统计口径 | ✅ CNY | PASS |
| v0.4.8 | `Memoria v0.4.8` | ✅ | 1 | 89 | ✅ | ✅ | ✅ | ✅ | PASS |
| v0.5.0 | `Memoria v0.5.0` | ✅ | 1 | 108 | ✅ | ✅ | ✅ | ✅ | PASS |

- **检查器报告的「主内容」长度**（剔除标题/分隔线/空行/造价段）：
  EN = 4962 / 4620 / 5890 字符；ZH = 4443 / 4370 / 3970 字符（均远大于 200，无 stub）。
- 三份 body 的完整审计输出见 `release-standard-fixtures/audit-offline.log`，
  结论均为 `PASS-WITH-SKIPS`（`TAG-REMOTE` 在 `--offline` 下 SKIP，不计为通过；见 §5）。

---

## 3. 字符数口径复核（Lead 自报 6198/5746/7116 与 5006/5066/4553）

| 版本 | EN：`## English` 行首 → `## 中文` 行首（**含**末尾 `---` 分隔） | EN：剔除末尾 `\n\n---\n\n`（= Lead 口径） | ZH：`## 中文` 行首 → 文末 | 检查器「有效块」口径（去标题/分隔线/空行，含造价段） EN / ZH |
|---|---|---|---|---|
| v0.4.7 | **6204** | 6198 | **5006** | 5681 / 4685 |
| v0.4.8 | **5752** | 5746 | **5066** | 5339 / 4612 |
| v0.5.0 | **7122** | 7116 | **4553** | 6609 / 4212 |

- **ZH 数字与 Lead 完全一致**（5006/5066/4553）。
- **EN 差 6 字符** = 是否把末尾 `\n\n---\n\n` 折叠掉：
  `6204-6=6198`、`5752-6=5746`、`7122-6=7116`。**内容零差异，只是边界口径不同**。
- 本报告与检查器采用**更可复现的口径**：行首→行首，原始字符数（不折叠分隔线）；
  「有效块」数字另列，用于 stub 判定与可读性，两者不混用。
- 结论：Lead 的字符数**可复现**，但必须注明口径；否则下一个人会以为差 6 字符是内容被改过。

---

## 4. 版本三查（tag 提交内）与 tag 指向

| tag | 本地 tag 对象 sha | 远端 `git/refs/tags` sha | 一致 | tag 提交内 `__version__.py` | tag 提交内 `version.md §1` | `Package/VERSION` |
|---|---|---|---|---|---|---|
| v0.4.7 | `cf54495df311…c0950` | `cf54495df311…c0950` | ✅ | `0.4.7` | `0.4.7` | 未入库（构建产物） |
| v0.4.8 | `dad24cd94e47…5283` | `dad24cd94e47…5283` | ✅ | `0.4.8` | `0.4.8` | 未入库 |
| v0.5.0 | `b43306e46598…8c51` | `b43306e46598…8c51` | ✅ | `0.5.0` | `0.5.0` | 未入库 |

- tag 提交：v0.4.7 `d88e4cba`、v0.4.8 `093dac0e`、v0.5.0 `8067cde6`（annotated tag 解引用）。
- `Package/VERSION` 是构建产物、**未跟踪**，审计模式无法从 tag 提交核验；检查器对此**显式说明**，
  没有假装查过（发版模式仍要求工作区 `Package/VERSION` 存在且一致）。
- 本机 `git ls-remote` 因网络策略失败（`github.com:443` 连接重置），改用 GitHub API refs 兜底；
  三版远端 sha 与本地 tag 对象**完全一致**（未发现 tag 被覆盖）。

---

## 5. 资产核验与「文档↔现实漂移」发现

| tag | 实际资产（GitHub） | 数量 | 成对 | 命名 vs canonical |
|---|---|---|---|---|
| v0.4.7 | `Memoria-v0.4.7-win64.zip` + `Memoria-v0.4.7-lite.zip` | 2 | ✅ | ⚠️ lite 缺 `win64-` 平台段 |
| v0.4.8 | `Memoria-v0.4.8-win64.zip` + `Memoria-v0.4.8-lite.zip` | 2 | ✅ | ⚠️ 同上 |
| v0.5.0 | `Memoria-v0.5.0-win64.zip` + `Memoria-v0.5.0-lite.zip` | 2 | ✅ | ⚠️ 同上 |

**独立核验历史（不只是最近三版）**：

```
v0.4.0 : Memoria-v0.4.0-win64-lite.zip | Memoria-v0.4.0-win64.zip   ← canonical
v0.4.5 : Memoria-v0.4.5-win64-lite.zip | Memoria-v0.4.5-win64.zip   ← canonical
v0.4.6 : Memoria-v0.4.6-win64-lite.zip | Memoria-v0.4.6-win64.zip   ← canonical
v0.4.7 : Memoria-v0.4.7-lite.zip      | Memoria-v0.4.7-win64.zip   ← 漂移
v0.4.8 : Memoria-v0.4.8-lite.zip      | Memoria-v0.4.8-win64.zip   ← 漂移
v0.5.0 : Memoria-v0.5.0-lite.zip      | Memoria-v0.5.0-win64.zip   ← 漂移
```

- **根因**：v0.4.7 打包时只照抄「最近自己的命名习惯」，没有回头对照
  `docs/guides/operations.md §5.1`（canonical `-win64-lite.zip`）——比标题违规更隐蔽：
  标题违规是「文档写了没遵守」，命名漂移是「**连文档都没人看**」。
- **裁决（Lead 2026-10-25，前提被本报告数据修正后）**：canonical 保持 `-win64-lite.zip`
  （历史多数 + 平台段语义一致，将来 `-macos-arm64-lite`）；已发布资产**不改名**（外部链接风险）；
  新发布一律 canonical；文档补历史漂移说明；机检两种都接受、`-lite.zip` 只 WARN。
- 已落地：`docs/guides/operations.md §5.1`、`docs/conventions/version.md §6`、
  `docs/conventions/release-copy.md` 反例 #12。

---

## 6. 检查器判定结果（离线重放实际数据）

| tag | 结论 | FAIL | SKIP | WARN |
|---|---|---|---|---|
| v0.4.7 | PASS-WITH-SKIPS | 无 | `TAG-REMOTE`（offline） | `ASSETS-COUNT`（历史漂移命名） |
| v0.4.8 | PASS-WITH-SKIPS | 无 | `TAG-REMOTE`（offline） | `ASSETS-COUNT` |
| v0.5.0 | PASS-WITH-SKIPS | 无 | `TAG-REMOTE`（offline） | `ASSETS-COUNT` |

在线复核 v0.5.0（不带 `--offline`）时 `TAG-REMOTE` = PASS（API 可见 `b43306e4…`），
证明联网兜底路径也真的能判。

---

## 7. 局限（如实登记）

1. 本报告核验的是**当前线上状态**，不是「发布当时的原始状态」；GitHub 只保留最新 body
   （`updated_at` = 2026-10-25T11:25Z），旧违规 body 已不可从 API 取回。
2. 未核验 zip 内容（仅名称/数量/大小），zip 内容验证属发版构建门禁（`release-smoke`），不在本报告范围。
3. `git ls-remote` 在本机不可用，tag 存在性证据来自 GitHub API refs（等价但非同一命令）；
   报告已显式标注，不把 API 结果冒充 `ls-remote`。
4. `Package/VERSION` 未入库 ⇒ 历史审计无法核对发布时的构建产物版本，只能核验已跟踪的两处。
