# 链接文本模型（M2 设计草案）

> 用户结论：**`[[]]` 里只放用户可见文本；文本即全局跳转定位键；改入口不改正文，而是重新扫描 + 用户多选确认。**

与 designV0 §3.5 一致，并废弃「链接键 ≠ 显示文字」为默认路径（`[[id|label]]` 仅作兼容/迁移）。

---

## 1. 核心原则

| 原则 | 说明 |
|------|------|
| **文本即键** | `anchor_text` = 用户看到的字符串 = 正文 `[[]]` 内的内容 |
| **全局入口** | 同一文件内，相同字符串共用一个 sidecar **跳转入口**（同 `targets[]`） |
| **实例可选** | 并非每一处相同文字都必须可点；用户多选哪些位置「挂接」到该入口 |
| **改键不改正文** | 修改入口匹配文本时，**不做**全文 replace；重新扫描 → 匹配面板 → 用户确认包裹/解除 |
| **单点剔除** | 右键某一处的链接 →「从跳转入口移除此处」：只 unwrap 该实例，不删整个入口 |

```
跳转入口 (sidecar links[])
  anchor_text: "按顺序点"
  targets: [actor-critic-框架]
  instances[]          ← 挂接到该入口的正文位置（显式列表）
    - { line, col, wrapped }
  excluded[]           ← 用户明确排除的位置（防止自动扫描再挂上）
```

---

## 2. 正文语法（目标态）

**唯一推荐写法：**

```markdown
可继续点 [[按顺序点]] 查看详情。
```

- `[[]]` 内 = 页面上看到的字 = `anchor_text`
- **不再**默认使用 `[[q-learning|Q-learning]]`；旧文件只读兼容，编辑保存时引导合并为文本键

**跳转解析：**

```
点击预览中的「按顺序点」
  → anchor_text = "按顺序点"
  → sidecar.links[].targets
  → resolve → 打开文件 + KP range
```

---

## 3. 实例（occurrence）模型

当前 M1 仅有单个 `occurrence: 0`，不足。M2 改为：

```yaml
links:
  - anchor_text: 按顺序点
    targets: [actor-critic-框架]
    instances:
      - line: 18
        start: 842        # 可选：UTF-16/byte offset，用于稳定定位
        wrapped: true     # 正文是否为 [[按顺序点]]
    excluded:
      - line: 10          # 第 10 行虽有「按顺序点」但用户排除
```

**规则：**

1. **扫描**：在正文中找 `anchor_text` 的 plain 出现 + 已有 `[[anchor_text]]`
2. **默认挂接**：新建入口时，匹配面板默认勾选全部（或 sidecar 无 `instances` 时视为「全部 plain + wrapped」）
3. **剔除**：右键 → 从入口移除 → unwrap + 写入 `excluded` 对应 line/offset
4. **预览**：仅 `instances` 中且未在 `excluded` 的位置渲染为可点链接

---

## 4. 交互流程

### 4.1 创建入口（选区 / 配置）

```
用户选中「按顺序点」或配置里填匹配文本
  → 扫描全文所有匹配
  → 打开「匹配确认」面板（见 §5）
  → 用户勾选位置
  → 勾选处写入 [[按顺序点]]，sidecar 写 targets + instances
```

### 4.2 修改匹配文本（重命名入口）

```
配置里把「查看二者」改为「按顺序点」
  ❌ 禁止：全文 replace 查看二者→按顺序点
  ✅ 正确：
     1. 旧 instances 全部 unwrap（或保留 plain 原文）
     2. sidecar anchor_text 更新
     3. 对「按顺序点」重新扫描 → 匹配确认面板
     4. 用户勾选 → 包裹 [[]] + 写 instances
```

### 4.3 右键 · 从跳转入口移除此处

```
预览/源码中某一 [[按顺序点]]
  → 右键「从跳转入口移除此处」
  → 仅该 instance：remove [[]] 保留 plain 文本
  → instances 删除该项；excluded 记录 line
  → 若 instances 为空且用户确认 → 可选删除整个 sidecar 入口
```

