# Memoria

本地知识图谱 IDE（离线检索内核 + snippet range 导航）。

## 项目结构

每个一级目录顶部都有 `README.md` 说明其职责（AGENT 请先读 [AGENT.md](AGENT.md#4-directory导航) 获取导航）。

```
├── src/            # 源码（Python 包 + 前端静态资源）         → src/README.md
├── tests/          # 单元/集成测试（pytest）                  → tests/README.md
├── docs/           # 文档中心（规范/设计/指南/示例知识库）      → docs/README.md
├── scripts/        # 开发者工具（开发启动/基准脚本）            → scripts/README.md
├── packaging/      # 打包发布（build_release.cmd → Package/）  → packaging/README.md
├── resources/      # 应用资源（图标）                         → resources/README.md
├── benchmarks/     # 检索评估数据与结果                       → benchmarks/README.md
├── config/         # 程序配置（ui-settings.json）             → config/README.md
├── artifacts/      # 临时产物/垃圾区（gitignore）             → artifacts/README.md
├── Package/        # 构建发布产物（gitignore）                → Package/README.txt
└── app.py          # 源码运行入口
```

> 缓存目录 `build/`（PyInstaller 中间产物）与 `logs/`（调试日志）均已被 `.gitignore` 忽略，各有简短 README 说明。

## 开发

```powershell
pip install -e ".[dev]"
.\scripts\run_dev.ps1        # 开发态（pywebview 壳 + DevTools）
# 或直接运行源码入口
python app.py
pytest
```

## 当前里程碑

**M0**：snippet range、侧车 `.memoria.yaml`、KP 跳转高亮、IDE 行号视图。

详见 `docs/design/designV0.md`。
