# task-178 — KG 埋点 E1/E2（D-KGV-08）· KG v0 落地最后一项

> **基线**：HEAD `17edfe3e`（开工时）；本任务改 2 个既有文件 + 新增 2 个文件 + artifacts，未 commit。
> **设计依据（只读）**：`docs/design/kg-visualization-v0.md §5`（D-KGV-08：E1/E2 + style/zoom/语料上下文；明确不采 `node_radius_px` / `labelHover` 逐事件）；`PHASE4-RULINGS.md D-KGV-08`。
> **纪律**：未改 `docs/**`、`docs/example/**`、`Package/**`、`docs/conventions/**`；存储走 task-160 既有用户态目录，不新增第二条路径规则。

---

## 0. 一句话结论

**埋点已落地，且让两条"已冻结但缺数据源"的裁决可结算**：
- **E1** `nodeRadius` 变化、**E2** `graphStyle` 切换，带 style / zoom / 语料上下文，落 **`%LOCALAPPDATA%\Memoria\config\graph-telemetry.jsonl`**（本地、append-only、不上传）；
- 读取接口 `get_graph_telemetry_summary()` 能直接回答「nodeRadius 是否被改过、改过几次、从多少到多少」「graphStyle 各风格启用分布」；
- **T-tel-7 已证明**：写失败/前端 RPC 失败都**静默降级 + 可观测计数**，主功能（设置保存）不受影响、页面零异常。

| 验收 | 结果 |
|---|---|
| **T-tel-1** 改 nodeRadius 落一条 E1（from/to 正确） | ✅ 真机 6→8、8→10 各落一条；文件行含 `{v,ts,ts_utc,event,from,to,style,zoom,zoom_kind,node_count,edge_count,corpus}` |
| **T-tel-2** 切 graphStyle 落一条 E2（from/to 正确） | ✅ `force→galaxy` 一条 |
| **T-tel-3** append-only；损坏行不影响后续追加 | ✅ 旧字节前缀不变；插入坏行后 `bad_lines=1`，后续追加仍成功且可读 |
| **T-tel-4** 读取接口汇总正确 | ✅ 单测 8 条记录 → E1 count/transition_counts、E2 distribution 全对；真机 RPC 返回 `E1 2 条（6→8、8→10）/E2 1 条（galaxy）` |
| **T-tel-5** 不联网 | ✅ 模块仅用 stdlib 文件 I/O；静态单测断言无 `requests/urllib/socket/urlopen` |
| **T-tel-6** 默认不采集时零开销（若做开关） | ✅ **不做开关**（v0 恒开但只在真实变化时写）；`_recordGraphTelemetry` 对非 E1/E2 设置项**零成本早退**；无变化/禁采字段不建文件 |
| **★ T-tel-7** 埋点失败不影响主功能 | ✅ 非法目录 ⇒ `status=degraded` 不抛错、`write_failures` 递增；RPC wrapper 永不 raise；真机模拟 RPC reject ⇒ `saveOk=true, pageErrors=0, noExtraLine=true` |
| 不采清单 | ✅ 无 `node_radius_px`、无 `labelHover`（单元测试检查代码行；注释中"不采"声明不算） |

---

## 1. 实现

### 1.1 存储层：新增 `src/memoria/storage/graph_telemetry.py`（用户态工具）

- **路径**：`MEMORIA_CONFIG_DIR`（测试/隔离覆盖）> `memoria.util.user_state.user_config_dir()` ⇒ **与 `ui-settings.json` 同目录**（task-160 的外置用户态，不新增路径规则）；
- **append-only JSONL**：`open("a")` + 每行一条 + `flush()` + `os.fsync()`；读取逐行 `try/except`（坏行计数 `bad_lines`，后续追加不受影响）；
- **事件白名单**：`nodeRadius_change` / `graphStyle_change`；字段白名单（kb_path/node_count/edge_count/style/zoom/zoom_kind/source）；命中 `node_radius_px`/`labelHover` **丢弃**；`from == to` 不记录（不是变化）；
- **语料上下文（服务端补全）**：`corpus = {kb_path, manifest_sha256(sha256 of .memoria/manifest.yaml), head(git rev-parse HEAD，KB 不在 repo 内则 null), measured_at}`；`node_count/edge_count` 来自前端当时引擎；全部计算失败都置 null，不抛错；
- **失败计数**：模块级 `_WRITE_FAILURES/_LAST_WRITE_ERROR`；`record_events()` 永不 raise，写失败返回 `{status:"degraded", error, write_failures}`；
- **无网络**：仅 `json/os/subprocess/time/datetime/pathlib/hashlib`；
- 单次写用 `no_window_kwargs()`（git 子进程；符合仓库"禁止控制台闪窗"静态扫描）。

