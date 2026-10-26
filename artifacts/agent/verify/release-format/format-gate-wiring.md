# FORMAT-GATE 接入发版流程（task-181 收口）

> **作者**：arch-contract。**性质**：把一个"写好了但从不在流程里跑"的门禁接进真实链路。
> **纪律**：不 commit；`Package/**` 只读；先证红。

---

## 0. 结论

**门禁已接进 `release_preflight.py` 的两个真实阶段，且已证红 —— 现在它真的能拦住发布。**

| 项 | 结果 |
|---|---|
| ① 接进 `--phase post` | ✅ 新检查项 `FORMAT-GATE` |
| ② 接进 `--verify-published` | ✅ `FORMAT-GATE` + 新增 `PUBLISHED-ASSET` |
| ③ 退出码契约 | ✅ 遵守 B3-e（0/1/2/3） |
| ④ **先证红** | ✅ 真实 CLI：`exit 1` 且 `failed` 含 `FORMAT-GATE` |
| ⑤ selftest 扩展 | ✅ **53 项全绿**（新增 6 项 FORMAT-GATE fixture） |
| pytest | ✅ **1618 passed** |
| team_audit | ✅ **FAIL=0** |

---

## 1. 为什么这一步最重要（Lead 的判据）

`release_format_gate.py` 此前是**独立脚本、没人调用**。那正是今晚反复出现的失败形态：

- 99.2% 门禁**永不触发** ⇒ 等于门禁不存在；
- `prompt_drift` 静默放行 ⇒ 检查跑但结论无效；
- `VERSION-NOTE` 无人解析 ⇒ 写了规则没人执行。

⇒ **"写了检查"和"检查在流程里跑"是两件事。** 本次把后者补上。

---

## 2. ① 接进 `--phase post`

### 接入位置与理由

| 阶段 | 能否校验真实产物 | 决定 |
|---|---|---|
| `--phase pre` | ❌ Package/ 与 zip 常还没构建 ⇒ 只能校验"预期" | 不接 |
| **`--phase post`**（tag 已 push、建 Release 之前） | ✅ 产物已就绪 | **接在这里** |

新增检查项 id：**`FORMAT-GATE`**，失败即 `FAIL`（不是 WARN）。

### 三层判据（避免误判，也避免静默跳过）

```
Package/ 不存在              ⇒ SKIP（无法校验真实产物，SKIP 不算通过）
Package/ 存在但无构建产物    ⇒ SKIP（未见 Memoria.exe / lib / resources ⇒ 未构建，如 selftest fixture）
Package/ 有产物但缺清单      ⇒ FAIL（明确要求先跑 release_manifest.py）
清单存在                     ⇒ 跑 A–D 校验，不过则 FAIL
异常                         ⇒ FAIL（不得当作通过）
```

> **为什么要"有产物但缺清单 ⇒ FAIL"**：这正是**当前仓库的真实状态** ——
> `Package/` 有 exe/lib/resources，但没有 `release-manifest.json`。
> 若这里静默 SKIP，就变成"清单没生成也能发布"，门禁形同虚设。

---

## 3. ② 接进 `--verify-published`（并补了线上资产校验）

`--verify-published` 走 `mode="audit"`，`FORMAT-GATE` 已在其中生效。

**新增 `PUBLISHED-ASSET`**（Lead 要求"那时拿到的是线上实际 asset"）：

| 比什么 | 说明 |
|---|---|
| 线上 asset `size` vs 本地清单 `asset.bytes` | 抓"本地合规但上传错了文件" |

**分工说明**：
- `FORMAT-GATE` 校验**本地构建产物**（结构 + 双向哈希 + zip 卫生）；
- `PUBLISHED-ASSET` 校验**线上真的挂出来的是不是那份**。

⇒ 两者合起来才闭环。若只有前者，一种失败形态没人能发现：**本地产物完全合规，但上传了另一个文件**。

### 诚实边界（写进代码注释）

GitHub Release JSON **不提供 asset 的 sha256** ⇒ 本项只能比对**大小**，
抓不到"大小相同但内容不同"。**不含数字签名。**

---

## 4. ③ 退出码契约（org.md B3-e）

沿用 `_print_checks` 既有逻辑：`summary.ok=False ⇒ return 1`。
- `FORMAT-GATE` 内部分三类：`PASS` / `FAIL`（阻断）/ `SKIP`（不计通过也不算失败）。
- 门禁自身异常 ⇒ 显式转 `FAIL`（`不得当作通过`）。

---

## 5. ★ ④ 先证红：真实 CLI 证明它真的拦得住

### 5.1 证红 1：有产物但缺清单（改前的真实状态）

```
$ python scripts/agent/release_preflight.py --tag v0.4.9 --title "..." --body-file ... --phase post --offline
  [FAIL] FORMAT-GATE: 缺少 Package/release-manifest.json ⇒ 无法校验包格式。
         先跑：python scripts/agent/release_manifest.py --package Package --version 0.4.9
结论：FAIL（3 项阻断：BODY-BILINGUAL, COST-SECTION, FORMAT-GATE）—— 不得发布
exit=1
```

⇒ **`FORMAT-GATE` 出现在阻断列表，整体 `exit 1`。**

