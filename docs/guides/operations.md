# 开发与发布操作手册（Operations）

> **用途**：Memoria 本地开发、验证、构建、发布的**可执行操作指引**——从零环境到发布包的全流程命令与注意事项。
> **目标读者**：维护者 / AI Agent（执行开发或发布任务时按本手册操作）。
> **关联文档**：[collaboration.md](./collaboration.md)（协作规则）；[version.md](../conventions/version.md)（版本规范）；[logging.md](../conventions/logging.md)（日志规范）；[packaging/README.md](../../packaging/README.md)（打包详情）。

---

## 1. 环境准备

```powershell
# 要求：Windows 10/11、Python ≥ 3.11
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"       # 开发安装（含 pytest）
pip install pyinstaller        # 仅构建发布包需要
```

可选依赖（按需）：
```powershell
pip install -e ".[semantic]"   # sentence-transformers 语义检索
pip install -e ".[search]"     # pypinyin 拼音搜索
```

## 2. 开发态运行

```powershell
.\scripts\run_dev.ps1          # 推荐：源码 + pywebview 壳 + DevTools + 无边框（MEMORIA_MODE=dev）
python app.py                  # 直接源码运行（同上，但需自行设环境变量）
```

`run_dev.ps1` 内置环境：`MEMORIA_MODE=dev`、`MEMORIA_SHELL=pywebview`、`MEMORIA_FRAMELESS=1`、`MEMORIA_DEBUG=1`。

切壳（备选 pyqt6）：
```powershell
$env:MEMORIA_SHELL="pyqt6"; .\scripts\run_dev.ps1
```

## 3. 验证

```powershell
pytest                         # 单元测试（tests/）
```

### 3.1 浏览器复现 harness（前端交互验证）

交互性前端改动（图片、编辑、图谱、导入）用 harness 在真实浏览器复现：

```powershell
python docs\example\rich-content-test\_harness.py            # 富内容样例库（KB=rich-content-test）
python docs\example\import-test\_harness_import.py --fresh    # 导入模块（KB=docs/example/empty3，--fresh 复位空库）
```

- harness 机制：bottle 服务真实前端 + UIAPI over `/rpc` + 注入 pywebview 桥。
- **注意**：harness 注入的桥对裸字符串 RPC 响应解析失败，需 `r.text()` + 单次解析的容错代理；且 api 需**异步延迟挂载**（先空壳再派发 `pywebviewready`，约 1.2s），否则晚于 app.js 加载的模块 init 会被静默跳过。
- 导入 harness 附加「测试反馈机制」（供 browseragent/脚本回读执行证据）：
  | 端点 | 作用 |
  |---|---|
  | `POST /harness/pick` | 队列 canned「文件选择」结果（`{type:dir\|files, value}`），替代原生对话框 |
  | `POST /harness/mark` | 测试步骤/断言标记（step/kind/ok/note） |
  | `POST /harness/console` | 前端 console/onerror/unhandledrejection 上报 |
  | `GET /harness/state` | 实时状态 + RPC/console 环形缓冲 |
  | `GET /harness/report` | 汇总结构化报告（meta+marks+rpc+console+错误统计），落 `<KB>/.memoria/harness/` |
- 验证原则：每阶段独立可交互验证（见 [image-asset-dev-plan.md](../design/image-asset-dev-plan.md) 的分阶段方法），完成即记录验证结果。

### 3.2 前端调试日志

| 前缀 | 含义 |
|------|------|
| `[SYNC]` | 预览同步（视图切换/内容收集/渲染） |
| `[img-rewrite]` | 图片路径重写（原 URL → API URL） |
| `[img-debug]` / `[img-attrs]` | 图片加载诊断 / 属性解析 |
| `[STATIC]` | 静态服务（KB 根初始化/文件请求/路径逃逸） |

## 4. 版本升级

1. 只改 [`src/memoria/__version__.py`](../../src/memoria/__version__.py)（唯一事实源，pyproject dynamic 读取）。
2. 构建时 `packaging/build.py` 自动读取并写入 manifest/VERSION/README。

```powershell
# 验证三处跟随：
python -c "import importlib; m=importlib.util.spec_from_file_location('v','src/memoria/__version__.py'); mod=importlib.util.module_from_spec(m); m.loader.exec_module(mod); print(mod.__version__)"
```

## 5. 构建发布包

```powershell
.\packaging\build_release.cmd            # 完整构建（PyInstaller --clean）
.\packaging\build_release.cmd --no-clean # 增量构建（更快）
```

- 产物：仓库根 `Package/`（`Memoria.exe` + `lib/` + `resources/` + `config/` + `VERSION` + `manifest.json` + `README.txt`）。
- 整包 zip/拷贝分发即可。
- **铁律**：`Package/lib/` 与 `src/` 代码必须同版本——每次改前端/后端后发布前重新构建；发布态验证跑 `.\.\packaging\run_release.cmd`。
- **随包资源**：`Package/resources/` 由 `packaging/build.py` `_stage_runtime_resources()` 登记表收集（icons/agent-prompts/examples/example-boonie），构建结束前自动自检必带文件（含 `resources/agent-prompts/organize.zh-CN.md`）。新增随包资源按 [packaging/README.md](../../packaging/README.md)「随包资源登记」四步维护；构建后自检：
  ```powershell
  python -c "from pathlib import Path; p=Path('Package/resources'); print((p/'agent-prompts'/'organize.zh-CN.md').is_file(), (p/'icons'/'Memoria.ico').is_file())"
  ```
- 构建中间产物 `packaging/build/`、`packaging/dist/` 已被 gitignore，勿提交。

## 6. 发布态运行

```powershell
.\packaging\run_release.cmd   # 运行 Package\Memoria.exe（发布态，pywebview 壳）
```

## 7. 日志与临时产物

- 调试日志按 [logging.md](../conventions/logging.md) 归置（默认 `artifacts/`，已被 gitignore）。
- `docs/tmp/` 只放少量诊断记录；一次性的批量产物进 `artifacts/`。

## 8. 发布里程碑收尾

发布成功（`build_release.cmd` 跑通）后按 [docs-management.md](../conventions/docs-management.md) §4.3 做 docs 定期整理：归位散文档、登记新文档、清理临时产物。
