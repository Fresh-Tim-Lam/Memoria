# 导入模块实现计划（0.3.0 · 模块化 + 分阶段验证）

> **用途**：把 0.3.0 导入体系拆成可独立推进、可逐阶段验证的模块计划；每个模块给出输入/输出、阶段拆分与「阶段验证」判定标准，供人机按序执行与验收。
> **事实来源**：[import-spec.md](./import-spec.md)（场景/格式/交互/接口契约，一切以它为准）。
> **制定日期**：2026-09-04。状态列随实现推进更新（`☑` 完成 / `◐` 进行 / `☐` 待做）。

---

## 0. 依赖关系与总览

```
M0 扫描/契约层 ──► M1 执行器 ──► M2 RPC ──► M3 前端 ──► M5 文档/样例 ──► M6 版本/回归
                     ▲            │           │                ▲
   M4 i18n ◄─────────┴────────────┴───────────┴────────────────┘（随各模块平行）
   M7 程序内 Agent 提示词 ◄── 依赖 M2/M3 基建；内容源随 M5 单点收口
```

- M0 先行：为一切提供统一的预览模型与 Agent 反馈契约。
- M1 依赖 M0 的决策模型；M2/M3 面向用户可见能力；M4 全程伴随（每模块新增文案即补键）。
- M7（程序内可复制的 Agent 整理提示词）依赖 M2 的资源 RPC 与 M3 弹窗基建；其提示词正文单一事实源文件由 M5 落位。
- M5/M6 在功能稳定后收口。

**当前状态（写入时刻）**：M0 主体完成（三源扫描/as_json/as_markdown/冲突原语，已冒烟）；M0.2 完成；M1–M7 待做（M0.3 剩余）。

---

## M0 统一扫描与契约层（依赖：import-spec §4/§7/§8）

**输入**：`kind(flat_file|md_dir|kb_bundle) + sources + kb_path`
**输出**：`ImportPreview`（摘要/文件动作/KP/冲突/issues）及其 JSON/Markdown 导出。

### 阶段
| 阶段 | 内容 | 验证 |
|---|---|---|
| M0.1 | `import_plan.py` 扫描层：三源解析、文件动作(new/overwrite/unchanged)、KP 冲突、`as_json/as_markdown` | `python artifacts 冒烟`：三源在空 KB 各出 1+ 计划项；Markdown/JSON 头部正确 —— **已通过** |
| M0.2 | md_dir 同名文件动作改为显式 `rename` + 冲突原语（不再静默 `stem-2` 改名） | 预置同名不同内容 .md → preview 出现 `file_exists` 冲突且 options 含 rename |
| M0.3 | kb_bundle 子目录 sidecar 映射健壮（sidecar 与 md 同级目录镜像；非 stem 全库搜索） | 构造带子目录 md+sidecar 包 → 每个 md 正确关联自身 KP，无误配 |

**验收**：`py_compile` 通过；三源 × 空库/已有库 两轮 preview 幂等一致（同输入同输出）。

---

## M1 统一执行器（import_executor）

**输入**：M0 的 preview + 用户 decisions（每 conflict 选 skip/overwrite/rename；可含「应用到全部」）
**输出**：写盘结果 + 计数 + 图谱构建报告（复用 spec §6/§9 语义，替代/兼容现有 `execute_import`）

### 阶段
| 阶段 | 内容 | 验证 |
|---|---|---|
| M1.1 | 决策归一：统一 resolve(conflict→action)（flat 现有 skip/overwrite/rename 语义保留）；md_dir 落点（纯文件/带 frontmatter 建 sidecar，range 缺失不写 range） | temp KB：md_dir 两个文件（1 有 concepts 1 纯文件）执行后文件数/sidecar 数断言 |
| M1.2 | kb_bundle 合并：写 md、按包 sidecar 建库 sidecar、链接/边随 KP 重命名改写 | 构造包（含 link/edge）合并到已有库；断言 sidecar links/edges 目标与重命名映射一致 |
| M1.3 | 幂等与覆盖安全：指纹 unchanged 跳过；overwrite 仅覆盖目标文件与自身 sidecar；失败逐项入 errors | 同源连续执行两次 → 第二次 0 变更；制造只读目标验证错误收集且部分成功状态为 partial |
| M1.4 | 收尾：`build_knowledge_base` 同步 + 结果模型（复用 ImportResult 扩展：files/kp/renamed/overwritten/skipped/unchanged/errors） | 执行后清单与磁盘实际一致（文件、sidecar、kp index 三方核对） |

