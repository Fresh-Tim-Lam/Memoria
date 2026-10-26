# KGViz 语料重新冻结 · 说明（corpus-refreeze）

**作者**：metrics-baseline
**时间**：2026-10-26
**HEAD**：`d9341bd1`（dirty）
**产物**：`corpus-refreeze.json`（61,718 B，artifact_sha256 `87bb4081fd81f962…`）
**复跑**：`python scripts/benchmark/maintenance/kgviz_corpus_refreeze.py --json artifacts/agent/verify/debate/kgviz/corpus-refreeze.json`

---

## 0. 一句话结论

> **方案 1（从 git 复现 133/404）实测不可行** —— 干净 HEAD 导出只有 **61 节点 / 154 边**。
> **采用方案 2 + 强化**：294 文件完整 manifest（path+sha256+size）作为**唯一身份**，
> 并在正文明确标注「**不能从 git 复现**」及其依赖的工作区状态。

---

## 1. 为什么必须重新冻结（问题确认）

`docs/design/kg-ontology-v0.md §5.1` 声明的语料：

```
语料 sha = 051deb7895c86185…
文件清单 sha = e12edfad…（182 文件）
```

**这个 sha 在当前 HEAD 上无法复现**（render-perf 发现，我复核确认）：

| 检查 | 实测 |
|---|---|
| `git archive HEAD docs/example` 文件数 | **218**（不是 182）|
| AAA_Vocab 子树（HEAD）| **169** |
| 工作区 AAA_Vocab 全部文件 | **1,227** |
| 工作区 docs/example 变更 | **241 项** |
| 工作区未跟踪文件 | **407 个** |

**⇒ 辩论用的 133 节点 / 404 边语料只存在于工作区，且工作区是活的（用户 app 在跑）。**

---

## 2. 六项冻结内容（`corpus-refreeze.json` 对应字段）

### ① commit

```json
{
  "head": "d9341bd1b676787209b4a90adc1b61471138ce84",
  "head_short": "d9341bd1",
  "dirty": true,
  "worktree_changes_total": 536,
  "worktree_changes_in_kb": 241
}
```
**⇒ 明确记录 dirty=true**：这份语料**不等于** HEAD 的内容。

### ② 语料路径集合

```
primary: docs/example/AAA_Vocab
定义：所有非 docs/ 的 .md（KP 源 + 库内笔记）
    + .memoria/sidecars/**/*.yaml（链接/边声明）
    + .memoria/manifest.yaml
排除：docs/**（库说明文档，实测 48 个 md 不产节点）
      .memoria/agent/**（运行时：会话/附件/复习）
      __pycache__ / build / cache
```

### ③ 内容 manifest

```
file_count     : 294
by_ext         : {'.md': 158, '.yaml': 136}
manifest_sha256: a6866c46cab71c43…   ← 这是【语料身份】
```

**每个文件都有 `path` + `sha256` + `size`**，任何人可用它逐字节校验。

**⚠️ 必须同时看 ③b（md 分类）**：

| 类别 | 数量 | 含义 |
|---|---|---|
| `md_with_kp` | **134** | KP 源文件（1 文件 1 KP）|
| `md_without_kp` | **24** | 库内笔记/计划/题库（Writing 课程、plan、prompts、reading、question-bank）|

**⇒ 既有说法「133 个 KP 各占一个文件」只对 `md_with_kp` 成立。**
**⇒ 24 个无 KP 的 md 仍纳入 manifest**（它们影响 build/检索），但不产生节点。

**这是本轮新发现的实质事实**，与 kg-ontology v0 的表述有偏差，需在 v0 修订时登记。

### ④ 节点/边复算

```
nodes           : 134
edges           : 404
by_type         : {reference: 404}
by_origin       : {link: 402, sidecar_edge: 2}
zero_degree     : 14
max_degree      : 25
avg_degree      : 6.03
```

**复算脚本**：`ev:file:scripts/benchmark/maintenance/kgviz_corpus_refreeze.py#classify_md`
（调用 `memoria.graph.collector.collect_graph_data`）