### 1.2 RPC：`src/memoria/presentation/api/ui.py`（末尾追加，锚点零漂移）

```
UIAPI.record_graph_telemetry(events, context)      → 写 1..N 条（失败 degraded，不 raise）
UIAPI.get_graph_telemetry_summary()                → {E1:{count,changed_count,transitions,transition_counts,from_counts,to_counts},
                                                        E2:{count,distribution,transition_counts},
                                                        events_total,bad_lines,write_failures,path,...}
```
两条都包在 `try/except` 内：即使存储模块异常也返回结构化 `degraded`，**不打断用户操作**。

### 1.3 前端采集：`src/memoria/ui/static/app/js/graph-settings.js`

- `save(partial)` / `reset()` 对比改前/改后，只有 `nodeRadius`、`graphStyle` **真变**才进入埋点；
- **250ms 合并**：同一轮滑块拖动/快速切换合并为一条（from=最初值，to=最终值），避免把每个 input 像素记成一次"用户改变"；
- 上下文：`style / zoom（2D transform.k 或 3D camera distance）/ zoom_kind / kb_path / node_count / edge_count`；
- 落盘：`pywebview.api.record_graph_telemetry(events, ctx)`，`Promise...catch(()=>{})`；所有异常吞掉（T-tel-7）；
- 对非 E1/E2 设置项先**零成本早退**（不分配对象）；
- 暴露 `window.MemoriaGraphTelemetry.flush()`（测试/可观测用）。

---

## 2. 真机验证（`verify_telemetry.json` + 落盘副本 `graph-telemetry.jsonl`）

环境/语料：pywebview/WebView2，HEAD `17edfe3e`，语料 = 工作区 `docs/example/AAA_Vocab` 现场副本（134 节点 / 404 边）；`MEMORIA_CONFIG_DIR` = 临时隔离目录。

### 2.1 E1（6→8、8→10）与 E2（force→galaxy）
```
E1a lineCount=1  {event:"nodeRadius_change", from:6, to:8, style:"force",
                  zoom:0.138258, zoom_kind:"2d-scale", node_count:134, edge_count:404,
                  corpus:{manifest_sha256:"236a48…", head:null, measured_at:"2026-10-26T14:45:32.459+00:00"}}
E1b lineCount=2  {from:8, to:10}
E2  lineCount=3  {event:"graphStyle_change", from:"force", to:"galaxy"}
```
（`head:null` 是因为验证语料是临时副本、不在 git 仓库内——服务端如实置 null，不伪造。）

### 2.2 读取接口（真机 RPC）
```
status=ok  events_total=3
E1: count=2  transition_counts={"6->8":1,"8->10":1}
E2: count=1  distribution={"galaxy":1}
bad_lines=0  write_failures=0
path=<MEMORIA_CONFIG_DIR>/graph-telemetry.jsonl
```

### 2.3 T-tel-7 前端半场（真机模拟 RPC 失败）
```
api.record_graph_telemetry = () => Promise.reject(...)
MemoriaGraphSettings.save({nodeRadius:11})
⇒ saveOk=true（设置确实保存成功）  pageErrors=0（无未捕获异常）
⇒ lineCountAfterFailure == 3（没有多写半条），noExtraLine=true
```

### 2.4 文件属性
```
underUserStateDir=true（与 ui-settings.json 同一用户态目录）
lines=5（含最后恢复默认设置的 E1）  badLines=0  allHaveContext=true  bytes=2524
```

截图：`shots/01_settings_telemetry.png`。

---

