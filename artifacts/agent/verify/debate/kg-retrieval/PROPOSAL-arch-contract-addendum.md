# Phase 1 补件：关掉 F-A + 测掉 U-2（A 方 · arch-contract）

> 沿用 `PROPOSAL-arch-contract.md` 的证据体系。**Phase 1 独立性不变**：未读他人提案、未与他人讨论。
> 数据全部来自**现成真实样本**（真库会话日志 / 真库正文），未自造数据。

---

## ① 关掉 F-A：agent **确实在读 KP**（F-A 不成立）

### 1.1 我原本的 Falsifier

> **F-A**：若能证明 agent **实际从不读 KP range**（只读整篇），
> 则锚点缺陷降级为"用户体验问题"而非"检索问题"。

### 1.2 实测（真实会话，非造数）

样本：`D:\AAA_Courses\数字通信原理\.memoria\agent\sessions\session-20261027T011706Z-0cb419b6.jsonl`
**567 行事件 / 105 次 `tool/call`**（Lead 说 87 次；日志此后有增长，以实际 105 为准）。
脚本：`fa_does_agent_read_kp.py`，产出 `fa-does-agent-read-kp.json`。

**工具调用全量分布**（`ev:bench:fa-does-agent-read-kp`）：

| 工具 | 次数 | 依赖 KP 锚点？ |
|---|---|---|
| `read_document` | **37** | ❌ 按文件+offset/limit 读 |
| `grep` | **28** | ❌ 按正则读 |
| `snippet` | 11 | ❌ 按行/查询读片段 |
| `search_kb` | 7 | ❌ 命中后**用 `_line_hint` 定位**（间接依赖，见 §1.4） |
| `propose_write` | 7 | — |
| **`read_kp`** | **6** | ✅ **直接依赖 KP range** |
| `outline` | 3 | ❌ |
| `kb_overview` | 2 | — |
| `validate_kb` | 2 | — |
| `skill` / `pwsh` | 各 1 | — |

⇒ **`read_kp` 被调用 6 次，F-A 不成立。**

### 1.3 那 6 次 `read_kp` 实际返回了什么（这是关键）

5 个不同 KP（`aliasing` 调了 2 次）。每次返回都**自带行范围**：

```
uniform-quantization（均匀量化）@ 教材/03_第3章_模拟信号的数字编码.md:439-604
aliasing（混叠现象与低通抽样定理）@ ...:90-200
pcm（脉冲编码调制）@ ...:1214-1218
ch3-summary（本章小结）@ ...:2844-2846
bandpass-sampling（带通抽样定理）@ ...:202-293
```

⇒ **agent 拿到的正是「文件 + 行区间」——就是 R4 里那个会漂的锚点。**
**锚点一旦漂移，这 6 次调用会静默返回错误章节，而 agent 不会知道。**

### 1.4 还有一条我原提案漏掉的间接依赖：`search_kb`

`ev:file:src/memoria/services/agent/tools/kb.py#L272-L275`：
```python
info = by_file.setdefault(rel, _kp_map_for_file(kb_path, rel)).get(kp_id, {})
line = info.get("line")          # ← 来自 _line_hint(kp)
```
⇒ `search_kb` 每次命中后，都用 `_line_hint` 给 agent 报位置。
本会话 `search_kb` 调了 **7 次** ⇒ **锚点缺陷的影响面 = 6（read_kp）+ 7（search_kb）= 13 次调用**，
占**全部读取类调用（92 次）的 14.1%**。

### 1.5 结论：时序关系（Lead 要求写清）

```
现在：agent 已经在用 KP 锚点（13/92 次调用 = 14.1%）
      ↓
      这些调用【当前恰好是对的】——因为该库 sidecar 尚未漂移
      ↓
一旦文档被编辑（前插/删行/改标题） ⇒ 18.8% 的 KP 会静默锚错（r4-wrongpin 实测）
      ↓
⇒ 锚点缺陷【当前就是正确性问题】，不是"将来才影响"
⇒ 而且它更危险：现在"看起来能工作"，所以没人会去修
```

**⇒ 我据此把严重度定级：P0（不是 P2）。**
理由：不是"将来做 KP 检索才需要"，而是**现在 14.1% 的读取路径已经落在它上面**，
且失效形态是**静默错**（`ok=True`）——这正是本项目反复在治的"看起来有实际没有"。

