# 本轮新增文档索引登记报告

> **任务**：task-188 ｜ **Owner**：`doc-consistency` ｜ **日期**：2026-10-27
> **结果**：本轮 6 项新增文档**已全部登记**；新登记链接 **0 死链**；`check_todo_size.py` **PASS**；`pytest 1655 passed`；`team_audit FAIL=0`。
> **改动**：4 个 README（+10/−2 行）；未动 `docs/design/kg-*.md`、`docs/conventions/**` 正文、`src/**`、`Package/**`；未 commit。

---

## 0. 一句话

新增的 6 项文档此前**在索引里完全找不到**（`docs/README.md` / `README.cn.md` 对 `marketing`、`kg-visualization`、`release-format`、`test-assertion` 均**零命中**）。现已全部登记，且**中英双语同步**。

---

## 1. ① 新增项登记结果

| # | 新增项 | 实际存在？ | 登记位置 | 说明 |
|---|---|---|---|---|
| 1 | `docs/design/kg-visualization-v0.md` | ✅ | `docs/README.md` + `README.cn.md` → `design/` 行 | KG 可视化 v0 冻结设计（FROZEN 2026-10-26） |
| 2 | `docs/design/release-format.md` | ✅ | 同上 | 发布包格式契约（`Package/` 布局与校验口径） |
| 3 | `docs/marketing/`（3 份） | ✅ | **新增一整行 `marketing/`** | claims.md（断言—证据表）/ repo-metadata.md（仓库页文案）/ tag-release-spec.md（发版 SOP） |
| 4 | `docs/todo/ideas.md` | ❌ **不存在** | **未登记**（见 §4-①） | 任务书写"若已产出"——实测**未产出** |
| 5 | `docs/conventions/test-assertion-granularity.md` | ✅ | `docs/conventions/README.md` + `README.cn.md` 索引表 | 源码字面量断言评估草案（状态：草案，未立项） |
| 6 | `docs/todo/`（目录） | ✅ | **新增一整行 `todo/`** | 台账附件目录，2026-10-26 起由 `todo.md` 索引化拆出 |

**顺带补登记**（原索引缺、且与本轮相关）：
- `design/` 行补上 **`kg-ontology-v0.md`**（见 §2-①）与上面的 `kg-visualization-v0.md`；
- 新增 `todo/` 一行——该目录 2026-10-26 就已存在于 `docs-management.md §4.1` 登记表，但 `docs/README.md` 一直没列。

---

## 2. ② 既有索引是否过期 —— 逐项核实

### ① `docs/README.md` 是否已列 `kg-ontology-v0.md`

**改前：否**（零命中）。该文件 2026-10-25 冻结（13 条裁决），是本轮 KG 工作的**核心设计文档**，却不在总索引里。
**改后：已在 `design/` 行登记**，与 `kg-visualization-v0.md` 并列。

### ② `docs/design/` 下是否有未登记的文档

**实测：61 份 `.md`，其中 46 份未在 `docs/README.md` 出现**。

| 判定 | 说明 |
|---|---|
| 这是**既有大面积欠账**，非本轮新增 | 46 份含 `agent-capabilities.md` / `agent-service-contract.md` / `dsh-agent-port.md` / `maintenance-jobs.md` 等长期存在的老文档 |
| **我没有擅自补这 46 条** | 理由：① 超出本任务「登记**本轮新增**」范围；② `docs/README.md` 的定位是**目录级索引（职责 + 关键文档）**，不是全量清单——把 61 份全塞进一行会严重破坏可读性，属于**索引结构决策**，不是登记 |
| **上报，请 Lead/registrar 裁决** | 两个选项：(A) 维持"关键文档"定位，明示它不追求全量；(B) 另建 `design/README.md` 做全量清单（**该文件当前不存在**，任务书里也提到它）。**我倾向 (B)**，但这是结构决策，我不擅自做。 |

> 46 份的完整清单可由下面的命令复跑得到（§3.3）。

### ③ `docs/todo.md` 索引区是否需要新增「想法台账」一行

**不需要**（现在）：`docs/todo/ideas.md` **不存在**，且 `docs/todo.md` 全文对 `想法` / `idea` 零命中。
按 `docs/todo/README.md` 规则 3「本目录每个 `.md` 必须被 `todo.md` 至少一个索引行覆盖」——**先有文件才登记**。登记一个不存在的文件会立刻造成死链。

⇒ **待 todo-owner 产出 `ideas.md` 后补一行**（我未改 `docs/todo.md`）。

---

## 3. ③ 相对链接死链核对

### 3.1 结论

| 范围 | 死链 |
|---|---|
| **本轮新增/改动的 10 份文档** | **0** ✅ |
| `docs/README.md` / `README.cn.md` | **各 1 条既有死链**（非本轮引入，见 §3.2） |

### 3.2 发现的既有死链（**只上报，不自行修**）

```
docs/README.md:23     → refs/README.md    (docs/refs/README.md 不存在)
docs/README.cn.md:23  → refs/README.md    (同上)
```

**核查**：
- `docs/refs/` 目录**根本不存在**（`Test-Path` 为假）；
- `git log --diff-filter=D -- docs/refs/*` **无任何删除记录** ⇒ 该目录**从未被提交过**；
- 但 `docs/conventions/docs-management.md:26` 的决策表**仍写着**「开发参考资料 → `refs/`」，且 `conventions/README.md` 里也有 `refs-system.md`（"Usage rules for the reference library (refs/)"）。

⇒ 这是**跨两份文档的既有悬空条目**（规范要求有 `refs/`，物理上没有）。**处置涉及"规范里这条该删还是该建目录"的语义判断，超出"只登记"范围，故只上报**（详见 §5-②）。

