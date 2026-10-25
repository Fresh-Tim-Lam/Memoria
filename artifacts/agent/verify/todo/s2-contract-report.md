# task-121（0.5.0-S2 服务层调用约定 + 写安全 W1–W4）收口报告

> **状态**：实现完成，`arch-contract` 待验收。
> **不 commit**（Lead 统一提交）。**全量 `pytest` 已跑**（见 §6：23 红全为预存债，0 新坏）。

## 1. 交付清单

| 类别 | 文件 |
|---|---|
| 生产代码 | `apply.py`（`origin` 必填参数 + W1 令牌校验）、`observation.py`（`issue_clearance`/`consume_clearance`/`CODE_GATE_BYPASS`）、`approvals.py`（`WriteCapability`/`WRITE_CAPABILITY`/`ContractViolation`/`CODE_APPROVAL_REQUIRED`）、`tools/kb.py`（`_bound` 签发令牌 + `origin="agent"`、粒度读喂 W2、"`snippet` 不记观察"、`KB_TOOL_NAMES` 补齐）、`ui.py`（`origin="human"`） |
| 契约文档 | `docs/design/agent-service-contract.md`（按 R-S2-11 重写 7 节） |
| 必红 fixture | `scripts/benchmark/maintenance/contract_w{1,2,3,4}.py` |
| 读写混合 A/B | `scripts/benchmark/maintenance/contract_readwrite_ab.py` |
| 被删除 | `src/memoria/services/agent/service_contract.py`（R-S2-15：零调用方） |

## 2. W1–W4 必红 fixture（每条都**构造违规路径**，不是 `assert raises`）

| Fixture | sha256 | 断言 | 关键判别力 |
|---|---|---|---|
| `contract_w1.py` | `d020cf7e…` | 8 条 | 漏传 `origin` ⇒ **TypeError**；`origin=""`/`"robot"` ⇒ `WRITE_ORIGIN_REQUIRED`；**人类路径无令牌 ⇒ 允许且真落盘**；`agent` 无令牌 ⇒ `WRITE_GATE_BYPASS` 且**备份调用 0 次、未落盘**；令牌重放 ⇒ 拒；缺 txid ⇒ 计划层拒 |
| `contract_w2.py` | `849179dd…` | 5 条 | 未读就写 ⇒ `FS_NOT_OBSERVED`；**`section` 后写必须放行**（R-S2-1 接缝，修复前=红）；`snippet` 后写 ⇒ 仍拒（片段≠看过）；读后被外部改 ⇒ `FS_STALE_VERSION` |
| `contract_w3.py` | `807f20df…` | 3 条 | 注入备份失败 ⇒ **零写入（sha 不变）**；写后 `restore_batch` ⇒ **逐字节**回 pre-image；备份批次里含写前 pre-image |
| `contract_w4.py` | `e5429a62…` | 4 条 | 核心写能力 + `auto` ⇒ `APPROVAL_REQUIRED`；`confirm` ⇒ 放行（**证明是条件规则**）；插件 `permissions.write` 非空 + `approval.write=auto` ⇒ 装载期 `approval_too_loose`；`confirm` ⇒ 不触发 |

## 3. 契约文档（R-S2-11 七处，全部按"当前实际行为"改写）

| 位置 | 改动 |
|---|---|
| 头部定位 | "facade 模块规格" → **"调用约定"**（R-S2-15：不建 facade 模块） |
| §1.2 | 拆成**两层**：工具分发层（W2/W4/令牌签发）vs 计划执行链（validate→compile→apply→restore）；明确 W2/W4 **不在**链上 |
| §2.1 | 补 `backup_failed`、`WRITE_GATE_BYPASS`、`WRITE_ORIGIN_REQUIRED`、`APPROVAL_REQUIRED` + `invalid_plan` **5 个子码** |
| §3.2 | `origin` 必填参数（已实现）+ **诚实边界**：令牌强度上限 = 「gate_ops 曾通过」不是「agent 真的读过」；进程内无法区分"人类 UI"与"撒谎的 human" |
| §3.4 | **等级差异表**：插件声明=装载期硬拒（强）/ 核心写=运行时判定（弱）；明确**否决**把 `replace_lines` 等加进 `RISKY_OPS` |
| §4 | 幂等**改为如实**：当前是「重复 txid ⇒ `backup_failed` 拒绝」，**不是幂等**；真幂等未实现、不承诺 |
| §5 | 删掉 facade 承诺：写侧契约面 = `apply_plan(origin=…)` + `WRITE_CAPABILITY` + 错误码；读侧**不抽**（R-S2-9），并给出延迟抽取触发条件（S3） |
| §6 | 读侧从"缺口"改为**既定架构**；新增 W1 边界、W4 等级差、幂等缺口、`gate`/`constrain` 死字段声明 |