**F-A 正式关闭：证伪失败（agent 确实读 KP）。**

---

## ② U-2 测掉了：块级 hash 完全可放进同步路径

### 2.1 实测（真库全量，`ev:bench:u2-block-hash`）

库：`D:\AAA_Courses\数字通信原理`，**59 个 md / 5.46 MB**。
块切分：ATX heading 起新块 + 空行分段落 + fenced code 整体一块。
hash 口径（等同提案 §3.3）：`sha256(LF归一化 + 剥行尾空白 + 结尾 \n)`。

| 场景 | 耗时 |
|---|---|
| **全量**（59 文件 / **30,986 块**） | **90.0 ms** |
| 单文件 **min** | 0.12 ms |
| 单文件 **median** | **0.89 ms** |
| 单文件 **mean** | 1.39 ms |
| 单文件 **p90** | 2.80 ms |
| 单文件 **max**（407KB 的 `08_第8章_差错控制编码.md`，1889 块） | **4.39 ms** |

> **复跑抖动说明**（避免复核时以为数字对不上）：上表是单次实测；复跑实测
> 全量 **88.4–90.0 ms**、median **0.89–0.91 ms**、max **4.39–4.63 ms**。
> 抖动 ~5%，属计时噪声，**不影响判据结论**（4.6ms 距 50ms 仍有 10 倍余量）。

### 2.2 对判据

Lead 给的判据：**单文件 < 50ms ⇒ 可同步；> 500ms ⇒ 必须异步。**

```
单文件最坏 4.39 ms  <<  50 ms      ⇒ ✅ 可放进"保存后"的同步路径（余量 11 倍）
即使全量 90 ms     <<  500 ms      ⇒ 连全量都能做，页加载时重建也不卡
```

### 2.3 增量场景（改 1 个文件）

```
典型（中位文件）：0.89 ms
最坏（最大 407KB 章）：4.39 ms
```

⇒ **保存一篇文档后，只重算该文件的块 hash，成本 < 5ms**，用户完全感知不到。

### 2.4 顺带关掉 F-B 的一半

**F-B**：若"任何编辑都让所有块 hash 变化"，则块锚退化为文件锚 ⇒ 方案无增益。
**实测反驳**：块切分产出 **30,986 块 / 59 文件 ≈ 525 块/文件**（不是 1）。
⇒ **块粒度是真实的、足够细**，编辑一处只会影响少数块。
（"编辑后实际变化块数"的分布仍待测，见残余未知 U-6。）

---

## ③ 这两条补件对提案的修正

| 项 | 原提案 | 补件后 |
|---|---|---|
| **F-A 状态** | 待验证（决定 P0/P2） | ✅ **已关闭（证伪失败）** ⇒ 严重度 **P0** |
| **U-2 状态** | 未测 | ✅ **已测**：全量 90ms / 单文件 4.4ms ⇒ 可同步 |
| 影响面 | 原只提 `read_kp` | **补：`search_kb` 的 `_line_hint` 也是受害路径** ⇒ 13/92 = 14.1% |
| 新增未知 | — | **U-6**：单次编辑实际导致多少块 hash 变化（F-B 的另一半） |

---

## ④ 残余未知（更新）

| # | 不确定 | 怎么定 |
|---|---|---|
| **U-6** | 一次真实编辑平均改变多少块的 hash | 可用 `document.py` 保存 diff 实测；若平均 >50% 块变化，则块锚价值下降 |
| U-3 | KP range 重叠在真库有多少 | 待测 |
| U-4 | 块切分与 task-156（引用块内列表）冲突 | 需读 task-155/156 结论 |
| U-5 | `document.py#L373-L473` 已有的"保存后重新锚定"是否与块锚重复劳动 | 需读该段全逻辑 |

---

## ⑤ 交付物

| 文件 | 内容 |
|---|---|
| `fa_does_agent_read_kp.py` / `fa-does-agent-read-kp.json` | F-A 实测（工具分布 + 6 次 read_kp 实证） |
| `u2_block_hash_bench.py` / `u2-block-hash-bench.json` | U-2 实测（全量/单文件耗时 + 块数） |
| 本文件 | 补件说明 |

**复现**：
```powershell
python artifacts/agent/verify/debate/kg-retrieval/fa_does_agent_read_kp.py
python artifacts/agent/verify/debate/kg-retrieval/u2_block_hash_bench.py
```
