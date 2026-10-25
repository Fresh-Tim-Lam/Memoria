# S4 扩展点独立验收（task-123）

> **验收者**：arch-contract。**对象**：commit `7c4818fd`（S4 扩展点 + gate/constrain 移出 v1）。
> **方法**：读 `git show` 逐条核 diff + 亲自跑判别力脚本与夹具 + 复算 sha + 复核契约文本。
> **结论：通过**（附 1 条须记录的口径细节 + 4 条已知限制）。
> **未改 `src/**`**，未 commit。**HEAD**：`7c4818fd`

---

## 0. 结论

# **通过**

| # | 查项 | 结论 |
|---|---|---|
| ① | 20 处测试迁移强度 | ✅ **等强度或更强**，无静默放宽（详见 §1，含 1 处语义被替代的分析） |
| ② | 判别力（真红过） | ✅ 亲自跑：改回 gate ⇒ `1 failed/6 passed`；还原 ⇒ `7 passed` |
| ③ | 扩展工具三条硬要求 | ✅ 全部**真强制**（超时真杀进程 / 截断真切片 / 前 39 把逐项等于） |
| ④ | 安全边界如实声明 | ✅ 写得比我预期更硬，**明确否定**"因为 read_only 所以安全" |

**我复算的 sha**：`s4_sample_plugin/check.py` = `4c0ce4b13433e790`（11 条全 PASS）
**pytest**：**1462 passed / 0 failed**（独立复跑）

---

## 1. ① 20 处测试迁移强度（核心）

### 1.1 先确认改动面

```
git show 7c4818fd --numstat -- 'tests/*'
→ 28  11  tests/test_agent_plugins.py     ← 唯一被改的测试文件
```
其余 16 个文件全是源码/文档/资源。测试 diff **只有 3 个 hunk**。

### 1.2 逐条核（对照提案者自述）

| # | 测试 | 提案者说法 | 我的核实 | 判定 |
|---|---|---|---|---|
| 1 | `KB_WRITE` 共享 fixture | 删 `gate`/`constrain` 字段 | diff 确认：3 行改为无字段 + 2 行注释说明 | ✅ 不变 |
| 2 | `test_the_v1_exemplar_loads_verbatim` | "保留逐字装载 + tool_id 顺序" | **逐字比较确实还在**：`errors == []`、`declaration.id == "kb-write"`、`[tool.tool_id ...] == [...]`、`declaration.approval == {...}`、`[tool.primitive ...] == [...]` **全部保留**；只把 `tools[1].gate == ...` / `tools[2].constrain == ...` 换成 `not hasattr(...)` | ✅ **等强度** |
| 3 | `test_bad_gate_value_is_rejected` → `test_gate_field_is_removed_and_rejected` | "任何取值都必须 removed_field" | 旧：1 个值（`sometimes`）⇒ `bad_field`；新：**3 个值**（`always`/`kb_has_sidecar`/`sometimes`）⇒ `removed_field` | ✅ **更强**（见 1.3 分析） |
| 4 | `test_gate_defaults_to_always` → `test_tools_without_gate_load_and_have_no_gate_attribute` | （commit 未单列） | 旧：不给 gate ⇒ 默认 `always`；新：不给 gate ⇒ 照常装载 + **无 gate 属性** | ✅ **等价替换**（字段已删，"默认值"不存在） |
| 5 | 其余 ~17 条 | "断言一字未动" | diff 确认：**只有 3 个 hunk**，其余测试函数的断言行**零变化**（它们只因共享 fixture 带 gate 而红） | ✅ 属实 |
| 6 | `test_agent_web` 2 条能力闸测试 | "断言一字未改" | diff 里**没有 test_agent_web.py** | ✅ 属实（改动在 `kb.py` 的 `getattr` 健壮性，不在测试） |

### 1.3 逐条判断 Lead 特别问的两点

**(a) exemplar 的逐字比较还在吗？** —— **在**。
该测试保留了全部 5 条结构性断言（装载无错、id/writable、tool_id 顺序、approval、primitive 映射），只把两条"字段值被解析"替换为"字段不存在"。这是契约面的**等价替换**，不是放松。

