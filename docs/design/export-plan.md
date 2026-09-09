# 导出功能设计（Export Plan）

> **用途**：为「文件 → 导出知识库」板块（当前为占位）拟定设计方案：范围界定、产物规格、RPC 与 UI 交互、验证阶段，供评审后实施。本期只锁定一种导出形态——**知识库包（kb_bundle）导出**（= 导入包的逆过程）；全库静态 HTML（R12）、沿路拼接导出（R14）、导出 PDF 均为**非本期**，见 §9。
> **目标读者**：项目负责人（用户，评审范围与拍板打开问题）；实施 Agent（按本方案分阶段落地）。
> **关联文档**：[import-spec.md](../reference/import-spec.md)（**bundle 布局单一事实源**——本方案不重复定义包结构，只定义"导出行为"）；[import-plan.md](../reference/import-plan.md)（导入分阶段实施与验证范式）；[dicussion.md](./dicussion.md)（R12/R14 路线图出处）；[docs-management.md](../conventions/docs-management.md)（登记与索引）。
> **状态**：草稿（待评审），2026-09-08 建立；2026-09-09 复核恢复（此前一度缺失致引用悬空）。
> **施工挂接**：见 [to-dolist.md §12 B7](../to-dolist.md)（导出知识库包，⏳ 待评审）。

---

## 1. 背景与动机

- 现状：「文件 → 导出」为 `disabled` 占位，tooltip「导出知识库（预留，待后续版本）」。
- 需求本质：让当前打开的知识库可被**完整带出**——用于备份、换机迁移、与他人交换/合并（他人用现有「导入」即能回灌，见 import-spec 场景 C）。
- 对称性：导入已支持 `kb_bundle`（md + sidecar + manifest）三源之一（import-spec §4C），导出做其逆过程，格式零新增、可直接复用 `validate` 与库内布局规则。

## 2. 范围界定

| 项 | 本期（Y） | 说明 |
|---|---|---|
| 导出为知识库包（bundle） | ✅ | 唯一本期交付 |
| 导出目标含图片资产（`.memoria/images/`） | ⏳ 打开问题 | 见 §8 决策 1 |
| 导出前清单预览 | ✅（轻量） | 摘要=文件/KP/边 计数，不必做到导入级冲突交互 |
| 合并/增量导出到已有目录 | ❌ 本期不做 | 本期只导出到**新建/空目录**；合并语义留给后续 |
| 全库静态 HTML 导出（R12） | ❌ | 保持 V2+/💡 状态 |
| 沿路拼接导出新文档（R14） | ❌ | 保持 V2 ⏳ 状态 |
| 导出 PDF | ❌ | 保持 💡 状态（无设计细节） |

## 3. 术语与现状（输入侧事实）

- 库内 `.memoria/` 实际包含：`sidecars/`（与 md 树**镜像**）、`cache/`（词法/embedding 索引，可再生）、`images/`（图片资产 + `registry.json`）、`manifest.yaml`（库级元数据）、`pending.yaml`（待确认）。见 `docs/example/*` 实际布局。
- bundle 导入期望的最小结构（import-spec §4C）：`manifest.yaml`（可选包级元信息）+ md 树 + `.memoria/sidecars/` 树；**不消费** cache/、pending/。
- 导出器产出物必须满足「导出的包能被 validate / 导入」——即与库内布局一致、路径相对、`\`→`/`。

## 4. 产物规格（目标目录布局）

用户选择目标目录 `T`（必须不存在或为空，见 §8 决策 2）。导出后：

```
T/
  manifest.yaml            # 导出器生成：package: name/version/source_kp_count + exported_at 等
  <md 树原样>              # 正文、子目录、frontmatter 原样复制（含相对路径图片引用）
  .memoria/
    sidecars/<树镜像>.memoria.yaml   # 与 md 一一对应复制
    images/                # [⏳ 决策 1] 图片资产 + registry.json（若包含）