### 4.4 右键 · 编辑跳转目标

不变：仍进统一链接编辑器，改 `targets[]` / pool，**不改**匹配文本逻辑（改文本走 §4.2）。

---

## 5. 「匹配确认」面板 UI

**入口：** 创建入口、修改 anchor_text、文件配置「重新扫描匹配」

```
┌─ 匹配「按顺序点」— navigation-demo.md ──────────────┐
│ 共 3 处 · 已挂接 1 处 · 排除 0 处                    │
├──────────────────────────────────────────────────────┤
│ [全选] [仅选未包裹] [清除]                             │
│                                                      │
│ ☑ L18 · 同段多链接                                   │
│     …可继续点 [[ddpg]] 按顺序点 在深度 RL 中的结合。    │
│     ^^^^^^^^ 高亮                                      │
│                                                      │
│ ☐ L10 · 多跳链路                                     │
│     按顺序点击（每跳一次后可用工具栏 ← 返回）：         │
│          ^^^^ 子串匹配（灰显，默认不勾）               │
│                                                      │
│ ☑ L42 · （未包裹）                                   │
│     …详见 按顺序点 一节。                              │
├──────────────────────────────────────────────────────┤
│ [取消]                    [确认并包裹所选 (2)]        │
└──────────────────────────────────────────────────────┘
```

**位置标识（回答「用户怎么知道在哪」）：**

| 元素 | 作用 |
|------|------|
| **L{行号}** | 主定位，与编辑器/assist 一致 |
| **章节名** | 向上找最近 `##` 标题，给语义上下文 |
| **snippet 行** | 匹配 span 前后各 ~40 字，匹配段 `<mark>` 高亮 |
| **状态徽章** | `已包裹` / `plain` / `已排除` / `子串`（不满足整词规则时） |
| **点击行** | 预览/源码 scrollIntoView + 临时 range 高亮（复用 KP 高亮带） |
| **hover** | 左侧色条 + 行号加粗（与 assist 候选行同风格） |

**子串规则：** 与 M1.5 `find_plain_text` 一致——「按顺序点」不匹配「按顺序点击」；子串行显示但默认不勾选。

---

## 6. 与现有组件关系

| 现有 | M2 调整 |
|------|---------|
| 链接编辑器 | 「显示文字」= anchor；去掉「链接键≠显示」高级默认；改 anchor 触发匹配面板 |
| `save_link_route` | 不再 `wrap_plain_text` 静默包裹；改为 `propose_link_instances` → 用户确认 API |
| `link_overrides` | key 仅为 `anchor_text`（可见文本） |
| `[[id\|display]]` | 只读；保存时提示迁移为 `[[display]]` |
| 预览灰色 | sidecar 有 targets 且 ≥1 可解析 → 可点（已实现）；实例未挂接处不渲染为链接 |

---

## 7. API  sketch（M2）

```python
scan_link_text_matches(rel_path, anchor_text) -> {
  matches: [{ line, col, end_col, snippet, wrapped, excluded, section }]
}

apply_link_instances(rel_path, anchor_text, targets, selected_lines[], ...) -> document

detach_link_instance(rel_path, anchor_text, line, col) -> document  # 单点剔除
```

---

## 8. 实施阶段

| 阶段 | 内容 |
|------|------|
| **M2a** | 设计对齐；链接编辑器 UI 文案；右键「从跳转入口移除此处」；`detach` API |
| **M2b** | `scan_link_text_matches` + 匹配确认面板 + 创建/重命名走面板 |
| **M2c** | sidecar `instances`/`excluded` schema；预览只渲染挂接实例 |
| **M2d** | 废弃 `[[id\|display]]` 写入；迁移工具 |

---

## 9. 一句话

**`[[]]` 是用户在正文里认得的字，不是系统 id；同一字共享一个跳转配置；哪些行算这个字的「入口」由扫描 + 用户勾选决定，改字只重新找、不硬改原文。**
