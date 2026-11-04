# B4 / task-351 报告 —— I-07 RendererAdapter(2D) + I-08 NavController

> **开工基线**：HEAD `8f582c79`（B3 已提交）。本任务**未 commit**。
> **冻结输入（只读）**：`S3-visual-v1`+ADDENDUM-1/2、`S4-render-v1`、`S5-nav-v1`（T01–T30）、`S6-contract-v1`（S6-6/S6-7）、`S8-metrics-v1`（冻结值）、`docs/todo/20-multilevel-graph-0.5.md`。
> **写域**：只新增 `src/memoria/ui/static/app/js/graph-multilevel/**`、`tests/graph/render/**`、`tests/graph/nav/**`；**未改** `docs/design/**`、旧 `graph-view-2d.js`/`app.js`/其他 `src` 域，**未 commit**。

## 0. 一句话结论

B4 的 P0 面全部有机器证据：**2D RendererAdapter**（只画 `presence=shown`、禁止读 `data_edge_ids`、预算 fail-visible、确定性布局/会话内保位、复用旧 label LOD、事件回传、3D `capability=false` 显式回退 2D）+ **NavController**（9 主状态 + 正交变量、T01–T30 全绿、`frame_id=sha256(canonical(S4_FRAME_SPEC))` 与 Python 常量一致、事务失败 diff=0、expand 不改 nav）。旧 KGviz 入口**物理保留**；差异逐项登记在 `legacy-alignment.json`。

## 1. 交付物

```
src/memoria/ui/static/app/js/graph-multilevel/canonical.js       规范 JSON + 同步 SHA-256（与 Python canonical_bytes 一致）
src/memoria/ui/static/app/js/graph-multilevel/renderer-adapter.js Renderer2D + Renderer3D(capability=false) + 工厂
src/memoria/ui/static/app/js/graph-multilevel/mount.js           挂载 + 渲染器事件 → NavController + 3D 显式回退 2D
src/memoria/ui/static/app/js/graph-multilevel/nav-controller.js  S5 状态机 + frame_id + 事务化
tests/graph/render/renderer_adapter.test.js                      13 条 Node 机检
tests/graph/render/test_renderer_adapter.py                      pytest 包装 + node --check + budget/对齐清单
tests/graph/render/fixtures/vm-b4.json                           B3 VM 白名单 fixture（含 suppressed/unknown/data_edge_ids 审计边）
tests/graph/render/legacy-alignment.json                         旧 KGviz 功能对齐清单（7 项 + 未关闭项）
tests/graph/nav/nav_controller.test.js                           15 条 Node 机检（T01–T30 逐行）
tests/graph/nav/test_nav_controller.py                           pytest 包装 + frame canonical/T 行冻结
```

## 2. 验收证据（命令 / exit code / 结果）

| # | 验收 | 命令 | 结果 |
|---|---|---|---|
| 1 | 2D smoke / 事件 / 同签名 | `node tests/graph/render/renderer_adapter.test.js` | exit 0；**13/13 PASS**：只画 shown（fixture 6 节点→4 绘制、5 边→3 绘制）；`nodeClick/edgeClick/backgroundClick/hover` payload 无导航字段；2D/3D 五方法参数个数一致 |
| 2 | 冻结预算结构断言 | 同上 + `pytest tests/graph/render` | `MAX_NODES=200 / MAX_EDGES=400 / ANIMATION_MAX_MS=180`；201 节点/401 边 ⇒ `RENDER_BUDGET_EXCEEDED`（**不静默裁剪**）；200/400 实测 render **1.62ms**、update **1.04ms**（Node fake-host，参考值非 P0） |
| 3 | 3D `capability=false` 且不阻断 | 同上 | `capability/capable=false`、`reason=3D_NOT_IN_0_5`；render/update throw `RENDER_UNSUPPORTED_BACKEND`；`mountGraphView(backend=3d)` **显式回退 2D**（`fellBack=true`）且 2D 继续可用 |
| 4 | T01–T30 全绿 | `node tests/graph/nav/nav_controller.test.js` | exit 0；30 行全部有可执行场景且 PASS（`details.t01_t30` 覆盖 T01..T30）；9 主状态/21 事件/`(state,event)` 唯一 |
| 5 | `frame_id` 可复算 | 同上 + pytest | `frame_id == sha256(canonical(S4_FRAME_SPEC))`；与 Python `sha256_canonical` 4 个常量逐一相等（默认/full/H 维/hop2） |
| 6 | nav 事务化 diff=0 | 同上 | CLICK_CLUSTER/SELECT_DIMENSION/TOGGLE_EXPAND 注入 S4 失败 ⇒ `ok=false`、`snapshotSha` 不变、stack 无孤立项；栈溢出失败同样 diff=0 |
| 7 | expand 不改 nav | 同上 | state/focus/level/dimension/stack 全部不变；仅正交 `mode` 切换；S4 请求带 `mode=full`；frame_id 可按新 mode 复算 |
| 8 | 功能对齐逐项 PASS | `pytest tests/graph/render` | `legacy-alignment.json` 7 项全 PASS/已登记差异（见 §4） |
| 9 | `node --check` | pytest wrapper | graph-multilevel 4 个模块 + 2 个测试 JS 全过（exit 0） |
| 10 | 不改 src 其它域 / 冻结稿 | `git status --porcelain` | 仅 `?? graph-multilevel/ ?? tests/graph/nav/ ?? tests/graph/render/`；`docs/design/**` 无改动 |