### 3.3 可复跑命令（写进报告，便于复查）

我写了一个一次性检查脚本（已删，源码附于下），或直接内联运行：

```bash
# 在仓库根执行：检查给定 markdown 的相对链接/图片是否有死链
python - <<'PY'
import re, sys
from pathlib import Path
ROOT = Path(".").resolve()
TARGETS = [
 "docs/README.md","docs/README.cn.md",
 "docs/conventions/README.md","docs/conventions/README.cn.md",
 "docs/design/kg-visualization-v0.md","docs/design/release-format.md","docs/design/kg-ontology-v0.md",
 "docs/marketing/claims.md","docs/marketing/repo-metadata.md","docs/marketing/tag-release-spec.md",
 "docs/conventions/test-assertion-granularity.md","docs/todo/README.md",
]
LINK  = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SKIP  = ("http://","https://","mailto:","#","data:","ftp://")
bad = 0
for rel in TARGETS:
    p = ROOT / rel
    if not p.is_file(): print(f"[MISS] {rel}"); continue
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        for pat in (LINK, IMAGE):
            for m in pat.finditer(line):
                t = m.group(1).strip()
                if not t or t.startswith(SKIP): continue
                f = t.split("#",1)[0].split("?",1)[0]
                if f and not (p.parent / f).exists():
                    print(f"[BAD ] {rel}:{n} → {t}"); bad += 1
print(f"\n死链 {bad} 条")
sys.exit(1 if bad else 0)
PY
```

**局限声明**：该检查只校验**文件部分**是否存在，**不校验 `#锚点` 是否真有对应标题**（那需要解析 Markdown 标题并做 slug 化，本任务未做）。

### 3.4 本轮新增文档的链接实测

`claims.md` 引用了 `kg-ontology` / `kg-visualization`（任务书特别点名）：**均解析成功**。
`tag-release-spec.md` 引用 `../../docs/conventions/version.md`：**解析成功**。
`release-format.md`：**无相对链接**（只引用代码路径）。

---

## 4. 门禁

| 项 | 结果 |
|---|---|
| `pytest -q tests` | ✅ **1655 passed / 0 failed**（基线 1645；+10 为他人新增测试，**未下降**） |
| `check_todo_size.py` | ✅ **PASS**：`todo.md = 24132 B / 320 行；无死链；WARN=0`（我未改 `todo.md`，确认未被撑爆） |
| `team_audit.py` | ✅ **FAIL=0**（`FAIL=0 WARN=56 INFO=30 合计 86 条`，"机检全绿"） |

> **一处必须说明的环境坑**：首次跑 pytest 出现 `test_release_format.py::test_packer_strips_private_config_but_package_keeps_it` **1 failed**，报
> `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'`（`packaging/make_release_zip.py:149` 的 `print` 打 `✓`）。
> **这与文档改动无关**：设 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` 后该文件 **33 passed**、全量 1655 passed。
> ⇒ 是**控制台编码环境**问题（cp1252），不是代码或文档缺陷。**建议后续跑门禁统一带上 UTF-8 环境变量**，否则会产生假红。

---

## 5. 上报项（**只上报，未自行修**，按 registrar 纪律）

### ① `docs/design/` 有 46 份文档未进总索引

见 §2-②。属既有欠账 + 索引结构决策，**需 Lead/registrar 定方向**（维持"关键文档"定位 vs 另建 `design/README.md` 全量清单）。任务书的写域里含 `docs/design/README.md`，暗示可能有这个意图，但文件当前不存在，我不擅自新建。

### ② `refs/` 悬空：规范要求它与物理现实矛盾

见 §3.2。两条死链 + `docs-management.md:26` 决策表 + `conventions/README.md` 的 `refs-system.md` 都在描述一个**从未存在过的目录**。
可能的处置（**由 owner 定**）：(A) 建 `docs/refs/README.md` 占位并说明用途；(B) 从 `docs/README.md` 表格删掉 `refs/` 行，并在 `docs-management.md` 标注该目录"暂未启用"。
我没有擅自删，因为那会改规范正文语义（`docs/conventions/**` 是明令不得动的）。

### ③ `docs/todo/ideas.md` 未产出

任务书条件项，实测未产出 ⇒ 未登记（避免造死链）。**待 todo-owner 产出后再补**（`docs/todo.md` 索引区一行）。

### ④ 写域外的必要改动（**主动披露**）

任务声明写域为 `docs/README.md` / `docs/design/README.md` / `docs/todo/README.md` / `docs/todo.md`，
但我**实际还改了 `docs/conventions/README.md` 与 `docs/conventions/README.cn.md`**（各 +2 行，仅索引表加一行）。

**理由**：`test-assertion-granularity.md` 住在 `conventions/`，而 `docs-management.md` 原则 3 要求
「新建文档后**必须同步父目录索引**」；其父目录索引正是 `conventions/README.md`。不改它，该文档依然"没人找得到"（与本任务的初衷相悖）。
**只加了索引表一行，未动任何规范正文**。若 Lead 认为越界，可回退这两处（不影响其余登记）。

---

## 6. 改动清单

| 文件 | 改动 |
|---|---|
| `docs/README.md` | `design/` 行补 3 份（kg-ontology-v0 / kg-visualization-v0 / release-format）；新增 `marketing/`、`todo/` 两行 |
| `docs/README.cn.md` | 同上（中文同步） |
| `docs/conventions/README.md` | 索引表 +1 行（test-assertion-granularity.md） |
| `docs/conventions/README.cn.md` | 同上（中文同步） |

**未改**：`docs/design/kg-*.md`（冻结）、`docs/conventions/**` 正文（仅两个 README 的索引表）、`docs/todo.md`、`src/**`、`Package/**`。
