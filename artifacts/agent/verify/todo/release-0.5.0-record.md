# 0.5.0 发版记录（2026-10-25 12:26）

## 发布物
| 项 | 值 |
|---|---|
| tag | `v0.5.0` → `c7c5fb39`（annotated，远端已核对一致） |
| Release | https://github.com/Fresh-Tim-Lam/Memoria/releases/tag/v0.5.0 |
| 资产 1 | `Memoria-v0.5.0-win64-lite.zip` 35.3 MB（不含 `hf/`） |
| 资产 2 | `Memoria-v0.5.0-win64.zip` 1179.5 MB（内置模型，离线可用） |
| 状态 | published（非 draft / 非 prerelease），2/2 资产 `state=uploaded` |

## 版本号变更（L4 披露）
`src/memoria/__version__.py`：`0.4.6` → `0.5.0`（单行）。
版本文件属人权限；本次由 Lead 修改，依据：本轮指令「发版保留版本号文件的人权限边界，
**人已在本指令中明确授权发版**」。`pyproject.toml` / `Package/**` 未手改。
`Package/VERSION` 与 `manifest.json` 由构建脚本从 `__version__.py` 派生。

## 真机冒烟
`
构建：packaging\build_release.cmd → exit 0，日志 [memoria.build] version=0.5.0
产物：Package\Memoria.exe  6.1MB  mtime 12:18:23
启动：Package\Memoria.exe → 窗口标题「Memoria v0.5.0」，无 crash.log
`
**这是「打包产物真能跑」的实测，不是推断。**

## zip 内容验证（脚本逐项读 zip）
`
完整包：400 文件，含 exe + Memoria.exe.config + hf/ + resources/agent-capabilities/
lite  ：361 文件，无 hf/
两者  ：config/ 条目 = 0（P06 教训：不打开发机 ui-settings）
       VERSION 内容 = 0.5.0
`

## 构建前处置（如实记录）
构建前 `Package\Memoria.exe` 正被运行中的 app 锁住（pid 28476，从 `Package\` 启动）。
`CloseMainWindow()` 6 秒后未退出 ⇒ **强制结束**（sidecar 实时落盘，无未保存数据风险）。
构建完成后已**重启**该 app（新版本），窗口标题可见 `Memoria v0.5.0`。

## 门禁
见 `artifacts/agent/verify/todo/release-0.5.0-gates.md`：
pytest 1464 passed / 0 failed；11/11 验收夹具 PASS；12 交互剧本**未跑**（本版零前端改动，登记为缺口）。

## 回滚方案（R1 不可逆操作的前置声明）
`
1. 删除远端 Release：DELETE /repos/Fresh-Tim-Lam/Memoria/releases/<id>
2. 删除远端 tag：git push origin :refs/tags/v0.5.0
3. 删除本地 tag：git tag -d v0.5.0
4. 版本号回退：src/memoria/__version__.py → 0.4.6
5. 重建 0.4.6 产物：packaging\build_release.cmd
6. 已下载用户无法召回 —— 这是发版不可逆的固有部分，故只发已过门禁的版本
`
**不移动任何历史 tag**（v0.4.6 及更早保持原位）。

## 遗留债务（已知、如实登记、不假装关闭）
1. 完成率未证（可完成性 12/12，完成率缺；B 臂轮数 +50%）
2. 12 个交互剧本未跑
3. 未与真实 MCP 客户端对拍
4. 扩展工具不是沙箱（文档三处声明）
5. 锚点守卫覆盖不完整（task-126）