### 门禁
```
pytest -q tests/graph            => 248 passed
pytest -q（全仓）                => 1958 passed, 7 skipped
node --check（全部改动 js）       => 0 fail
i18n_selftest.js                 => PASS, exit 0
team_audit.py                    => FAIL=4（**均为既有仓库级问题，非 B4 引入**，见 §6）
```
## 3. 关键实现口径

- **唯一输入 = B3 VM**；Renderer 只按 S3 白名单读取节点/边字段，**不读 `data_edge_ids`**（静态扫描 + 行为等价测试），不做 presence/裁剪（S4 唯一裁剪者），只渲染 `shown`。
- **S3 token**：KP 固定半径 **8px**（screen-space，不按 degree）；cluster `clamp(8+2.2·log2(member_count+1),12,28)`；cluster 徽标=member_count；root_exempt 虚线双环；只画 shown 边。
- **确定性布局 + 会话内保位**：seed = `layoutSeed` 或 `fnv1a(view_model_id)`；同 VM 两次 render 位置 deep-equal；`update(sameVM)` moved=0（不 reheat）；`relayout:true` 才重排。
- **事件白名单**：`nodeClick{node_id,kind}` / `edgeClick{edge_id}` / `backgroundClick{}` / `hover`；无 frame/mode/focus/history 等导航字段；`handleRendererEvent` 是唯一入口。
- **Nav**：`GraphNavFrame` 只在 Presentation；frame_spec 8 字段；`frame_id` 每次从 spec 派生；stack 存 `{frame_id, canonical_frame_ref(=S4_FRAME_SPEC), ts}`；MAX_STACK=50；持久化只白名单 `mode/dimension/level0`；非法 `(state,event)` fail-closed。
- **3D**：仅同签名五方法 + `capability=false`；`render/update` fail-visible；mount 回退 2D（S3-11 降级可见）。

## 4. 旧 KGviz 功能对齐（0.4.10；详见 legacy-alignment.json）

| 旧能力 | 状态 | 说明 |
|---|---|---|
| 连续节点大小 | LEGACY_ONLY_REGISTERED_DIFFERENCE | 新图按 S3 冻结 token（KP 固定 8 / cluster 公式；VM 无 degree）；旧视图连续大小原样保留 |
| 度 tooltip | LEGACY_ONLY_REGISTERED_DIFFERENCE | 新 VM 按 S3 无 degree ⇒ tooltip 原值需 Presentation 补；旧 tooltip 保留 |
| 标签 LOD/避让 | **PASS** | 复用 `MemoriaGraphLabels.layoutNodeLabels`（机检证明被调用） |
| 布局确定性种子+会话内保位 | **PASS** | 新 Renderer 确定性布局；update moved=0；旧布局模块保留 |
| 边高亮 | **PASS** | hover 关联边 alpha 0.95 / 非关联 0.5（机检 stroke alpha） |
| 3D 光晕 | PASS_LEGACY | 0.5 不做 3D；旧 3D 入口保留；新接口 capability=false |
| legacy 入口保留 | **PASS** | 未改 app.js/index.html/旧 view ⇒ 旧 2D/3D 仍是默认路径；新挂载器需显式调用 |

## 5. 未关闭项（已登记，报 Lead）

1. **新 Renderer 未接入 app.js/index.html**（B4 写域不含；接入需 Lead 批准并记录基线）。当前新模块只能通过 `mountGraphView()` 显式使用；旧入口仍默认。
2. **degree tooltip 新路径数据源**：S3 VM 白名单无 degree，需 Presentation 从 S4/DataSource 取原值（后续任务）。
3. **S5 附录 A 的 148 边口径差异**：按唯一 `(state,event)` 展开为 **89** 条；S5 工程校核同时写"148 边 / 149 边全部唯一"，两者与唯一性口径不一致。B4 按唯一口径实现并测试，已在此报告；请 Lead/SE 复核 148 的展开定义（若是 target 组合展开，会与 R-S5-10 唯一性冲突）。
4. **严格复用旧 `graph-view-2d` 相机/缩放**：当前新 Renderer 是独立 VM→canvas 实现（仅复用 label 模块与确定性种子思路），未复用旧 `GraphView2D` 实例（旧 view 绑定旧 engine/连续大小语义，直接复用会把旧 token 带入新图）。若 Lead 要求严格复用旧取景/相机，需要改 `graph-view-2d.js`（写域外，需先报 Lead + 基线）；取景/裁剪/presence 本身未重写：presence 归 S4，Renderer 只过滤 shown。

## 6. team_audit FAIL=4（既有问题，非 B4）

```
[FAIL] deliberation_quality：artifacts/agent/verify/debate/graph-utility/** 102 个辩论产物未被 git 跟踪
[FAIL] l1_task_before_spawn：历史 dispatch-log 15 条 spawn 未配对 --task 行（2026-10-27 记录）
[FAIL] prompt_drift ×2：resources/agent-prompts/kb-agent-readme.md 依赖 apply.py / plugins.py 变更
```
- 上述 4 条均与 B4 新增文件无关（B4 文件在 `graph-multilevel/**`、`tests/graph/{render,nav}/**`，尚未 commit 属预期）；请 Lead 处置。

## 7. 复跑

```powershell
.venv\Scripts\python.exe -m pytest -q tests/graph
node tests/graph/render/renderer_adapter.test.js
node tests/graph/nav/nav_controller.test.js
node --check src/memoria/ui/static/app/js/graph-multilevel/canonical.js
node --check src/memoria/ui/static/app/js/graph-multilevel/renderer-adapter.js
node --check src/memoria/ui/static/app/js/graph-multilevel/mount.js
node --check src/memoria/ui/static/app/js/graph-multilevel/nav-controller.js
```
