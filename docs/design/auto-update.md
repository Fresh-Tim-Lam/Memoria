# 自动更新（Auto Update）设计

> 状态：**已实现并发布于 0.4.15**（opt-in；`0bc17d8b`）。0.4.13/0.4.14 仍只有「检查 / 下载 / 手动替换」。
> 原则：**用户显式触发、先校验、可回滚、绝不静默替换**。
> 实现：`src/memoria/services/update_auto.py` + `resources/updater/apply_update.ps1`；E2E 证据 `artifacts/agent/verify/auto-update/`。

## 1. 为什么现在只有手动操作

不是 UI 漏做，而是旧实现刻意把「替换应用目录」留给人：

- Windows 下 `Memoria.exe` 正在运行时锁住自身和 `lib/`，进程无法替换自己的目录；
- 0.4.13 的发布包没有数字签名，也没有随 Release 上传 `release-manifest.json`（只上传两个 zip）⇒ 只能校验 zip 结构 + GitHub asset digest，不能声称“安全/防篡改”；
- 替换会改变用户机器上的应用文件，属于 R1 不可逆操作，失败必须能恢复；
- lite 包不含 `hf/`，如果直接覆盖会删掉用户的离线模型，导致离线功能损坏。

因此旧版设计成“下载后给四步手动说明”。自动更新要补的是**一个受控的替换器**，而不是把四步说明改成按钮。

## 2. 用户体验

更新页下载完成后，卡片出现两个动作：

```
[自动更新并重启]   [打开下载文件夹]
```

默认仍给手动说明的折叠区；`自动更新并重启` 是可选增强，不默认静默执行。

点击后：

1. 弹出确认框，列出：
   - 当前版本 → 目标版本
   - 将关闭 Memoria，替换应用目录（不碰知识库 / `%LOCALAPPDATA%\Memoria\config`）
   - lite 包会保留现有 `hf/`
   - 备份目录位置与回滚方式
2. 用户确认后，下载产物已经通过完整性校验 ⇒ 启动独立 updater helper，Memoria 退出。
3. 下次启动时更新页显示结果：
   - `更新成功：0.4.13 → 0.4.14`
   - 或 `更新失败，已回滚：<原因>`，并保留手动替换说明。

不提供“后台静默自动安装”。自动检查/提示可以后台，**替换必须用户确认**。

## 3. 架构

```
Memoria (pywebview)
  │ 1. verify_downloaded_package(zip, expected_sha256, expected_version)
  │ 2. write auto-update.json (job manifest)
  │ 3. spawn helper (detached)
  ▼
apply_update.ps1 (hidden PowerShell, packaged under resources/updater/)
  │ 4. wait for parent PID exit (timeout 60s)
  │ 5. re-verify sha256 + zip entry hygiene
  │ 6. extract to sibling staging dir
  │ 7. validate VERSION / Memoria.exe / lib
  │ 8. preserve hf/ for lite; preserve config/ if present
  │ 9. rename app dir -> backup; staging -> app dir
  │ 10. start new Memoria.exe
  │ 11. write update-result.json (success / fail; if fail, restore backup)
  ▼
new Memoria process
  │ 12. get_update_state / update UI reads result; offer Retry/manual
```

### 3.1 后端新增

在 `src/memoria/services/update.py`：

- `prepare_auto_update(path, *, expected_version, expected_sha256) -> dict`
  - 重新校验**最终下载文件**（不只是 `.part`）；拒绝 `ok=false`；
  - 检查 `frozen` / `os.name == "nt"`；开发态返回 `unsupported`；
  - 检查目标目录可写、盘符空间 ≥ 解压后大小 × 2；
  - 写 `%LOCALAPPDATA%\Memoria\update-job.json`（原子替换）；
  - 返回 helper 参数与确认信息。
- `start_auto_update(job_id) -> {status:"started"}`
  - 校验 job 属于当前版本/当前进程；
  - `subprocess.Popen` 启动 helper（`CREATE_NO_WINDOW | DETACHED_PROCESS`）；
  - 返回后前端调用 `window.close()`；不要在同进程里替换。
- `get_auto_update_result() -> dict | None`
  - 读 `%LOCALAPPDATA%\Memoria\update-result.json`；成功后清除/归档，避免重复提示。

在 `src/memoria/presentation/api/ui.py` 增加只读/受控 RPC：

- `prepare_auto_update(asset_name)`
- `start_auto_update(job_id)`
- `get_auto_update_result()`

### 3.2 Helper

`resources/updater/apply_update.ps1`（随包分发）：

- 只接受一个 JSON 参数文件，避免命令行引号/中文路径问题；
- 不使用 `Expand-Archive` 的默认路径覆盖行为；先解到同盘 sibling staging，失败可整目录删除；
- 使用 `Get-FileHash -Algorithm SHA256` 对照发布 asset digest；
- 使用 `zipfile` 卫生规则（路径穿越/绝对路径/重复条目）在 Python 端先做；helper 只做 hash + 结构复核；
- 替换前把旧目录 rename 为 `Memoria.backup-<oldver>-<timestamp>`；
- 失败时 rename 回去；成功保留备份（首版不自动删，提示用户手动清理）；
- lite：在新目录中移入旧 `hf/`；full：用新包 `hf/`；
- 启动新 exe 后写结果文件；helper 自身退出，不留后台进程。

