"""用户态（user state）目录解析 —— 安装目录之外的持久化落点。

## 为什么需要这个模块（task-160 根因）

用户态（`ui-settings.json`、`agent.json`）过去存在 `<install_root>/config/` ——
**在安装目录内**。后果：

- 用户**解压覆盖**新发行包 ⇒ `config/` 被整个覆盖 ⇒ 丢 LLM 配置（含 API key）、
  丢最近打开的知识库列表、丢窗口位置；
- 用户**解压到新目录** ⇒ 旧 `config/` 留在旧目录 ⇒ 同样丢。

`packaging/build.py` 的 `_RELEASE_PRESERVE_DIRS` 只保护**构建机**的 Package，
对最终用户换包完全无效（这是本问题最关键的误判点）。

⇒ 真正修法只能是**把这个目录搬出安装目录**：换包＝只替换程序文件，用户态完全不动。

## 为什么是 `%LOCALAPPDATA%` 而不是 `%APPDATA%`

`%APPDATA%`（Roaming）会被 Windows 域漫游同步到其它机器。而这里存的是：

- `ui-settings.json`：最近库**绝对路径**、窗口尺寸/位置、主题 ——
  绝对路径在另一台机器上通常不存在，漫游过去只会得到一堆失效条目；
- `agent.json`：含 API key 与出网域名名单 ——
  **凭据随漫游复制到多台机器会扩大泄露面**，且它不属于"用户偏好"。

⇒ 两者都是**机器本地的应用状态**，语义上正是 LocalAppData。
统一放一个目录也避免"两个位置各存一半、排查时找不到"。

## 放在 `util/` 而不是 `app/runtime.py` 的原因

`app/runtime.py` 是"开发态/发布态：路径解析与默认壳选择"，与 UI 壳、`install_root()` 强绑定，
且被其它并行任务改动。用户态目录是**两个存储层模块共用的纯路径决策**，
放在通用工具层可以避免 `storage` ↔ `app` 的反向耦合与写域冲突。
"""
from __future__ import annotations

import os
from pathlib import Path

#: 应用在用户目录下的子目录名（`%LOCALAPPDATA%\\Memoria\\`）
APP_DIR_NAME = "Memoria"

#: 用户态配置子目录名（`...\\Memoria\\config\\`）
CONFIG_DIR_NAME = "config"


def user_config_dir() -> Path:
    """用户态配置目录（安装目录之外）—— `ui-settings.json` / `agent.json` 的默认落点。

    解析顺序：
    1. `%LOCALAPPDATA%`（Windows 标准）
    2. `$XDG_DATA_HOME`（Linux/BSD 标准）
    3. `~/.memoria/config`（兜底；与更早的历史位置 `~/.memoria/` 区分开层级）

    **注意**：本函数**不**处理 `MEMORIA_CONFIG_DIR` / `MEMORIA_AGENT_CONFIG` 覆盖 ——
    那是调用方（存储层）的职责，因为两个模块的覆盖变量不同、语义也不同。
    """
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if local:
        return Path(local) / APP_DIR_NAME / CONFIG_DIR_NAME
    return Path.home() / ".memoria" / CONFIG_DIR_NAME