**验收**：与旧 `execute_import` 对同一平面输入做对照：计数与磁盘产物一致（结构等价）。

---

## M2 RPC 接入（后端 API）

**输入**：前端/脚本请求；**输出**：统一 JSON（preview/result）。

| 阶段 | 内容 | 验证 |
|---|---|---|
| M2.1 | 新增 `import_scan(kind, sources)` / `import_execute(kind, sources, decisions)`（桥接 M0/M1）；旧 `pre_scan_import/execute_import` 标记 deprecated 但保持可用 | 直接调 api 层函数：flat 全流程 scan→execute 结果与旧路径一致 |
| M2.2 | 源拾取：`select_import_sources(kind)`（.txt 多选 / .md 多选+目录 / bundle 目录选择）；windows 对话框权限与取消处理 | 模拟取消返回空、错误路径返回错误消息 |
| M2.3 | 冲突 decisions 往返：前端选择 → decisions 结构校验 → 透传 M1 | 非法 decisions（未知 action/未知 subject）被拒绝并给出可读错误 |

**验收**：不依赖 UI 的脚本可完成「scan→查看反馈→decisions→execute」闭环。

---

## M3 前端导入对话框（import-flow.js 扩展）

**输入**：工具栏「导入」；**输出**：源选择 → 预览 → 反馈/确认 → 结果。

### 阶段
| 阶段 | 内容 | 验证 |
|---|---|---|
| M3.1 | 源类型切换与预览渲染（文件/KP/冲突三区，复用 .-modal 风格；文案全走 `t()`） | 真机：三类源各弹预览，摘要/文件/KP/冲突计数与后端一致 |
| M3.2 | 冲突交互：逐项 skip/overwrite/rename + 「应用到全部」；确认导入、结果报告 | 构造冲突 KB 真机：改项后执行结果与选择一致；取消则零写入 |
| M3.3 | Agent 反馈：按钮「复制反馈」输出 JSON 文本块 / Markdown 清单（契约同 spec §8，schema_version 冻结 1.0） | 复制的 JSON 可被脚本解析且字段与 preview 一致 |
| M3.4 | 增量引导：执行成功后状态栏提示 + 建议「构建」同步图谱；重导同源提示 0 变更 | 幂等真机：同源二次导入显示「无变更」 |

**验收**：覆盖 spec §9 全流程；真机脚本记录每步截图/文案核对。

---

## M4 i18n（全程伴随）

| 阶段 | 内容 | 验证 |
|---|---|---|
| M4.1 | 新增 `import.*` 键族（源类型/预览区/冲突动作/反馈按钮/结果文案 zh/en 成对，模板参数化） | `node --check` + `i18n_selftest` PASS；语言切换预览即时生效 |
| M4.2 | 随 M1–M3 每新增文案即时补键；收尾 `scan_ui_strings` rows=0 | 扫描器 rows=0 |

---

## M5 文档与样例

| 阶段 | 内容 | 验证 |
|---|---|---|
| M5.1 | to-dolist 附录 A（整理提示词）/B（平面格式）迁移指向 import-spec（本文为事实来源，附录保留兼容性链接） | 链接可跳转、无重复口径 |
| M5.2 | 使用说明：三种源「选择什么文件/目录、会看到什么预览、冲突怎么选」+ 示例包样例库 | 按说明在示例库可完整复现导入流程 |
| M5.3 | 样例库隐私与 .gitignore：仅维护「官方样例知识库」，docs/example 其余本地库自动忽略（用户记录项） | `git status` 只出现应维护的官方样例；样例文件仍可随包（打包构建不受 ignore 影响） |

---