**与辩论值的差**：

| | 辩论引用 | 本次实测 |
|---|---|---|
| 节点 | 133 | **134** |
| 边 | 404 | **404** ✓ |

**⇒ 边数完全一致；节点差 1，因工作区仍在变动（用户 app）。这与「不可复现」是同一件事。**

### ⑤ build 状态

```
post_build     : true
build_dir存在  : true
产物           : graph.json / graph_audit.json / report.json
```

**render-perf 残差 A 的反歧义，我已复核源码确认：**

```js
ev:file:src/memoria/graph/kb_build.py#L293-L298
  body_stripped, hints_stripped = strip_known_wikilink_edge_hints(body)
  if hints_stripped:
      raw = compose_markdown(body_stripped, fm)
      with open(full, "w", encoding="utf-8") as fh:   ← 真的写回源 md
          fh.write(raw)

ev:file:src/memoria/graph/kb_build.py#L312
  save_sidecar_for_md(full, kb_path, sidecar)          ← 真的写回 sidecar
```

**⇒ `kb_build` 是【破坏性迁移】，不是只读路径。**
**⇒ 论文/文档里「404 vs 454」不能解释为"两条只读路径的差异"，它含 build 的一次性迁移副作用。**

**实测佐证（clean HEAD vs 工作区文件差异）**：
```
work 文件数 1227 / clean 169
共有但内容不同 : 87 个（含 md 50、yaml 33）
只在 work     : 1063（含 73 个新增 sidecar、.memoria/build 产物）
只在 clean    : 5
```

### ⑥ 能否从 git 复现

```
can_reproduce_from_git = false
verdict = "不能从 git 复现"
```

**四条理由**：

1. **干净 HEAD 导出（61 节点 / 154 边）≠ 辩论语料（工作区 134 / 404）**
   - 这是最硬的证据：方案 1 直接实测失败
2. 工作区含 407 未跟踪文件、241 项 docs/example 变更（用户 app 实时编辑）
3. `.memoria/build` 产物存在 ⇒ 该副本已被 `kb_build` 迁移过（post-build）
4. **用户 live app（Memoria.exe）可能持续写入** ⇒ 工作区语料是「活的」，今天的 sha 明天可能变

**⇒ 它依赖什么工作区状态（必须写进设计文档）**：

```
· 241 项未提交变更（其中 md 50 处、sidecar 33 处被 kb_build 改写）
· 73 个新增 sidecar（未跟踪）
· .memoria/build 前/后状态（post-build）
· 用户 live app 的实时写入状态
```

---

## 3. 方案决策（Lead 要求的判断）

| 方案 | 可行性 | 结论 |
|---|---|---|
| **方案 1**：构造可复现语料（干净 commit + fixture 生成 133/404）| **实测不可行** | ❌ 干净 HEAD 只有 61/154，差距不是"少量补丁"能补的——需要重建 73 个 sidecar + 24 个 md，本质上是"重新造一份数据"，不是"复现" |
| **方案 2 + 强化**：完整 manifest 作为唯一身份 | 可行 | ✅ **采用** |

**⚠️ 方案 2 的固有限制（必须写进设计文档，不能藏）**：

> **别人无法重建这份语料，只能信任 manifest。**
> 这意味着：若未来有人质疑「134 节点 / 404 边」这个数字，**无法通过重新生成来验证**，
> 只能核对"当前工作区是否等于 manifest"。
> **⇒ 一旦工作区改变，该 manifest 就永久失效，且无法回滚。**

---

## 4. 给 Phase 4 / Phase 5 的建议（我的立场）

1. **设计文档必须写**：「该语料不可从 git 复现，manifest `a6866c46…` 是唯一身份」
2. **不要再用单个"语料 sha"** —— 改为三元组：`(HEAD sha, manifest_sha256, 测量时间)`
3. **辩论里的「133 节点 / 404 边」应标注为「工作区快照，非可复现基线」**
4. **建议 Phase 5 冻结时，同时冻结 manifest 文件本身**（把 corpus-refreeze.json 入库）
5. **24 个无 KP 的 md 这个事实应登记进 kg-ontology v0 修订**（它修正了「1 文件 1 KP」的表述）