### 3.3 结果文件

`%LOCALAPPDATA%\Memoria\update-result.json`：

```json
{
  "status": "success",
  "from_version": "0.4.13",
  "to_version": "0.4.14",
  "backup_dir": "C:\\...\\Memoria.backup-0.4.13-...",
  "finished_at": "2026-11-13T08:30:00+08:00"
}
```

失败时 `status:"failed"`、`rolled_back:true/false`、`reason`、`log_path`。下次启动由 `get_update_state` 附带，UI 顶部显示一次。

## 4. 安全与完整性

当前发布没有数字签名，因此自动更新必须写清楚：

- 校验的是 **GitHub Release asset digest + zip 结构/路径卫生 + 包内 VERSION**；
- 不是代码签名，不能阻止拥有 GitHub 发布权限的人替换包；
- helper 不联网、不执行包内任意脚本，只解压 + 校验 + 文件替换；
- 不允许从 UI 直接传任意路径/任意 URL 给 helper；
- `expected_sha256` 必须来自本次 `check_for_update` 的缓存，且与下载文件一致；
- 路径必须位于 Downloads 或本次 job 目录；helper 使用规范化路径并拒绝 `..`。

## 5. 失败与回滚矩阵

| 场景 | 行为 |
|---|---|
| 下载校验失败 | 不启动 helper；保留文件；显示失败原因 |
| 父进程 60s 未退出 | helper 写 failed，不触碰目录 |
| 解压失败/空间不足 | 删除 staging，旧目录不动 |
| VERSION 与目标不一致 | 删除 staging，不替换 |
| 替换 rename 失败 | 还原 backup |
| 新 exe 启动失败 | 记 failed，保留 backup，提示手动回滚 |
| 用户目录只读/Program Files | 启动前可写性检查，建议改用手动包 |
| lite 无 `hf/` | 从旧目录 move 到新目录；失败则回滚 |
| 断电/进程被杀 | 下次启动检测 `update-job.json` 的 `status=swapping`，提示备份位置并给恢复按钮 |

## 6. UI 改动

`update-settings.js`：

- 下载完成卡片增加主按钮 `自动更新并重启`；
- 点击打开确认对话框（复用 `.-modal` 家族，不新造）；
- 调用 `prepare_auto_update` → 显示摘要 → `start_auto_update`；
- 若 RPC 返回 `unsupported`（开发态/非 Windows/只读目录），降级为现有手动步骤并说明原因；
- 下次打开更新页读取 `get_auto_update_result`，显示一次性结果横幅；
- 手动步骤不删除，作为回滚/失败兜底。

i18n 新增键至少：

`update.autoInstall` / `update.autoConfirmTitle` / `update.autoConfirmBody` / `update.autoStarting` / `update.autoUnsupported` / `update.autoSuccess` / `update.autoFailed` / `update.autoRolledBack` / `update.autoBackupKept`.

## 7. 验证计划

### 单元

- `prepare_auto_update` 拒绝：非 frozen、非 Windows、sha 不匹配、版本不匹配、只读目录。
- job/result 文件原子写与幂等。
- helper 的 JSON 参数路径含空格/中文。
- lite `hf/` 保留、full 不保留旧 `hf`。
- 失败回滚（mock rename 失败）。

### 真机（独立副本，不在用户 KB 上）

用一个 `Memoria-auto-update-test/` 副本：

1. 0.4.13 lite 副本 → 下载 0.4.14 lite → 自动替换 → 启动 0.4.14；检查 VERSION、config 不变、KB 不变、`hf/` 保留。
2. full 包替换；检查旧 `hf` 被新包替换，无残留 staging。
3. 断点：校验失败、父进程拒绝退出、磁盘空间不足、只读目录；每项都不得损坏旧目录。
4. 断电模拟：`update-job.json` 恢复提示。

### 发布门禁

- 自动更新属于 R1：必须先有本设计评审、至少一次真机成功 + 一次回滚演练；
- 首版默认关闭（按钮存在但需确认），不默认后台替换；
- release notes 必须披露“无数字签名、只做 digest/结构校验”。

## 8. 实施顺序

1. 后端 `prepare_auto_update` + helper 模板 + 结果文件（先不接 UI）。
2. 真机用临时副本跑通 lite 自动替换与回滚。
3. UI 按钮/确认框/结果横幅 + i18n。
4. 全量/定向测试 + 真机矩阵。
5. 随 0.4.14 发布，notes 披露边界；保留手动路径。

## 9. 不做的部分（首版）

- 不做后台静默自动安装；
- 不做 delta 增量包；
- 不做多平台（当前只支持 Windows 便携目录）；
- 不自动删除 backup；
- 不声称代码签名/防篡改；
- 不在开发态/非 frozen 运行 helper。
