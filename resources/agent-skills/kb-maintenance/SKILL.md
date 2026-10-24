---
name: kb-maintenance
description: 维护知识库的固定流程：改正文、建点连边、改文件都走 propose_write 一批写入（先读后写、写前备份、失败整批回滚、回执卡可撤销），并掌握各 op 的字段、顺序规矩与失败处理。
whenToUse: 用户要求新增 / 修改 / 删除知识库内容（正文、知识点、跳转、文件、图谱边），或你判断需要动库时
---

# 维护知识库（kb-maintenance）

> 本技能**随应用分发**（在知识库目录之外），它**没有**需要你另外读取的资源文件——照着下面做即可，
> 不要去读技能的资源目录（库外路径会被读取工具拒绝）。

## 1 唯一写入口：`propose_write`

所有库内内容改动都走 **`propose_write`** 一个工具，**一次调用即落盘**（不再有"提议 → 人点确认"两步）。
它内部自动：校验 → 试算（dry-run）→ 写前备份 → 整批写入 → 审计；失败**整批回滚**、库一个字不动；
写成功后用户在对话栏**回执卡**上可「撤销这一批」。

信封（`op_id` 可省，默认 `o1`、`o2`…）：

```json
{ "intent": "一句话说清这批要干什么", "ops": [ { "op": "动词", "op_id": "o1", "…": "…" } ] }
```

一批里的 op **按你给的顺序执行**，后面的 op 看到的是前面 op 生效**之后**的正文。

## 2 先读后写（硬闸）

写之前**必须**用 `read_document`（或 `grep` / `glob`）读清目标文件的**当前**原文与行号——凭印象写必被拒。
撞到下面三闸就回头重读：

| 错误码 | 含义 | 怎么办 |
|---|---|---|
| `FS_NOT_OBSERVED` | 这个文件你还没读过 | 先 `read_document` 再写 |
| `FS_NOT_FOUND` | 你读到过它、但当时不存在 | 重读，确认它现在在不在 |
| `FS_STALE_VERSION` | 你读之后它被改过了 | 重读拿**当前**行号与逐字原文 |

## 3 op 一览（16 个可写 + 1 个只登记）

**正文（行级）**：`replace_lines`（`range`+`expect`+`text`）/ `insert_lines`（`after`+`expect`+`text`）/
`delete_lines`（`range`+`expect`）。`expect` 必填——它是"改哪里"的内容级门槛，要**逐字**对得上原文。

**整块**：`upsert_block`（代码块 / mermaid / 公式，`kind`+`range`+`expect`+`content`；**表格不支持**）。

**知识点 / 边 / 链接**：`upsert_kp`（新建/更新 KP）/ `rename_kp`（改 id，全库级联）/ `delete_kp`（只删配置、
正文不动）/ `upsert_edge`（建边）/ `attach_links`（挂跳转、包裹正文 `[[…]]`）/ `detach_links`（拆跳转、还原正文）。

**文件**：`create_file` / `rename_file`（全库级联 `[[stem]]`）/ `delete_file`（被正文引用会**硬拦**）/
`move_file`（跨目录搬）/ `rebuild_manifest`（等价界面「构建」）。

**图片**：`insert_image_ref`（往正文插一行图片引用；图片入库 / 改属性 / 移动删除**不做**）。

`set_kp_range` 只登记、**未编译**——不要提它（会被当未实现）。

## 4 顺序规矩（两条）

- `rename_file` / `delete_file` / `move_file` 必须是**最后一条**（它们改路径或全库引用，之后再有 op 会活在
  两套坐标系里）。
- 其余"先建后挂"放**同一批**：`先 replace_lines 写正文 → 再按新行号 upsert_kp → 再 attach_links`；
  `先 create_file 新建 → 再给新文件建点挂链`。

## 5 失败怎么处理

| 返回 | 怎么办 |
|---|---|
| `INVALID_PLAN`（校验/试算没过） | 按返回的每个 `op_id` 的错误改对，**重提整批**——别删出错的 op、也别丢掉没出错的 op |
| `WRITE_FAILED` | `stale_write` ⇒ 重读文件拿当前行号/原文后重提；`backup_failed` / `path_rejected` ⇒ 稍后重试或换路径；其余原样告诉用户，**不要反复重试同一批** |

## 6 这几件事不走 `propose_write`

- **复习卡**：`review_cards_upsert` / `review_card_disable` / `review_grade` / `review_due_list` 等 `review_*`
  工具；**绝不直写** `cards.json` / `progress.json`。
- **联网抓取**：`web_search` / `fetch_url`（正文落待确认清单，不进上下文；见 `web-research` 技能）。
- **中间产物 / 跑命令**：`scratch_write` / `scratch_read` 落脚本工作区；用 `pwsh` / `cmd` 执行（每次执行
  **要过审批**、工作目录限库内）。

## 7 不许做的事

- 不凭印象写行号/原文——先读。
- 不直写任何 `.memoria/**` 事实源（sidecar / manifest / pending 都由编译器经原语落盘）。
- 不重复提同一批（写成功了就别再发一遍）；被拒也别换汤不换药地重试。