**(b) `test_bad_gate_value_is_rejected` 的替代充分吗？** —— **充分，且更强**。
- 旧版：只测 **1 个非法值**（`sometimes`）⇒ 断言"非法值被拒"。
- 新版：测 **3 个值**（含历史合法的 `always`、`kb_has_sidecar`）⇒ 断言"整个字段被拒"。
- **覆盖面更宽**（1→3 值，且覆盖了旧版认为合法的值）。
- **Lead 问的"旧语义（合法值被接受）是否丢了"**：**没丢，而是正确地消失了** —— 因为 `gate` 字段整个移出 v1，**不存在"合法取值"**。旧语义的前提（字段存在）已不存在，保留它反而是错的。
- 补偿验证：`test_tools_without_gate_load_and_have_no_gate_attribute` 覆盖了"字段缺席时照常装载"这一新合法形态。

### 1.4 一个关键的独立验证（删字段 ≠ 删能力）

这是我最担心被悄悄削弱的地方——删 `gate` 会不会把**能力闸**一起删了。实测：

```
GATE_VALUES 是否还存在:  False      ← 字段枚举已删
op_available 是否还在:   True       ← 能力闸核心仍在
OP_TOOL_IDS 条目数:      17
TOOL_CATALOG 条目数:     13
plan.py:1143:  if verb in KNOWN_OPS and not active.op_available(verb):
```

⇒ **能力闸完整保留**，靠 `op_available()` + 启用位，不依赖 `gate` 字段。提案者"测试跟着机制走，不是跟着字段走"**属实**。

---

## 2. ② 判别力（亲自跑，不采信报告）

```
[1] 备份完成 sha=ffe87c1421902bb2…
[2] 已把 gate 临时改回 v1（REMOVED_TOOL_FIELDS 去掉 gate）
[3] 临时改回后：exit=1 | 1 failed, 6 passed, 51 deselected
[4] 已还原 sha=ffe87c1421902bb2… | 与备份一致=True
[5] 还原后：exit=0 | 7 passed, 51 deselected
== 判别力证明: PASS ==  (改回⇒红=True, 还原一致=True, 还原⇒绿=True)
```

**跑完后 `git status -- src/`**：仅 `ask_stream.py` 有改动（mtime **10-12**，是我在 S3 验收时就记录过的**历史遗留**，非本脚本造成）。`plugins.py` 的 `git diff` **为空** ⇒ 判别力脚本**未留残留**。

⇒ **新断言真的会红**（不是"删旧断言变绿"），且脚本自带 sha 备份/还原校验。

---

## 3. ③ 扩展工具三条硬要求（亲自跑 `check.py`）

`artifacts/agent/verify/todo/s4_sample_plugin/check.py` 独立运行：**11 条全 PASS，sha `4c0ce4b13433e790`**

| 要求 | 实测证据 | 判定 |
|---|---|---|
| **超时真杀进程** | `ext.slow`（脚本睡 30s，timeout=1s）⇒ `code=EXT_TOOL_TIMEOUT, elapsed=**1.01s**`；代码层 `subprocess.run(timeout=float(timeout_s))` + `except subprocess.TimeoutExpired`（`registry.py:348-357`） | ✅ **真杀**，不是 sleep 后返回 |
| **截断真强制** | `ext.big` 输出 512KiB ⇒ `bytes=**262198**`（= 256KiB 切片 + 标记）+ `marker=True`；代码层 `len(raw_bytes) > EXT_TOOL_OUTPUT_MAX_BYTES` ⇒ 切片 + 追加"已截断"（`:372-375`） | ✅ **真切片** |
| **前 39 把逐项等于基线** | `前39一致=True, read_only一致=True`（用 `base_names` + `base_ro` 比**名字+顺序+read_only 三项**） | ✅ 不只比数量 |
| **registry.py 零具体工具名** | grep `kb_stats` / `ext.` / `slow_tool` / `big_tool` ⇒ **0 命中**；夹具亦验证 `contains_kb_stats=False, contains_ext=False` | ✅ |

补充实测：
- 基线 39 把 ✅
- 默认关闭（声明存在未启用 ⇒ 仍 39 把）✅
- 启用后 **42 把**（`ext.kb_stats` / `ext.slow` / `ext.big`）✅
- **扩展工具真执行**：插件自己的代码算出「1 篇 md / 5 行 / 2 个标题行」✅ —— 这是"第三方真能加工具"的实证
- 5 类 removed_field 全红（`gate`/`constrain`/`tool_schema_ref`/`budget`/`lifecycle`）✅
- `GATE_VALUES` 不存在、`ToolDeclaration` 只剩 `impl`/`tool_id` ✅

