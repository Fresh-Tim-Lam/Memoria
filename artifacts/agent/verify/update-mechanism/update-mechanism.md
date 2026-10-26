# 版本更新机制（task-180）实现与真机验证

> 人要求：「KG 设计+落地全齐+**版本更新机制** 再发」；范围 = 手动检查 + 提示 + **自动下载安装包** + **手动操作说明**（人明确不要自动替换）。
> 范围裁决（2026-10-26 23:00）：「给厕所上锁，保证发布包格式就好了」⇒ **不做数字签名**；下载后用 task-181 的 `verify_package` 校验**结构与完整性**；UI 禁止「防篡改 / 安全 / 已签名」，只写「**已校验包结构与完整性（不含数字签名）**」。

---

## 0. 结论（T-upd 1–9）
| # | 验收 | 结果 | 证据 |
|---|---|---|---|
| T-upd-1 | 出网关闭 ⇒ 检查更新**零请求** | ✅ 真机离线启动后 mock 服务日志 **0 条**；后端在调用 opener 前返回 `offline` | `update-e2e-offline.json`、`tests/test_update_mechanism.py::test_outbound_disabled_makes_zero_requests` |
| T-upd-2 | 正常联网显示当前/最新；已是最新提示 | ✅ 当前 0.4.9 / 最新 0.4.10、发布日期、说明、资产；`updateAvailable` 分支/`upToDate` 分支均实现 | `update-e2e-normal.json` `bodyChecked`；截图 `normal-update-tab.png` |
| T-upd-3 | 网络失败 fail-open | ✅ 返回 `status=error`，主功能不中断；不抛异常 | `test_network_error_is_fail_open` |
| T-upd-4 | 下载进度可见、可取消、取消无半成品 | ✅ 真机 full 8MB mock：**37.5%（3.0MB/8.0MB）** 进度；取消后下载目录 **空（无 .part）**；再次下载 lite 成功 | `downloadingUI.progress`、`cancelUI.files=[]` |
| T-upd-5 | 大小与 Release 声明一致 | ✅ 下载完成的 lite 1621B == mock release 声明；校验器另做 size 核对 | `update-e2e-normal.json` `done` + `verify_downloaded_package` size check 测试 |
| T-upd-6 | 有清单则校验并报告；无清单明确“未校验” | ✅ 包内 `release-manifest.json` → 调 `verify_package(..., check_asset_bytes=False)` → UI「已校验包结构与完整性（不含数字签名）」；无清单 → `mode=zip-only` + UI「文件完整性未被校验」 | `tests/test_update_mechanism.py` 17 例（含 tamper / 无清单 / size mismatch） |
| T-upd-7 | 手动说明四要素 | ✅ 关闭进程 / 只替换应用文件夹 / 配置在 `%LOCALAPPDATA%\Memoria\config` / lite 不要删旧 `hf/`；不自动替换 | `bodyDone`；截图 `normal-downloaded.png` |
| T-upd-8 | i18n 中英双语 | ✅ `update.*` 全键双语；`i18n_selftest` PASS | `i18n_selftest.js` |
| T-upd-9 | 隐私：只发标准 HTTP GET + UA，不送本地数据 | ✅ mock 日志：仅 `GET /latest`、`GET /asset/*`；无 Cookie/Authorization；header 仅 `accept/accept-encoding/connection/host/user-agent` | `privacy` 字段 |

三条硬要求：
1. **出网关闭零请求**：真机离线跑请求日志 0；单测注入 opener 断言 **未被调用**（不是“没处理响应”）。
2. **启动性能**：自动检查由前端 `setTimeout(6000)` 延迟触发，异步 `call`，不在窗口启动路径；真机在打开设置前已看到自动请求（`autoBeforeManual=1`）。
3. **隐私**：检查/下载只用标准 `urllib` GET + `User-Agent: Memoria/<version>`；无 Cookie/Auth/本地数据。

---

## 1. 实现
### 后端 `src/memoria/services/update.py`（新增 735 行）
- `check_for_update(manual=False)`：出网 gate（复用 `agent.llm.config.is_enabled()`）→ 24h 自动缓存 → GitHub Releases API `GET /repos/Fresh-Tim-Lam/Memoria/releases/latest` → 解析版本/日期/说明/资产 → fail-open。
- `get_update_state()`：当前版本 / 出网开关 / 自动检查配置 / 上次缓存 / 配置目录 / 下载目录（**零网络**）。
- `start_update_download(asset_name)`：只接受**检查缓存过的 release 资产**（不信任前端 URL），校验 host ∈ GitHub 域名；后台线程流式写入 Downloads/`*.part`，进度/取消状态在内存 job；完成后调校验；失败/取消删除半成品；`os.replace` 原子落盘。
- `verify_downloaded_package(...)`：优先读包内 `release-manifest.json`，调 task-181 的
  `memoria.services.verify.manifest.verify_package(path, manifest, expected_version=…, check_asset_bytes=False)`
  （下载场景只校验内容/结构，容忍重打包；GitHub asset 的 size/sha256 另行核对）；
  无清单时退化为 zip 卫生（不重复/不穿越/非空/EOCD）+ 明确“未校验文件完整性”。
- `cancel_update_download` / `get_update_download_status` / `open_download_folder`。
- 隐私：请求头只有 `User-Agent`（+ GitHub 要求的 `Accept`）；测试断言无本地字段。
- `no_window_kwargs()`：非 Windows 打开下载目录的 `subprocess.Popen` 已接 task-159 守卫（`update.py:732`）。

