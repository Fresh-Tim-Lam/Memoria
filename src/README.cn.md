[English](README.md) | 中文

# src/ — Memoria 源码

> src layout：Python 包 + 前端静态资源，安装后以 `memoria` 包导入。

## 结构

| 路径 | 职责 |
|------|------|
| `memoria/app/` | 桌面启动入口：`desktop.py`（DPI/UTF-8 兜底）、`shell/`（pywebview / pyqt6 壳）、`build.py`、`runtime.py` |
| `memoria/cli/` | 命令行入口（`memoria`） |
| `memoria/domain/` | 领域类型（Range、KP 等） |
| `memoria/range/` | snippet + line_hint 定位算法 |
| `memoria/graph/` | 图谱构建、边推导、链接审计、布局基准 |
| `memoria/presentation/` | pywebview API 桥（`api/`）、路径解析、bottle 静态服务器 |
| `memoria/services/` | 应用服务：文档加载、检索内核（lexical/embedding/rerank 融合）、导入引擎、KP 索引 |
| `memoria/storage/` | 侧车 YAML、manifest、Markdown 解析、目录扫描、原子写入 |
| `memoria/ui/static/` | 前端资源：`app/`（界面 HTML/CSS/JS）、`theme/`（memoria.css）、`vendor/`（MathJax 等第三方） |
| `memoria/__version__.py` | 版本唯一事实源 |

## 规则

- 禁止在 `src/` 放置临时/调试文件 → 归 `artifacts/`
- 版本号只允许修改 `__version__.py`，**禁止**手改 pyproject.toml 中的硬编码版本号（见 [docs/conventions/version.md](../docs/conventions/version.md)）
- 前端保持原生 JS 无框架风格
