# v0.4.9 发布资产泄露真实 API key —— 事故与修复报告（task-185）

> **性质**：发布资产（GitHub Release 公开 zip）内含维护者真实 API key。
> **人的裁决**：「不怕，我以后会换 key，**不用替换**」⇒ 不执行资产替换/公关动作；
> **本任务范围缩小为纯打包修复**：保证 **v0.4.10 及以后不再犯**。
> **作者**：release-manager（2026-10-27）。**不 commit。**
> **纪律**：本报告**不复制真实 key 值**；只写"已暴露 1 个 key，建议轮换"。

---

## 0. 一句话

v0.4.9 两个公开 zip 把 `Package/config/agent.json`（内含真实 API key）打进了发布包；
**根因**是发布 zip 的打包清单包含了整个 `config/`，且当时的格式门禁校验对象是 `Package/` 目录、
没有「zip 内敏感内容」这一项。修复 = **打包时从 zip 剥离私有 config + 清单从 zip 条目生成 +
门禁只校验 zip 并扫描 `sk-`/私有配置**；已用泄露版 zip 与重建版 zip 双向实测证明门禁会红/会绿。

---

## 1. 事实与时间窗

| 项 | 内容 |
|---|---|
| 受影响版本 | **v0.4.9**（唯一受影响版本；v0.4.7 / v0.4.8 的 zip 无 config/ 条目） |
| 受影响资产 | `Memoria-v0.4.9-win64.zip`（405 条目）、`Memoria-v0.4.9-win64-lite.zip`（366 条目） |
| 泄露内容 | `config/agent.json`（真实 API key，**报告不复制值**）；另含 `config/ui-settings.json`（维护者本机设置）与 `.gitkeep` |
| 发布时间 | `published_at = 2026-10-25T14:09:33Z`；两个资产上传 `14:10:29Z / 14:10:49Z` |
| 发现时间 | 2026-10-26 23:50（Lead 实测 zip 内部结构） |
| 暴露窗口 | 约 **1 天**（自 2026-10-25 14:10Z 起，至人换 key 时止） |
| 是否进入 git 历史 | **否**：`Package/**` 在 `.gitignore` 内；钥匙只存在于构建产物与已发布 zip |
| 人的处置 | **不替换资产**（「我以后会换 key，不用替换」）⇒ 本报告不含替换/公关动作 |

> **风险定性**：任何下载过 v0.4.9 资产的人都能读取该 key。按"已泄露"处理：
> 建议人尽快轮换（这是人的决定，不在本任务执行范围）。

---

## 2. 根因（三层，缺一都不会发生）