## M6 版本与回归（0.3.0 收口）

| 阶段 | 内容 | 验证 |
|---|---|---|
| M6.1 | 版本 0.3.0：`src/memoria/__version__.py`、pyproject、README 徽标同步 | `_read_version` 一致性检查通过（build.py 会拦截不一致） |
| M6.2 | 全量回归表（真机）：三类源 × {新建库 / 增量 / 冲突(跳过·覆盖·重命名) / 幂等重导}；对照手动实现校验：文件、sidecar、图谱边/节点结构 | 每格 ✓/✗ 记录；缺陷回 M 级修复后复验 |

**M6.2 浏览器真机回归记录（browseragent × `docs/example/import-test/_harness_import.py --fresh`，KB=docs/example/empty3）**

harness 即「测试反馈机制」载体：bottle 真实前端 + UIAPI over `/rpc` + 异步注入 pywebview 桥 + canned pick/mark/console/report 通道（详见 operations.md §3.1；运行记录落 `<KB>/.memoria/harness/`）。

| 用例 | 结果 | 证据（UI 弹窗/状态栏 + RPC + 磁盘） |
|---|---|---|
| md_dir 新建 | ✓ | 预览 新建3/KP1/冲突0（含 sub/plain-sub.md 子目录）；结果 sidecar1·KP1；文件树 3、图谱节点1 |
| md_dir 幂等重导 | ✓ | 修复后（浏览器验证）：预览 无变更3·新增KP0·冲突0；执行 无变更3·KP0·sidecar0，净零变更 |
| flat 新建 | ✓ | 预览 新建2/KP2；结果 sidecar2·KP2；KP imp-kp-alpha/beta 互引边成立 |
| flat 冲突-跳过 | ✓ | mutate 播种 → 冲突4行(2文件+2KP 默认跳过) → 结果 跳过2·KP跳过2·零写入 |
| bundle 新建 | ✓ | 预览 新建2/KP2（k1.md + sub/k2.md）；结果 sidecar2·KP2；文件树 7、图谱节点5 |
| bundle 冲突-覆盖 | ✓ | mutate k1.md → 覆盖决策执行：files_overwritten=1（内容回写原稿）/unchanged=1/sidecar1/kp_overwritten=1（未变 KP 不虚计，见下方 KP 计数记录） |
| flat 冲突-重命名 | ✓ | 逐行 rename + 填新值 → files_renamed=1；磁盘生成 imp-kp-beta-2.md（concepts id 改写、回引保留）、原文件保留 |

结构核对（收尾）：md×8、sidecar×6、图谱节点6/边3(reference)。flat 互引边成立；bundle k1→imp-b-kp2 的链接仅在 sidecar links（锚点无行号），KP 待配置范围前不入边——与设计一致（与 flat 有锚点范围成边对照成立）。

**幂等冲突噪声修复（2026-09-05）**：`import_plan.py` 新增 `_is_idempotent_kp` 判定——目标文件无变更（action==unchanged）且库内该 KP 同处此文件 → 不构成冲突，三解析器（flat/md_dir/bundle）统一应用；`kp_new` 口径改为只计「非 unchanged 文件」所携带的 KP。三源幂等重导复验（RPC）：预览 无变更N·新增 KP 0·冲突 0，执行 0 写入；新建导入预览数值不变（md 新建3/KP1、flat 新建2/KP2、bundle 新建2/KP2 均回归一致）。

**KP 计数归类修复（2026-09-05）**：`import_executor.py` KP 计数按决策归类——新增→`kp_imported`、覆盖→`kp_overwritten`、重命名→`kp_renamed`、跳过→`kp_skipped`；仅在 KP 实际落盘（md 写入或 sidecar 落库）时计数，未变文件不虚计。结果弹窗补 KP 明细行（`import.resultStatsKp`，中英成对）：「KP：新增 N · 覆盖 N · 重命名 N · 跳过 N」。RPC 复验：md/flat/bundle 新建 `kp_imported`=1/2/2、幂等全 0；flat 重命名+跳过 `kp_renamed=1/kp_skipped=1`；bundle 覆盖 `kp_overwritten=1`（sub/k2.md 未变不计数）；UI 结果弹窗两行统计渲染正常（浏览器验证通过）。