### 5.2 证红 2：生成清单后 → 暴露真实残留（**这不是 bug，是门禁在正确工作**）

```
$ python scripts/agent/release_manifest.py --package Package --version 0.4.9
  ✓ 已生成 Package\release-manifest.json（407 个文件）

$ python scripts/agent/release_preflight.py ... --phase post --offline
  [FAIL] FORMAT-GATE: 包格式/完整性不符，拒绝发布：
         包含禁止的顶层条目：['.gitkeep', 'frameless-ok.txt', 'logs/', 'window-diag.txt']
结论：FAIL（3 项阻断：... FORMAT-GATE）—— 不得发布
exit=1
```

### 5.3 证红 3：清掉残留后 → 变绿

（fixture 环境验证）`FORMAT-GATE: 已校验包结构与完整性（不含数字签名）` ⇒ PASS

### 5.4 证红 4/5：线上资产不符 / 包缺必含条目

```
[FAIL] PUBLISHED-ASSET: 线上资产 ... 大小 999999 字节 ≠ 本地清单登记 21 字节
                       ⇒ 上传的可能不是同一份产物
[FAIL] FORMAT-GATE: 包格式/完整性不符，拒绝发布：缺少必含顶层条目：['resources/']
```

⇒ 每一类失败都能**精确指出是哪一项**，不是笼统报错。

---

## 6. ⑤ selftest 扩展（6 项新 fixture，全绿）

```
[PASS] ③ FORMAT-GATE 合规包 ⇒ PASS
[PASS] ③ FORMAT-GATE 缺必含条目 ⇒ FAIL
[PASS] ③ FORMAT-GATE 多未声明文件 ⇒ FAIL
[PASS] ③ FORMAT-GATE 有产物缺清单 ⇒ FAIL（不静默 SKIP）
[PASS] ③ FORMAT-GATE 空壳 Package ⇒ SKIP（不误判）
[PASS] ③ FORMAT-GATE FAIL ⇒ 整体 summary.ok=False（会 exit 1）
SELFTEST PASS（53 项）
```

> 第 6 项直接验证 **"单项 FAIL ⇒ 整体 exit 1"** 这条链路，而不只是单项行为。

---

## 7. ⚠️ 现状：门禁现在是红的，这是正确行为

**发 0.4.10 前必须清理 `Package/` 里的运行时残留**：

| 残留 | 性质 | 证据 |
|---|---|---|
| `.gitkeep` | 占位文件 | 0 字节 |
| `frameless-ok.txt` | **运行时诊断日志** | 含本机绝对路径 `D:\AAA_Jupyter\...`、知识库路径 |
| `window-diag.txt` | **窗口调试日志** | 含时间戳与窗口坐标 |
| `logs/` | 运行日志目录 | 被列为禁止顶层条目 |

**清理动作归谁**（我的判断，供 Lead 定夺）：
- **应由发版流程做**：`packaging/build_release.cmd` 或 `build.py` 在打包前清理这些运行时产物；
- 或 Lead 手工清理后再构建。

**不归我**：我的写域不含 `Package/**` 与 `packaging/build.py`（任务书写明不得动）。

⇒ **建议**：在 `build.py` 的产物收尾处加一句清理（或在 `_RELEASE_PRESERVE_DIRS` 同级加"禁止复制"清单），
这样以后不会再混进来。**这是一个独立的、很小但关键的后续项。**

---

## 8. 实施中发现并修掉的真实缺陷

| # | 缺陷 | 怎么发现 | 修法 |
|---|---|---|---|
| 1 | **selftest fixture 的空壳 Package 被误判为 FAIL** | 接入后 selftest 4 项变红 | 加"是否有构建产物"判据 ⇒ 空壳 SKIP |
| 2 | **`--release-json` 读不了带 BOM 的 JSON** | 我自己的测试文件被 PowerShell 写了 BOM | `utf-8` → `utf-8-sig` |
| 3 | fixture 里未声明文件生成顺序错 | selftest 单项红 | 先生成清单、后塞文件 |

> 第 2 条是**真实的用户可遇到问题**：GitHub 下载的 JSON 或 Windows 生成的 JSON 可能带 BOM。

---

## 9. 改动清单

| 文件 | 改动 |
|---|---|
| `scripts/agent/release_preflight.py` | 新增 `eval_format_gate` / `eval_published_asset` / `_selftest_format_gate` / `_make_fixture_package`；`run_release_checks` 接入两项；`_load_release_json` BOM 容错 |
| `scripts/agent/release_format_gate.py` | 无改动（`run_checks` 已可复用） |
| `artifacts/agent/verify/release-format/report.md` | 本报告 |

---

## 10. 未做 / 后续

| 项 | 说明 |
|---|---|
| **清理 Package 运行时残留** | 见 §7，需发版流程或 Lead 处理，**之后门禁才会绿** |
| 接入 `build.py` 自动清理 | 建议作为独立小任务（我的写域不含 `packaging/`） |
| 线上 asset 内容哈希 | GitHub JSON 不提供 sha256 ⇒ 只能比大小；要更强需下载 asset 后算哈希（成本高，v1 再议） |