1. **打包清单包含了整个 `config/`**：v0.4.7 / v0.4.8 的发布 zip 用显式清单打包、**不含 config/**
   （430/486 条目，`config` 条目 0）；v0.4.9 偏离为把 `Package/config/` 整目录打进去
   （366/405 条目，`config/agent.json`、`config/ui-settings.json`、`config/README.txt` 都在）。
2. **清单生成对象错位**：清单从 `Package/` 目录生成（而不是 zip 条目）⇒ 私有文件天然进入清单，
   "清单说 zip 里应该有什么"变成"Package 里有什么"，发布侧无从发现夹带。
3. **格式门禁对象错位 + 无敏感扫描**：`FORMAT-GATE` 当时校验 `Package/` 目录（人的本地测试构建），
   既不可能发现 zip 夹带，又会在人保留真实 key 时把门禁逼成"要么删 key、要么红"；
   且没有任何扫描检查 `config/agent.json` / `sk-…`。

---

## 3. 修复（设计纠正：清单与门禁的对象是 zip）

> 人的要求：「我本地需要在 Package 真实测试，真实的 key 你能发布的时候去掉吗」
> ⇒ `Package/` 保留真实 key（人的本地测试工作流）；发布物 zip 必须干净。

### 3.1 打包：从 Package 生成干净 zip（`packaging/make_release_zip.py`，新增）

```
顶层排除：logs/  cache/  __pycache__/  .git/
顶层文件排除：.gitkeep  frameless-ok.txt  window-diag.txt  release-manifest.json
config/ 只允许：config/README.txt（agent.json / ui-settings.json 一律不进 zip）
lite 变体：再排除 hf/
固定 zip 时间戳（同内容重复打包字节稳定）
```

打包后自检（失败即删除半成品 zip、exit 1）：结构 / 双向哈希 / 版本 / zip 卫生 / 敏感内容。

### 3.2 清单：从 **zip 条目**生成（`release_manifest.py --zip …`）

- `manifest.py` 新增 `build_manifest_from_zip()`：逐 zip 条目算 sha256/bytes；
- 已移除"从 Package/ 目录生成发布清单"的 CLI 用法（旧 `--package` 用法不再提供）；
- 清单与 zip 同目录：`<zip 名>.manifest.json`。

### 3.3 门禁：只校验 **zip**（`release_format_gate.py` 重写）

A–E 硬失败（任一项 ⇒ exit 1）：

| 项 | 内容 |
|---|---|
| A 结构 | zip 顶层 required/optional/forbidden；`config/` 只允许 `config/README.txt` |
| B 双向 | 清单 ↔ zip 条目集合相等；每个条目 sha256/bytes 一致 |
| C 一致 | zip `VERSION` == `manifest.version` == `--expect-version` |
| D zip 卫生 | 无重复条目 / 无路径穿越 / 无 EOCD 尾随数据 |
| E 敏感内容 | 私有配置条目（`config/agent.json`、`config/ui-settings.json`）或内容命中 `sk-…` / `"api_key": "<长值>"` ⇒ 失败（只报路径，不打印内容） |

**扫描只允许扫 zip，禁止扫 `Package/`** —— 人的测试 key 就在 Package（扫它必然误报）。

> **为什么不是无差别扫字面量 `api_key`**：应用自身设置代码大量引用该键名
> （`src/memoria/services/agent/llm/config.py` 等，会在 zip 的 `lib/**` 内出现），
> 无差别扫描会误报**所有**版本（已实测：clean zip 的 `agent-panel.js` 就含该字面量）。
> ⇒ 判据 = `sk-` 形态 + JSON 赋值形态 + 私有配置条目，三项合起来覆盖真实泄露形态。

### 3.4 接入发版流程（`release_preflight.py`）

- `FORMAT-GATE` 改为：找 `artifacts/Memoria-<tag>-win64.zip` 与 `-win64-lite.zip`，**两个都校验**
  （各自对同目录清单）；缺 zip 在 `--phase post` 直接 FAIL；
- `PUBLISHED-ASSET`（0c 审计）：改为读 zip 清单，与 GitHub 线上资产的 size + **sha256 digest**（可用时）比对；
- 不再依赖 `Package/` 目录或 `Package/release-manifest.json`。

---

## 4. 二次验证（实测，不是推论）

### 4.1 泄露版 zip → 新门禁必须红（证红）

```
python scripts/agent/release_manifest.py --zip dist-release/Memoria-v0.4.9-win64-lite.zip --version 0.4.9
python scripts/agent/release_format_gate.py --zip dist-release/Memoria-v0.4.9-win64-lite.zip --expect-version 0.4.9
```

实测输出（exit 1）：

```
== 发布包格式校验 FAIL（4 项）==
  ✗ zip 包含禁止的顶层条目：['.gitkeep']
  ✗ zip 的 config/ 含私有文件（只允许 config/README.txt）：['config/agent.json', 'config/ui-settings.json']
  ✗ zip 含私有配置条目（不得随包）：config/agent.json
  ✗ zip 含私有配置条目（不得随包）：config/ui-settings.json
```

### 4.2 真实 Package（**保留人的真 key**）→ 新流程重建 ⇒ 干净 + 门禁绿

```
python packaging/make_release_zip.py --package Package --variant lite --version 0.4.9 `
    --out dist-release/clean-v0.4.9/Memoria-v0.4.9-win64-lite.zip
python packaging/make_release_zip.py --package Package --variant full --version 0.4.9 `
    --out dist-release/clean-v0.4.9/Memoria-v0.4.9-win64.zip
```

| 产物 | 条目数 | zip 内 config/ | 私有文件 | 门禁 |
|---|---|---|---|---|
| 旧 v0.4.9 lite（泄露版） | 366 | agent.json / README / ui-settings.json | ❌ | **FAIL** |
| 旧 v0.4.9 full（泄露版） | 405 | 同上 | ❌ | **FAIL** |
| 重建 lite（clean） | **363** | 仅 README.txt | ✅ | **PASS** |
| 重建 full（clean） | **402** | 仅 README.txt | ✅ | **PASS** |

- 条目差 `-3` = `.gitkeep` + `config/agent.json` + `config/ui-settings.json`；
- `Package/config/agent.json` **仍在**（人的本地测试工作流未被破坏）；
- 附加全量扫描：两个 clean zip 内无 `sk-…` 形态（应用代码里配置键名 `api_key` 属正常引用，
  不判失败——见 §3.3 说明）。

### 4.3 人为把私有文件塞进 zip → 门禁必须红（证红二）

pytest 固化：
- `test_gate_rejects_key_injected_zip`：把含 key 的 `config/agent.json` 塞进 zip ⇒ 门禁 FAIL；
- `test_packer_strips_private_config_but_package_keeps_it`：Package 里放真 key → 正常打包 zip 干净、
  gate PASS；同时证明**打包不删除** Package 的 key；再把 key 塞回 zip ⇒ FAIL；
- `test_scan_zip_sensitive_detects_sk_key` / `..._detects_api_key_assignment` / `..._allows_plain_setting_name`；
- `test_manifest_from_zip_lists_exact_entries` / `test_gate_accepts_clean_full_and_lite_zips` /
  `test_zip_layout_rejects_private_config`。

### 4.4 发版流程回归（合成 repo-root）

`--phase post`（artifacts 放 full+lite 两个干净 zip + 清单）：

```
[PASS] FORMAT-GATE: 已校验 2 个发布 zip 的结构与完整性（不含数字签名）：
       ['Memoria-v0.4.10-win64.zip', 'Memoria-v0.4.10-win64-lite.zip']
结论：PASS-WITH-SKIPS，exit 0（仅 TAG-REMOTE/ASSETS-COUNT 因离线跳过）
```

### 4.5 门禁与测试结果（2026-10-27）

```
python -m pytest -q tests/test_release_format.py tests/test_update_mechanism.py
  ⇒ 44 passed（含新增 8 条 task-185 用例）

python scripts/agent/release_preflight.py --selftest
  ⇒ SELFTEST PASS（54 项；③ FORMAT-GATE 已改写为 zip 对象：干净 full+lite PASS /
     缺必含条目 FAIL / 未声明文件 FAIL / 私有 config+key FAIL / 缺清单 FAIL /
     无 zip post FAIL、audit SKIP / 汇总 exit 1）

python scripts/agent/team_audit.py
  ⇒ FAIL=0 WARN=56 INFO=30（机检全绿）

pytest -q tests（全仓）
  ⇒ 1642 passed / 2 failed —— 两个失败均为并行任务（未提交的 splash/CSS 改动）：
     tests/test_checkbox_dot_style.py::test_specificity_wins_without_important
     tests/test_splash_animation.py::test_reduced_motion_disables_animation_and_keeps_static_overlay
     证据：工作区 `src/memoria/ui/static/app/css/app.css` 有 +178 行未提交改动、
     `src/memoria/ui/static/app/js/splash.js` 未跟踪；与本任务写域无关，单独跑后者通过（时序相关）。
```

### 4.6 旧口径回归（确保没有把 Package 门禁的语义弄丢）

- `verify_package()` 客户端入口保留：目录形态仍可校验；zip 形态改为「清单声明的 layout
  （为空则跳过顶层检查）+ 双向哈希 + config 白名单 + 敏感扫描」，兼容旧清单的更新机制测试（11 passed）。
- 发布前置（release/pre/post）与 `--verify-published` 均抽查可跑（selftest + 合成 post PASS）。

---

## 5. 残留与边界（如实登记）

1. **`Package/config/agent.json` 仍含真实 key** —— 按人的要求保留用于本地测试；
   防泄露完全依赖"打包必剥离 + 门禁必扫描"两道。**建议人换 key 后仍不要把它移回 zip**。
2. **不替换已发布资产**（人裁决）。v0.4.9 的两个公开 zip 仍含该 key；
   风险由人通过**轮换 key** 消解（不在本任务范围）。
3. **格式门禁不含数字签名**：能抓"不小心把私有文件打进 zip"，抓不到"有意替换并重算哈希"。
   对外表述仍只能是「已校验包结构与完整性（不含数字签名）」。
4. **本报告不含真实 key 值**（纪律要求）；如需核对泄露面，按文件名与大小自查即可。
5. 新增打包脚本 `packaging/make_release_zip.py` 是**唯一**推荐的 zip 生成路径；
   手写 `Compress-Archive Package\*` 会重新引入本次事故。
