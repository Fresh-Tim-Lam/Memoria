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


# ── 用户态合并策略（task-179：按 mtime 较新者胜，per-key）─────────────────────


def file_mtime(path: Path) -> float | None:
    """文件的 mtime（秒）；读取失败/不存在 ⇒ `None`（**不要用 0 代替** —— 0 会假装"很旧"）。"""
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def merge_by_mtime(
    *,
    current: dict,
    incoming: dict,
    current_mtime: float | None,
    incoming_mtime: float | None,
) -> tuple[dict, list[str]]:
    """**per-key** 合并两份配置，同键冲突时取 mtime 较新的一方。

    ## 为什么是 per-key 而不是 per-file（实测依据）

    真实两份 `agent.json` 的**键集合不同**：

    ```
    安装目录 : api_key, base_url, model, status_refresh_ms, timeout_s
    用户态   : api_key, base_url, enabled, model, script_use_bundled,
               status_refresh_ms, timeout_s, transcript_mode
    ```

    ⇒ 若按**整文件覆盖**，安装目录那份更新就会把用户态独有的
    `enabled` / `script_use_bundled` / `transcript_mode` **全部抹掉** —— 比原缺陷更糟。

    ## 三条规则

    1. **只在一侧存在的键** ⇒ 一律保留（并集）。这是"不丢东西"的底线。
    2. **两侧都有且值相同** ⇒ 保留原值（**不因 mtime 不同而改写**，避免无谓写盘/churn）。
    3. **两侧都有但值不同** ⇒ 取 **mtime 较新**的一侧；mtime 相等或不可判 ⇒ **保守保留 current**
       （不冒险用可能更旧的值覆盖用户当前的设置）。

    ## 返回

    `(merged, adopted_keys)` —— `adopted_keys` 是**从 incoming 采纳的键名**，
    供调用方写可观测日志（"采纳了哪边、几项"）。
    """
    merged = dict(current)
    adopted: list[str] = []

    # incoming 更新 ⇒ 冲突键取 incoming；否则保持 current（含相等/不可判）
    incoming_newer = (
        incoming_mtime is not None
        and current_mtime is not None
        and incoming_mtime > current_mtime
    )

    all_keys = list(current.keys()) + [k for k in incoming.keys() if k not in current]
    for key in all_keys:
        in_cur = key in current
        in_inc = key in incoming
        if in_cur and not in_inc:
            continue  # 规则 1：用户态独有 ⇒ 保留
        if in_inc and not in_cur:
            merged[key] = incoming[key]  # 规则 1：补入
            adopted.append(key)
            continue
        if current[key] == incoming[key]:
            continue  # 规则 2：值相同 ⇒ 不动
        if incoming_newer:
            merged[key] = incoming[key]  # 规则 3：incoming 更新
            adopted.append(key)
        # 否则保守保留 current

    return merged, adopted