---

## 4. ④ 安全边界声明（Lead 特别在意的一条）

### 4.1 设计文档 §10.3（`docs/design/agent-plugin-design.md:456-466`）

原文（标注"**原文照抄，不许软化**"）：
```
扩展工具是【用户显式安装的任意代码】，不是沙箱；
`read_only` 仅参与审批档判定，不构成执行强制；
要受 W1–W4 保护，必须走内置 propose_write 链路，而不是在扩展工具里直接写文件。
```
推论：
> 子进程完全可以自己 `open(path, "w")` 写文件 —— **那条路径在 W1 写者链之外**，
> W1（入口唯一）/ W2（读后写）/ W3（写前备份）**都不保护**它。
> ⇒ **不能**说"扩展工具不新增写者"；准确说法是"**扩展工具在 W1 写者链之外**"。

### 4.2 样例插件 README（`s4_sample_plugin/README.md:40-47`）

**与设计文档逐字一致**（同样三句 + 同样推论）。

### 4.3 代码注释也一致（`registry.py:315-317`）

```
# 扩展工具 = 用户显式安装的任意代码，不是沙箱：read_only 只是审批提示，
# 子进程可以自己写文件 —— 那条路径在 W1 写者链之外（W1/W2/W3 都不保护）。
```

### 4.4 判定

**✅ 完全达标，且比要求更硬。**

- **没有**任何"因为 read_only 所以安全"的表述；
- 恰恰相反：三处（设计文档 / 样例 README / 代码注释）都**明确写出** `read_only` **不构成执行强制**、`W1/W2/W3 都不保护`；
- 并**主动否定**了一个容易误导的说法（"不新增写者"），给出准确表述（"在 W1 写者链之外"）。

**这是本次交付里我最满意的一处**：它主动放弃了那个最诱人、也最危险的简化表述。

---

## 5. 一条须记录的口径细节（非缺陷）

**commit message 说"20 failed → 0 failed"，但 `tests/` 只有 1 个文件（28 增/11 删）被改。**

这不是矛盾：那 20 个失败来自**共享 fixture 的传染**——`KB_WRITE` 带 `gate` 后，所有引用它的测试都装载失败。实测该文件里有 **25 个测试**引用 `KB_WRITE` 或 `decl()`，其中只有 3 个函数的断言行被改，其余因 fixture 修复而自动转绿。

⇒ **"20 failed" 是现象，"3 处断言改动" 是本质**。两者不冲突，但**报告措辞容易被误读成"改了 20 处断言"**。建议后续报告写"**共享 fixture 修复使 20 个测试转绿，其中仅 3 个函数需改断言**"。

---

## 6. 已知限制（如实登记，非缺陷）

| # | 限制 | 触发条件 / 影响 |
|---|---|---|
| L1 | **扩展工具不是沙箱**（见 §4） | 已是 v1 契约明文；若未来要沙箱，需单独立项（涉及进程隔离/权限模型） |
| L2 | 未与真实第三方插件联调 | 首个真实第三方插件接入时需一次完整联调（含 `ext.` 命名、scripts 路径、超时设置） |
| L3 | `ext.` 是**本地约定**，非上游标准 | 若将来要对齐上游工具命名空间，需一次迁移（声明面已隔离在 `ext.` 前缀，迁移面可控） |
| L4 | 默认关闭依赖**库级注册表** | 无 `<kb>/.memoria/agent/capabilities.json` ⇒ 扩展工具一律不投影（安全默认，但也意味着第三方插件"装上没反应"——需文档说明如何启用） |

---

## 7. 复现

```bash
cd D:/AAA_Jupyter/Memoria
git show 7c4818fd -- tests/test_agent_plugins.py      # 3 个 hunk
python artifacts/agent/verify/todo/s4_gate_removal_discrimination.py   # 改回⇒红, 还原⇒绿
python artifacts/agent/verify/todo/s4_sample_plugin/check.py           # 11 条, sha 4c0ce4b1
python -m pytest -q tests                                              # 1462 passed
```