## 3. 机检（`tests/test_kgviz_telemetry.py`，9 条）

| 测试 | 内容 |
|---|---|
| T-tel-1 | `record_events` 写入 E1，from/to/ts/v 正确 |
| T-tel-2 | E2 写入，from/to 正确 |
| T-tel-3 | 旧字节前缀不变（append-only）；插入坏行后仍可追加，`bad_lines=1`，事件序列正确 |
| T-tel-4 | 10 条造数 → `transition_counts` / `distribution` / `changed_count` 正确 |
| T-tel-5 | 模块源码无网络调用 |
| T-tel-6 | 无变化/禁采字段 ⇒ 不落盘、不建文件；前端对非 E1/E2 早退 |
| **T-tel-7** | 非法落盘目录 ⇒ `degraded`、不抛错、`write_failures` 递增；RPC wrapper 永不 raise |
| 前端结构 | E1/E2 事件名、250ms 合并、`record_graph_telemetry`、`.catch(()=>{})`、无禁采字段（代码行） |

> **过程中被现有门禁抓到一次真问题**：首版 `graph_telemetry.py` 直接 `subprocess.run` 调 git，被 `tests/test_console_no_window.py` 的静态扫描判红（控制台闪窗回归）⇒ 已改用 `no_window_kwargs()`；这也证明该门禁确实在防新增启动点漏接线。

---

## 4. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q`（基线 1547） | **1558 passed / 0 failed**（1547 + 9 新测 + 既有 doc-anchor/console 守卫全绿） |
| `node --check` 全部前端 js | **0 fail** |
| `i18n_selftest.js` | **PASS，exit 0** |
| `scripts/agent/team_audit.py` | **FAIL=0** |
| 12 交互剧本 | **12/12，failed=0**（26.1s，`scripts/benchmark/surface/results/raw-interaction-t178-final_17edfe3e.json`） |

---

## 5. 改动文件

```
src/memoria/storage/graph_telemetry.py            新增 303 行（用户态 append-only 埋点存储 + 汇总）
src/memoria/presentation/api/ui.py                +41 行（末尾追加 2 条 RPC；既有行号锚点零漂移）
src/memoria/ui/static/app/js/graph-settings.js    +109 行（E1/E2 采集 + 250ms 合并 + 失败静默）
tests/test_kgviz_telemetry.py                     新增 136 行（9 条机检）
artifacts/agent/verify/todo/kgviz-telemetry/      报告/JSON/落盘副本/截图/verify_telemetry.py
```
`git diff --stat`（既有文件）：2 files changed，+149/−1（不含新增文件）。

## 6. 复跑

```powershell
.venv\Scripts\python.exe -m pytest tests/test_kgviz_telemetry.py -q
.venv\Scripts\python.exe artifacts/agent/verify/todo/kgviz-telemetry/verify_telemetry.py
```
产物：`verify_telemetry.json`、`graph-telemetry.jsonl`、`shots/01_settings_telemetry.png`。

## 7. 诚实局限 / 登记

| # | 项 | 说明 |
|---|---|---|
| L1 | **无 UI 查看器** | 读取接口只到 RPC + Python 函数（`summary()`）；v0 不需要界面。 |
| L2 | **`head` 仅在 KB 位于 git 仓库内时非 null** | 用户普通 KB 不是 git 仓库 ⇒ `head:null`；`manifest_sha256 + measured_at` 仍可定位语料。 |
| L3 | **3D zoom 用相机距离** | `zoom_kind` 区分 `2d-scale` / `3d-camera-distance`，二者数值不可直接比较（已显式标注 kind）。 |
| L4 | **不做开关** | v0 恒开，但仅在真实变化时写；若将来要"关闭采集"，加一个本地开关即可（当前无 UI 需求）。 |
| L5 | **`node_count/edge_count` 是前端当时引擎值** | 与后端 `graph_audit` 可能不同（前端只走 collector 路径，与 D-KGV 第 2 条一致）；报告字段名已区分。 |
| L6 | **T-tel-7 后端真实磁盘满/权限失败未在真机复现** | 用非法目录 + RPC wrapper 单测覆盖；真机只覆盖前端 RPC 失败与正常写盘。 |