---

## 5. 我做不到的 / 不确定的（M3 登记）

### unknowns

| id | 内容 | if_true_then |
|---|---|---|
| **U-C1** | 51deb78 那个旧 sha 当时对应哪份语料 | 若找到原始快照 ⇒ 可判断是否需要保留它作为历史参考 |
| **U-C2** | 用户 app 是否仍在写工作区（测量期间）| 若是 ⇒ 本 manifest 在生成时已可能不一致；需在 app 关闭时重测 |
| **U-C3** | 若把 24 个无 KP 的 md 排除，manifest 是否更稳定 | 若更稳定 ⇒ 应改为只冻结 md_with_kp（134 文件）|
| **U-C4** | build 副作用（md 50 处 / sidecar 33 处被改写）是否可逆 | 若不可逆 ⇒ 「辩论语料」永远无法回到 pre-build 状态 |

### not_doing

| 项 | 理由 |
|---|---|
| 构造 fixture 重建 133/404（方案 1 的完整尝试）| 需重建 73 sidecar + 24 md，本质是造数据不是复现；时间成本远超本轮 |
| 关闭用户 app 后重测 | 会干扰人的实时使用（纪律要求不动用户进程）|
| 改 `docs/design/kg-ontology-v0.md` | 门禁：不改 docs/，由 Lead 统一改 |
| commit | 门禁：不 commit |

---

## 6. 复跑与校验

```bash
export MEMORIA_CONFIG_DIR=$(mktemp -d)
.venv/Scripts/python.exe -X utf8 \
  scripts/benchmark/maintenance/kgviz_corpus_refreeze.py \
  --json artifacts/agent/verify/debate/kgviz/corpus-refreeze.json
```

**第三方校验 manifest**（逐文件比对）：
```python
import json, hashlib, os
d = json.load(open('artifacts/agent/verify/debate/kgviz/corpus-refreeze.json', encoding='utf-8'))
BASE = 'docs/example/AAA_Vocab'
bad = []
for it in d['③_manifest']['files']:
    p = os.path.join(BASE, it['path'])
    if not os.path.exists(p):
        bad.append(('MISSING', it['path'])); continue
    if hashlib.sha256(open(p,'rb').read()).hexdigest() != it['sha256']:
        bad.append(('CHANGED', it['path']))
print('不匹配:', bad if bad else '无（语料与 manifest 一致）')
```

### 6.1 ⚠️ 复跑一致性说明（重要，防止误判"不可复现"）

**实测复跑两次**：

| 字段 | 第 1 次 | 第 2 次 | 一致？ |
|---|---|---|---|
| `③_manifest.manifest_sha256` | `a6866c46cab71c43…` | `a6866c46cab71c43…` | ✅ **一致** |
| `④_graph_census.nodes / edges` | 134 / 404 | 134 / 404 | ✅ **一致** |
| `artifact_sha256`（整个 JSON）| `87bb4081…` | `c3d8e0fa…` | ❌ **不同** |

**原因**：JSON 内含 `refrozen_at` 时间戳字段 ⇒ 整体 sha 必然不同。

**⇒ 判定"语料是否一致"必须看 `manifest_sha256`，不是 `artifact_sha256`。**
**⇒ `artifact_sha256` 的作用是"这份冻结文件没被篡改"，不是"语料没变"。**

这与 E5（不一致必须披露）一致：我主动披露这个差异，而不是让读者误以为复跑失败。

---

## 7. 一句话给 Lead

> **方案 1 试过了，失败：干净 HEAD 只有 61/154，不是 133/404。**
> **方案 2 已交付，294 文件 manifest（sha `a6866c46…`）是语料唯一身份，并明确标注「不可从 git 复现」。**
> **另有一个新发现需登记：158 个语料 md 里只有 134 个产生 KP，24 个不产生——「1 文件 1 KP」的表述需要修正。**
