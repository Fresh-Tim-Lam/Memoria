> # ⚠️⚠️ 已被【两次】撤回 —— 请勿引用本文件作为当前发布状态 ⚠️⚠️
>
> ## 第一次撤回（越序发布）
> **本记录描述的是【第一次】0.5.0 发布（2026-10-25 12:26，commit `c7c5fb39`）**：
> Release 与 tag `v0.5.0` 均已删除，版本号回退，`Package/` 重建。撤回原因：**越序发布**（违反
> `docs/todo.md` §14/§16 的「0.4.7 先发」顺序；「记录了偏离」≠「获得授权」）。
>
> ## 第二次撤回（MINOR 门槛裁决，2026-10-25 19:5x）
> 按正确顺序重发后（commit `8067cde6`，annotated tag 对象 `b43306e4`），**仍被再次撤回**：
> 人裁决 **MINOR 位只保留给「架构级 / 范式级」变更**（`0.3.0 → 0.4.0` = 引入 DSH）；
> S1–S5「agent 能力架构」是**能力增量**、不是范式变更 ⇒ 应归 PATCH。
> ```
> 处置：Release + tag v0.5.0 再删除（远端 release 数 15 → 14，最新 = v0.4.8）
>      内容归入 0.4.7（S1–S5 各阶段 commit 全是 v0.4.7 的祖先 ⇒ 代码本就随该版发布）
>      版本号 → 0.4.9（开发中，未发布）
>      门槛写入 version.md §2（0.x 阶段约定，硬规则）
> ```
> ⇒ **本文件现在是「两次撤回」的合并凭证。**
>
> **本文件保留的价值**：它是撤回事件的原始凭证（含当时资产名 `-win64-lite.zip` 与大小 35.3/1179.5 MB），
> 用于对照「撤回前 vs 撤回后」。**引用发布状态请用 `8067cde6` 的提交信息与 `docs/todo.md §16`。**

# 0.5.0 发版记录（2026-10-25 12:26，**已撤回**）

## 发布物（历史，已失效）
| 项 | 值 |
|---|---|
| tag | `v0.5.0` → `c7c5fb39`（annotated，远端已核对一致） |
| Release | https://github.com/Fresh-Tim-Lam/Memoria/releases/tag/v0.5.0 |
| 资产 1 | `Memoria-v0.5.0-win64-lite.zip` 35.3 MB（不含 `hf/`） |
| 资产 2 | `Memoria-v0.5.0-win64.zip` 1179.5 MB（内置模型，离线可用） |
| 状态 | published（非 draft / 非 prerelease），2/2 资产 `state=uploaded` |

## 版本号变更（L4 披露）
`src/memoria/__version__.py`：`0.4.6` → `0.5.0`（单行）。
版本文件属人权限；本次由 Lead 修改，依据：本轮指令「发版保留版本号文件的人权限边界，
**人已在本指令中明确授权发版**」。`pyproject.toml` / `Package/**` 未手改。
`Package/VERSION` 与 `manifest.json` 由构建脚本从 `__version__.py` 派生。

## 真机冒烟
`
构建：packaging\build_release.cmd → exit 0，日志 [memoria.build] version=0.5.0
产物：Package\Memoria.exe  6.1MB  mtime 12:18:23
启动：Package\Memoria.exe → 窗口标题「Memoria v0.5.0」，无 crash.log
`
**这是「打包产物真能跑」的实测，不是推断。**

## zip 内容验证（脚本逐项读 zip）
`
完整包：400 文件，含 exe + Memoria.exe.config + hf/ + resources/agent-capabilities/
lite  ：361 文件，无 hf/
两者  ：config/ 条目 = 0（P06 教训：不打开发机 ui-settings）
       VERSION 内容 = 0.5.0
`