```

- **排除**：`.memoria/cache/`、`.memoria/pending.yaml`、`.bak` 文件、`logs`/杂散（非 KB 内容）。判定以「该目录属于 KB 内容（md/sidecar/manifest/images）还是运行时可再生/待确认」为准。
- **复制语义**：md/sidecar 为**原样拷贝**（不改正文、不改 id）；manifest 为**导出器重建**（不复制库内可能过期的旧值，`source_kp_count` 以实扫为准）。
- **一致性**：导出完成后对 `T` 跑 `validate`（导入侧既有），结果计入完成反馈；发现未配对 sidecar/md 列入警告但**不阻断**（允许纯文件 md）。

## 5. 后端 RPC 设计草图

沿用导入两段式（scan 预览 → execute 落盘）范式，接口命名入 `ui.py` 并登记 i18n 键族 `export.*`：

```
select_export_target() -> {status, dir?}                 # 系统目录选择对话框（pywebview 宿主已有同类实现）
export_scan(target_dir)  -> ExportPreview                # 只读：统计 files/kps/edges + 目标目录合法性检查
export_execute(target_dir, options) -> ExportResult      # 写包 + 自校验
# ExportPreview/ExportResult 字段（与 ImportResult 同风格，冻结后登记）：
#   { target, files, kps, edges, images, manifest, errors[] , validated{ok,issues} }
```

- **前置条件**：已打开知识库（无 KB → 菜单项置灰/点击提示先打开）。
- **目标目录校验**：不存在 → 创建；已存在且非空 → 错误返回「请选择空目录」（本期策略，决策 2 复核）。
- **原子性**：先写临时子目录 `T/.export-staging-<ts>/` 完成后再移入 `T`；任一步失败 → 清理 staging、返回部分失败明细（可复用导入 partial 状态语义）。
- **不改原库**：全程只读源 KB；绝不写回、不删 `.bak`、不动 cache。

## 6. UI 流程

1. 菜单启用：`#file-menu-export` 移除 `disabled`；tooltip 更新为实际语义。
2. 点击 → RPC 目录选择 → `export_scan` 预览（摘要行 + 目标目录合法性）→ 确认 → `export_execute` → 完成反馈（文件/KP/边/图片计数 + 自校验结果）＋「打开文件夹」按钮（宿主能力，沿用现有「打开路径」实现）。
3. i18n：新增 `export.*` 键族（zh/en 成对），沿用「文案走 i18n、内容不进 i18n」纪律；按钮与预览行均走 `t()`。
4. 无 KB 时该项保持灰显（与「导入」同策略，先开后用）。

## 7. 阶段与验证（评审通过后执行）

| 阶段 | 内容 | 验证 |
|---|---|---|
| M1 后端扫描 | `export_scan`：目标合法性 + 文件/KP/边统计 + 排除规则 | py_compile；对 showcase 库产出 preview 计数与磁盘实扫一致 |
| M2 写包与自校验 | `export_execute` + staging/原子 + validate 自检 | 导出到空目录 → 包结构/计数与库内三方核对（md、sidecar、manifest） |
| M3 RPC | 两接口桥接 + 取消/错误处理 | 冒烟：无 KB / 目标非空 / 只读目标 三种错误路径 |
| M4 前端 | 启用菜单 + 流程 + `export.*` i18n zh/en | browser/harness 真机：导出 showcase → 用「导入」回灌到空库 → 结构等价断言 |
| M5 文档/登记 | 本设计定稿 + docs-management 修订记录 + to-dolist 勾选 | 文档索引同步；单一事实源指针（import-spec §4C）不重复定义 |

推进规则同 import-plan：每阶段结束给出验证结论后再进下一阶段。

## 8. 打开问题（评审需拍板）

- 决策 1：图片资产 `.memoria/images/` **是否随包导出**？——倾向 ✅ 包含（否则换机/分享丢图，相对路径引用悬空）；代价是包变大 + registry 一致性。
- 决策 2：目标目录已存在且非空时的策略——本期仅「报错要求空目录」；是否预留「导出=合并」到后续。
- 决策 3：`.bak` 是否排除——倾向 ✅ 排除（可再生草稿，导入侧也无需）。
- 决策 4：导出范围含库内**非 KP 纯文件 md**（无 sidecar）——倾向 ✅ 原样包含（导入场景 B 兼容）。

## 9. 非本期导出（保留路线图状态，不展开）

- **R12 全库静态 HTML**（dicussion §5.2 / R12）：只读子集分享，V2+/💡。
- **R14 沿路拼接导出**（dicussion §14 / designV0 §5.2）：路径 → 新 md+sidecar 草稿，V2 ⏳。
- **PDF**（to-dolist V04）：💡 无细节。