## 4. `service_contract.py` 删除（R-S2-15）

- Lead 独立查调用图：`submit_write` **零调用方**（全仓仅该文件自身 3 处）；`propose_write` 自己做
  `gate_ops + issue_clearance` 编排，**未委托**给它。
- `WRITE_CAPABILITY` 已迁到 `approvals.py`（审批域，R-S2-9）；`service_contract.py` **已删**。
- 残留引用：仅 `approvals.py` 的一行注释（记录"不建"的裁决依据）与 `contract_w1.py` 的 docstring —— 均非代码依赖。

## 5. 读写混合 A/B（Lead 特别要求；`s2-readwrite-ab.json`，sha `b8790e7f…`）

5 个真实任务（真实工具 handler；**每臂都真写入成功**，失败数 0）：

| 臂 | 轮数(中位) | 每轮 tok(中位) | 总账 sum |
|---|---|---|---|
| **A 当前**：`read_document` → `propose_write` | 2 | 1000.5 | **18,278** |
| **B_after**：`outline` → `section` → `propose_write` | 3 | 191 | **4,055** |
| **B_before**（模拟 R-S2-1 修复前：section 后必须补 `read_document`） | 4 | 196.5 | **21,402** |

**结论（这是 Lead 要的"折扣"）**：
- **修复后：77.81%**（相对纯读 92.43% ⇒ **−14.62 个百分点**的真实折扣）
- **修复前（模拟）：−17.09%** —— 即**读写混合下粒度化反而比整篇读更贵**（多一轮整篇补读）。
- ⇒ R-S2-1 接缝修复在**读写混合**口径下价值约 **+94.9 个百分点**（−17.09% → 77.81%）。
- 口径声明：`B_before` 是**模拟**（修复已生效，无法真回退），依据是"修复前 gate 必报 `FS_NOT_OBSERVED`"这一确定性行为；产物里标 `emulated=True`。

## 6. 全量回归（Lead 纪律：改签名必须全量跑）

```
pytest -q tests        →  23 failed, 1437 passed   (64s)
```
Lead 用独立 git worktree 在 HEAD 上对照：
- 两边都失败（**预存债**）= **23 个**（前端渲染 / fsrs / `system_clipboard.py` 源码完整性；与本轮无关）
- 只在工作区失败 = **0 个**（**0 新坏**）
- 只在 HEAD 失败 = **2 个**（`test_agent_loop::test_loop_answers_without_tools`、`test_agent_session_query::test_kb_tool_names_match_built_tools`）⇒ 本轮**顺带修好**

`py_compile` 全部改动文件 = 0；未改前端、未 commit。

## 7. 本轮四个自我更正（比实现本身更值得记）

| # | 形态 | 谁发现 | 教训 |
|---|---|---|---|
| 1 | `heading=None` 静默回 `sections[0]`（S1） | 我自曝 → Lead 定性为生产缺陷 | 默认值让错误看起来像结果 |
| 2 | A/B harness 漏传 `heading`（S1） | 我自曝 | 度量脚本要像产品代码一样验证 |
| 3 | **`origin` 做成 plan 字段 ⇒ 省字段即绕过**（fail-open） | `arch-contract` 实测 | 不可信输入不能当安全开关；**调用点参数**才是 fail-closed |
| 4 | **改签名后没跑全量测试**（31 红） | Lead | 改签名 = 必须全量重跑再报（L2：自报 PASS 不算验收） |
| 5 | `KB_TOOL_NAMES` 未随 S1 三把工具更新（声明漂移） | 本轮全量跑 | 声明≠事实；roster 一致性测试必须跑 |

## 8. 已知缺口（诚实，不留在文档里充数）

1. **W1 的绝对边界**：进程内无法阻止 monkeypatch/伪造；`origin` 是调用点自述。
   真正"绕不过"要等进程边界（S3 MCP）。
2. **W4 等级差**：核心写能力只有运行时判定，没有插件那样的装载期硬拒。
3. **写幂等未实现**：重复 txid = 拒绝（不是幂等）。
4. **读写混合 A/B 是代理指标**：不调用模型；`B_before` 为模拟。真机完成率仍由 `metrics-baseline` 负责（S1 遗留债，未关）。
5. `gate` / `constrain` 仍是死字段（R-R1 已裁，S4/task-123 处理）；本契约**不依赖**它们。