### RPC `src/memoria/presentation/api/ui.py`（+59 行）
新增 `get_update_state` / `check_for_update` / `start_update_download` / `get_update_download_status` /
`cancel_update_download` / `open_update_folder`，全部 try/except 包住（更新功能永不影响主功能）。
> **行号锚点处理**：RPC 块放在 `UIAPI` 类**末尾**（现有方法之后），因此文档里 `agent_*` 等行号锚点零漂移；
> 没有为了让测试绿去改文档/删测试。

### 前端
- 新增 `src/memoria/ui/static/app/js/update-settings.js`（392 行）：
  - 设置弹窗新增「更新」页签（`graph-settings.js` 动态注入模块，不改 index.html 静态结构）；
  - 当前/最新/日期/说明/资产（lite 默认推荐；full 显式选择 + 体积警告）；
  - 手动检查、下载/进度/取消、完成后的校验结果与四步手动替换说明 + 打开所在文件夹；
  - 启动后 6s 延迟静默检查（24h 限频由后端保证）+ 设置按钮小圆点 badge。
- `graph-settings.js`：`renderTabsHtml` 增加 `update` 页签（+35/−1）；按需加载 update-settings.js。
- i18n `zh-CN.js` / `en.js`：`settings.tab.update` + `update.*`（+56 行/语言）。
- 下载后的校验文案严格为「**已校验包结构与完整性（不含数字签名）**」；无清单时明说未校验；无「防篡改/安全/已签名」。

---

## 2. 真机证据（WebView2 + 真实 app.js；mock GitHub Releases 服务）
产物：`artifacts/agent/verify/update-mechanism/`
- `update-e2e-normal.json` / `.log`（正常联网）
- `update-e2e-offline.json` / `.log`（出网关闭）
- `shots/`：`normal-update-tab.png`、`normal-checked.png`、`normal-downloaded.png`、`normal-downloaded-bottom.png`、`offline-offline.png`
- `mock_update_server.py`（只读 mock；日志只记方法/路径/header 名/UA，不记正文）、`update-fixture-gen.py`（lite 1.6KB / full 8MB 带清单 zip）、`update-e2e-run.ps1`、`update-e2e-probe.mjs`

关键读数：
```
正常：auto check before manual = 1（启动后 6s 延迟请求）
      manual check → 0.4.9 → 0.4.10，资产 lite 1.6KB / full 8.0MB
      full 下载中 37.5% (3.0MB/8.0MB) → 取消 → 下载目录 []
      lite 下载完成 1621B；校验 UI = 已校验包结构与完整性（不含数字签名）
      手动步骤四要素全 true；无 auto replace；禁用措辞 []
      requests: 4 条，全 GET；路径 /latest, /asset/full, /asset/lite；无 cookie/auth
出网关闭：页面显示「出网已关闭」、检查按钮 disabled；mock 请求日志 0 条
```
> mock 服务器只在本机回环监听；生产代码固定 `api.github.com` + GitHub 资产域名。

---

## 3. 修复 Lead 指出的 7 个失败
1. `test_console_no_window`：`update.py` 打开下载目录的 `subprocess.Popen` 补 `**no_window_kwargs()`（`update.py:732`）。
2. `test_doc_anchors` 5 处：**不漂移**——把新增 RPC 块移到 `UIAPI` 类末尾，原有 `agent_*` 方法行号不变（未改文档、未删测试）。
3. `test_settings_agent_sections`：页签数 7→8（新增「更新」页签）；测试改名为 `test_tab_set_is_eight_with_update_tab` 并在 docstring 说明来源；**未删断言**。
4. （Lead 第四点）已接 `verify_package(..., check_asset_bytes=False)`，下载侧另核对 GitHub asset size/digest；UI 措辞按规定。

---

## 4. 门禁（当前工作区，全部跑）
- `pytest -q tests` → **1618 passed**（Lead 基线 1558；本次新增 17 例 update 测试，其余为库存/其他 owner 已提交测试；0 failed）
- `node --check` → 67 文件 0 失败
- `i18n_selftest` → PASS（FAIL=0）
- `team_audit` → **FAIL=0**（WARN 56 / INFO 30）
- `prompt_drift` → FAIL=0（exit 0）
- 12 剧本 → **12/12，failed 0**
- 未 commit；未动 `docs/example/**`、`Package/**`、`__version__.py`、`docs/conventions/version.md`。

## 5. 本任务改动
```
新增  src/memoria/services/update.py                         735
新增  src/memoria/ui/static/app/js/update-settings.js       392
新增  tests/test_update_mechanism.py                        286
新增  tests/test_update_ui_contract.py                       87
改    src/memoria/presentation/api/ui.py                     +59
改    src/memoria/ui/static/app/js/graph-settings.js         +35/−1
改    src/memoria/ui/static/app/i18n/{zh-CN,en}.js           +56 each
改    tests/test_settings_agent_sections.py                  +5/−4
产物  artifacts/agent/verify/update-mechanism/**（报告/探针/mock/夹具/JSON/截图/log）
```

## 6. 限制 / 待接（如实）
1. 真机验证用本地 mock Releases（保证可重复、可观察请求）；**未对真实 GitHub 线上 release 做端到端下载**（生产 URL/UA/资产分类有单测；真实 release 的清单是否随包内嵌由发布门禁 task-181 负责）。
2. 下载校验按 Lead 裁决使用 `check_asset_bytes=False`；GitHub asset 的 size/sha256 另做核对（有 digest 才比 sha）。
3. 自动检查的 24h 限频以本地 `update-state.json` 为准；手动检查不受限。
4. 不做自动替换（人明确要求）；UI 只给手动步骤。
5. **建议（Lead 提的纪律）**：`no_window_kwargs` 已第三次被漏接，静态扫描能抓但事后；建议把“新建子进程”收口到一个 `spawn(...)` helper（内部强制 no_window）或 import 时强制检查，从物理上避免再漏。