遗留观察：已清零（validate_kb error:None 为 harness 摘要假象已修；get_window_chrome 属 harness 无窗口外壳预期，CannedHost 已补 frameless 兜底）。

---

## M7 程序内 Agent 整理提示词（依赖：import-spec §12）

**输入**：单一事实源提示词资源 + 使用说明；**输出**：导入入口内可一键复制的提示词对话框。

| 阶段 | 内容 | 验证 |
|---|---|---|
| M7.1 | 单一事实源文件落位：`resources/agent-prompts/organize.zh-CN.md`（正文取自原整理提示词；英文版同目录）；打包 `resources/` 随包拷贝含该目录 | 文件就位；`build.py` 后 `Package/resources/agent-prompts/` 存在 |
| M7.2 | 资源读取 RPC：`get_agent_prompt(name)`（返回正文+版本+使用说明；缺失返回可读错误） | 直调 api 返回与文件一致 |
| M7.3 | 前端入口：工具栏「导入」下拉 →「整理提示词」弹窗（正文预格式化展示 + 使用说明 + 「复制」按钮；外壳文案 `t()`） | 真机：复制内容与原文件一致；中英界面切换正常 |
| M7.4 | 文档同步收口：to-dolist 附录 A 改为指向事实源文件（生成/迁移说明，防双份漂移） | 附录 A 仅保留链接与摘要；改一次源文件后两处一致 |

**验收**：用户按「复制提示词 → 发给 Agent → 收平面文件 → 平面导入」在样例库完整走通（spec §12 全流程）。

---

## 状态跟踪表

| 模块 | 状态 | 备注 |
|---|---|---|
| M0 扫描/契约 | ☑ | M0.1–M0.3 通过：三源扫描/JSON·Markdown 导出/重名冲突原语/bundle 子目录 sidecar 映射/幂等一致性 |
| M1 执行器 | ☑ | import_executor.py：三源写盘/sidecar（flat range·md 无 range·bundle 改写）/决策 skip·overwrite·rename/幂等跳过/图谱构建；冒烟通过（重导 unch=1 w0 kp0） |
| M2 RPC | ☑ | ui.py 新增 select_import_sources/import_scan/import_execute（decisions 校验），旧接口标 deprecated；md_dir 目录递归保子目录结构；py_compile+冒烟通过（对话框真机项归 M6） |
| M3 前端 | ☑ | import-flow.js 重写为统一向导：源选择卡 → import_scan 预览（摘要/文件/KP/冲突）→ 冲突逐项+应用到全部+重命名输入 → 复制反馈 JSON/Markdown → import_execute → 结果（新增 import.* 键 ~34 个 zh/en 成对；真机交互项归 M6） |
| M4 i18n | ☑ | import.* 键族补齐，zh/en 平衡（0 missing/en-only），node --check+selftest PASS，扫描器 rows=0 |
| M5 文档/样例 | ☑ | to-dolist 附录 A（→organize.zh-CN.md 单一事实源）/B（→import-spec §4A）收口为指针；import-test 夹具就位（flat/mdsrc/bundle）；.gitignore 忽略 empty*/导入test/行政法 本地库（M5.3） |
| M6 版本/回归 | ☑ | 版本 0.3.0（__version__/README 徽标+正文）；自动化回归通过；GUI 真机项已用 browseragent × `_harness_import.py`（empty3）跑通：三源 × 新建/幂等/冲突(跳过·覆盖·重命名) 全 ✓ + 结构核对（见 M6.2 回归记录） |
| M7 程序内 Agent 提示词 | ☑ | organize.zh-CN.md 事实源 + get_agent_prompt RPC（与文件字节一致）+ 导入向导「Agent 整理提示词」卡/复制视图 + 附录 A 同步指针；en 缺键回退 zh 文件 |

> 推进规则：每模块按阶段执行；每阶段结束给出该表验证结论（命令/断言/真机记录）后再进入下一阶段。