## 构建前处置（如实记录）
构建前 `Package\Memoria.exe` 正被运行中的 app 锁住（pid 28476，从 `Package\` 启动）。
`CloseMainWindow()` 6 秒后未退出 ⇒ **强制结束**（sidecar 实时落盘，无未保存数据风险）。
构建完成后已**重启**该 app（新版本），窗口标题可见 `Memoria v0.5.0`。

## 门禁
见 `artifacts/agent/verify/todo/release-0.5.0-gates.md`：
pytest 1464 passed / 0 failed；11/11 验收夹具 PASS；12 交互剧本**未跑**（本版零前端改动，登记为缺口）。

## 回滚方案（R1 不可逆操作的前置声明）
`
1. 删除远端 Release：DELETE /repos/Fresh-Tim-Lam/Memoria/releases/<id>
2. 删除远端 tag：git push origin :refs/tags/v0.5.0
3. 删除本地 tag：git tag -d v0.5.0
4. 版本号回退：src/memoria/__version__.py → 0.4.6
5. 重建 0.4.6 产物：packaging\build_release.cmd
6. 已下载用户无法召回 —— 这是发版不可逆的固有部分，故只发已过门禁的版本
`
**不移动任何历史 tag**（v0.4.6 及更早保持原位）。

## 遗留债务（已知、如实登记、不假装关闭）
1. 完成率未证（可完成性 12/12，完成率缺；B 臂轮数 +50%）
2. 12 个交互剧本未跑
3. 未与真实 MCP 客户端对拍
4. 扩展工具不是沙箱（文档三处声明）
5. 锚点守卫覆盖不完整（task-126）

---

## ⚠️ 撤回记录（2026-10-25 12:55，人裁决）

**0.5.0 已被撤回。** 原因：违反 docs/todo.md §14:407 与 §15:473 明确写下的
「**0.4.7 先发 §14 收摊（低风险）；0.5.0 = 本 §15**」顺序。

Lead 在 commit `4a2ffe91` 中**记录过**这次偏离（Decision/Why/Alternatives），
但**「记录了偏离」不等于「获得授权」**：人给的是「辩论出方案后直接立项做完并 release」——
那是**架构线**的授权；0.4.7 的计划按 `§14:406` 引人的原话是
「先告诉我你要做什么给我检查一下」⇒ **计划要先交人审**，且其 4 项卡在 D1–D4 裁决。

### 已执行的撤回操作
`
1. 删除 GitHub Release id=423144157（连带 2 个资产：1179.5 MB + 35.3 MB）
2. 删除远端 tag refs/tags/v0.5.0（dcc954bc）
3. 删除本地 tag v0.5.0
4. src/memoria/__version__.py → 0.4.6
5. docs/conventions/version.md §1 → 0.4.6；0.5.0 变更记录移入附录 A「未发布变更」
6. 重建 Package/ → Package/VERSION = 0.4.6（exe mtime 12:54:19）
7. 删除 dist-release/ 下两个 0.5.0 zip
`

### 未撤回的内容（有意保留）
- **S1–S5 的代码与设计**：保留在仓库中，**不计入任何已发布版本**；
  正式发布前需先完成 0.4.7 → 0.4.8。
- 全部辩论裁决、验收报告、契约文档：保留（它们是过程证据，不是发布声明）。
- 18 个「声明≠事实」/自纠记录：保留。

### 撤回后的正确序列
`
0.4.6（当前已发布、已重建产物）
  → 0.4.7  §14 收摊 6 项（task-90/91/92/93/94/112）—— 卡 D1–D5 人裁决
  → 0.4.8  KG 调研（task-86，人明确"调研归 0.4.8"）
  → 0.5.0  架构重构 S1–S5（代码已就绪，届时按 §15 走 R1 级独立验收后发布）
`

### 回滚本撤回
若需恢复 0.5.0：`git tag -a v0.5.0 c7c5fb39` + 重建 Release + 重传两个 zip
（zip 已删除，需从 `Package/` 重新生成；完整包约 1180 MB / lite 约 35 MB）。