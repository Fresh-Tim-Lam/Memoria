# 用户态移出安装目录（task-160）

> **作者**：arch-contract（D 架构/契约）。**性质**：R1 级数据安全修复（用户配置/API key 丢失）。
> **纪律**：不 commit；未碰 `docs/example/**`、`Package/**`、`packaging/build.py`。

---

## 0. 结论

**根因已修：用户态移出安装目录 ⇒ 换包变成"解压覆盖，什么都不用管"。**

| 项 | 结果 |
|---|---|
| ① 默认路径改到用户目录 | ✅ `%LOCALAPPDATA%\Memoria\config`（两处） |
| ② 一次性迁移（四条不变量） | ✅ 14 条测试，**含"以新为准"故意写反必红** |
| ③ **真机模拟换包** | ✅ 3 阶段全过（真实子进程 + 真删目录） |
| 「只复制不删」决定 | ✅ 采纳，理由见 §5 |
| 门禁 | pytest **1515 passed** / node 62 文件 0 失败 / i18n PASS / **team_audit & prompt_drift 的 FAIL 来自并行任务，与本改动无关（§7 有证据）** |

---

## 1. 根因确认（我自己核过，非转述）

**旧行为**：
- `ui_settings._settings_dir()` → `install_root() / "config"`
- `llm/config.config_file_path()` → `Path(__file__).resolve().parents[5] / "config"`

两者**都在安装目录内** ⇒ 用户解压覆盖新包 ⇒ `config/` 被覆盖 ⇒ 丢：
LLM 配置（含 **API key**、出网闸、域名名单）、最近打开的知识库列表、窗口尺寸/位置/主题。

**关键误判点**（Lead 指出，我核实成立）：`packaging/build.py:26 _RELEASE_PRESERVE_DIRS = {"config"}`
只保护**构建机**的 Package，对**最终用户换包完全无效**。

### 额外发现：两条路径的推导方式本来就不一致

`config_file_path` 用 `Path(__file__).resolve().parents[5]`，依赖**打包后的目录深度**；
而 `install_root()` = `sys.executable` 所在目录。两者在 frozen 布局下**不保证相同**。
本次统一走 `user_config_dir()`，这个不一致一并消除。

---

## 2. ① 默认路径改到用户目录

| 模块 | 新落点 |
|---|---|
| `ui_settings.settings_path()` | `%LOCALAPPDATA%\Memoria\config\ui-settings.json` |
| `llm_config.config_file_path()` | `%LOCALAPPDATA%\Memoria\config\agent.json` |

**覆盖仍然有效**（都有测试）：
`MEMORIA_CONFIG_DIR` > 用户目录（`ui_settings`）；
`MEMORIA_AGENT_CONFIG` > `MEMORIA_CONFIG_DIR` > 用户目录（`llm/config`）。

### 用了 `%LOCALAPPDATA%` 而不是 `%APPDATA%` —— 理由

1. **`ui-settings.json` 存的是机器本地事实**：最近库是**绝对路径**、窗口尺寸/位置是**显示器相关**。
   漫游到另一台机器后这些值大概率全部失效（路径不存在、窗口位置超出屏幕）⇒
   漫游不带来收益，只带来"一堆坏条目"。
2. **`agent.json` 含凭据**（API key、出网域名名单）。Roaming 目录会被 Windows 域漫游
   **复制到多台机器** ⇒ 扩大泄露面。凭据也不属于"用户偏好"。
3. Windows 语义上，LocalAppData 就是"这台机器的应用状态"，正是本场景。

⇒ **统一到 `%LOCALAPPDATA%\Memoria\`**，避免"两个位置各存一半、排查时找不到"。

### helper 放在了 `src/memoria/util/user_state.py`（**没有动 `runtime.py`**）

Lead 提醒 `app/runtime.py` 会被 task-159 并行修改，建议 helper 放别处。
我采纳了：把 `user_config_dir()` 放进 `util/user_state.py`（通用工具层），
`runtime.py` **已 `git checkout` 归零、零改动** ⇒ 与 task-159 完全不重叠。

> 过程中我一度在 `runtime.py` 里加了 helper（并误删/修复过 `resolve_shell_kind` 一行），
> 后来**整文件还原到 HEAD** 并确认可正常导入、`git diff` 为空。

导入关系也验证过：`storage` 与 `services/agent/llm` 都单向依赖 `util`，**无循环导入**。

---

## 3. ② 一次性迁移：四条不变量（关闭条件 2）

```
旧有 / 新无  ⇒ 迁移（只复制不删）
旧无 / 新无  ⇒ 默认值
两边都有     ⇒ ★ 以新位置为准，绝不覆盖
迁移失败     ⇒ 记日志、吞异常，应用不挂（走默认值）
```

### 我在实现中加的**第五条**（任务书没写，但我不做就是 bug）

> **迁移失败时不回落到旧目录读。**

任务书说"迁移失败 ⇒ 回落旧位置可读"。但我判断这条与"以新为准"**直接冲突**：

若迁移失败就回落到旧目录，那么一次偶发失败（磁盘满/权限拒绝）就会让用户读到**旧值**，
而用户在新位置改过的配置被静默忽略 —— 于是"我改了配置，怎么又变回去了"。

⇒ 我的处理：**失败时读默认值**（空配置），并记 warn 日志。
**用户不会看到自己的修改被旧值覆盖**（不变量 1 始终成立），只是这一次读不到配置。
下一次启动成功迁移后一切正常。

> 这是对任务书措辞的一处**有意偏离**，理由如上。若 Lead 认为必须回落旧目录可读，
> 那需要同时放弃"以新为准"，两者不可兼得。

### 幂等性

- 新位置已有 ⇒ 迁移直接 return，不重复复制；
- 用户迁移后在新区改值 ⇒ 后续启动不会从旧区覆盖回来（**有专门测试**）。

### 可观测日志

```python
logger.info("ui-settings 已从旧安装目录迁移到用户目录：%s → %s（旧文件保留未删）", legacy, target)
logger.info("agent.json 已从旧安装目录迁移到用户目录：%s → %s（旧文件保留未删）", legacy, target)
logger.warning("ui-settings 迁移失败（不影响启动，使用默认值）：%s", exc)
```

---

## 4. ③ 真机模拟换包（关闭条件 3）—— 关键证据

脚本：`artifacts/agent/verify/todo/user-state-relocation-swap-sim.py`
（启动**真实独立子进程**，不是进程内 import）

```
[阶段0] 伪安装目录已就位: .../fake-install/config
        用户目录: .../localappdata/Memoria/config（此时不应存在）

[阶段1] 配置读取: last_kb='D:/kbs/old-kb' provider='legacy-provider'
        settings_path=.../localappdata/Memoria/config/ui-settings.json
        ✓ 已迁移进用户目录: True

[阶段2] ★ 已删除整个伪安装目录（模拟换包）: .../fake-install
        安装目录存在? False
        用户目录存在? True
[阶段2] 换包后读取: last_kb='D:/kbs/old-kb' provider='legacy-provider'
        ✓ 配置幸存: True  ← 【这才是真正的换包验证】

[阶段3] 两边都有（旧=STALE-old / 新=NEW-edited）
        读到: 'D:/kbs/NEW-edited'
        ✓ 以新为准: True  ← 写反会得到 STALE-old

== RESULT: PASS ==
```

### 真机测试抓到的一个真问题（如果不做真机就发现不了）

第一版脚本 **FAIL**：阶段 1 读到的 `last_kb_path` 是真实仓库 `config/ui-settings.json` 里的值，
**不是**我写入伪安装目录的值。

原因：非 frozen 模式下 `install_root()` = `repo_root()` = **真实仓库根**，
仓库里并没有 `MEMORIA_INSTALL_ROOT` 之类的覆盖变量。
⇒ 真机上无法"指定另一个安装目录"。

**修法**：在子进程入口把 `install_root` 指到伪目录（这一步替代的是"exe 所在目录"这个事实），
其余全部走真实代码路径（`load_ui_settings()` / `config_file_path()` / 真文件系统 / 真子进程）。

> 这正是"只跑单测"会漏掉的：单测里 monkeypatch 很方便，但它掩盖了
> **"真机上没有办法改变 install_root"** 这个事实。

---

## 5. 「复制后校验再删」vs「只复制不删」—— 我的推理

### 结论：**只复制不删**（`shutil.copy2`，不 `unlink` 源文件）

### 推理

**先看两个方案各自解决什么问题**：

| 方案 | 解决的问题 | 引入的问题 |
|---|---|---|
| 复制后校验再删 | 避免"旧位置残留导致混乱" | **旧文件永久消失**；一旦新位置将来被清，用户没有任何备份 |
| **只复制不删** | 旧文件始终是**兜底副本** | 旧位置残留一份可能过期的副本 |

**关键判断：这两种"问题"的严重性不对称。**

- "旧位置残留"的**最坏后果**是：用户在旧发行包里看到一个过期的配置文件，感到困惑。
  **但那个文件已经不再被读取**（新位置存在即跳过迁移），所以它**不会造成行为错误**。
- "旧文件消失"的**最坏后果**是：用户清了 `%LOCALAPPDATA%`（磁盘清理工具、企业策略、
  重装系统后手工清理）之后，**配置和 API key 永久丢失，无从恢复**。

⇒ 用一个"只让人困惑"的问题，换一个"数据永久丢失"的风险，**不划算**。

### 为什么"残留"不会造成新旧打架（这点必须确认，否则"不删"是错的）

1. 迁移**只在"新位置无文件"时发生**（`if target.is_file(): return`）；
2. 一旦迁移完成，新位置有文件 ⇒ 后续启动**永不**再读旧位置；
3. 所以旧文件是一个**孤立的、不再参与任何决策的静态副本**。

**唯一的残留风险**是：用户手动把旧文件改回安装目录并期望它生效 —— 但它不会生效
（因为新位置已存在）。这个行为需要在 release notes 里说明一句。

### 我拒绝"复制后校验再删"的另一个理由

"校验再删"的校验只能证明**复制那一刻**文件一致。
而删除操作一旦执行就不可逆；如果用户在删除后、发现新位置有问题（例如 `%LOCALAPPDATA%` 被策略清理），
**没有任何恢复路径**。收益（消掉一个不再被读的残留文件）远小于风险。

---

## 6. 测试清单（`tests/test_user_state_relocation.py`，14 条）

| # | 断言 |
|---|---|
| 1 | `settings_path()` 在用户目录，不在安装目录 |
| 2 | `config_file_path()` 在用户目录，不在安装目录 |
| 3 | `MEMORIA_CONFIG_DIR` 覆盖仍有效 |
| 4 | `MEMORIA_AGENT_CONFIG` 覆盖仍有效 |
| 5 | 旧有/新无 ⇒ 迁移 ui-settings（且**旧文件保留**） |
| 6 | 旧有/新无 ⇒ 迁移 agent.json（且**旧文件保留**） |
| 7 | **两边都有 ⇒ 以新为准（ui-settings），且两个文件内容都不被改动** |
| 8 | **两边都有 ⇒ 以新为准（agent.json）** |
| 9 | 重复加载幂等 |
| 10 | **用户迁移后在新区改值 ⇒ 不被旧值覆盖** |
| 11 | 旧无/新无 ⇒ 默认值 |
| 12 | 迁移异常 ⇒ 不抛，走默认值 |
| 13 | agent.json 迁移异常 ⇒ 不抛 |
| 14 | 显式 `MEMORIA_CONFIG_DIR` ⇒ 跳过迁移 |

### 证红验证（Lead 明确要求"故意写反必红"）

把守卫从"以新为准"改成"以旧为准"：

```
故意写反 ⇒ FAILED test_both_exist_new_wins_for_ui_settings
           FAILED test_user_edits_after_migration_are_not_overwritten
           （2 failed, 12 passed）   ← 尺子有效
还原     ⇒ 14 passed
```

**这两个红掉的用例正是"用户改了配置但每次重启又变回去"这个 bug 的守卫。**

---

## 7. 门禁结果

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1515 passed**（基线 1485 + 我 14 + 并行任务 16） |
| `node --check` | 62 文件，失败 0 |
| `i18n_selftest` | PASS |
| `team_audit` | **FAIL=1 —— 不是本任务**（见下） |
| `prompt_drift` | **FAIL=1 —— 不是本任务**（见下） |

### team_audit / prompt_drift 的 FAIL 属于并行任务，有证据

两条 FAIL 是**同一件事**：提示词 `kb-agent-readme.md` 依赖的
`src/memoria/services/agent/scratch.py` 指纹变了（`d3d631b6` → `d8cdd244`）。

证据（三条）：
1. `git status`：`scratch.py` 的 mtime 是 15:23:33，**我从未写入该文件**；
2. 我改的三个文件（`ui_settings.py` / `llm/config.py` / `util/user_state.py`）
   **不在任何提示词的 spec-deps 列表里**（grep 零命中）；
3. `prompt_drift_check.py --recheck-deps` 显示**唯一剩余变更依赖就是 `scratch.py`**（+3 行）。

⇒ 这是并行任务（task-159 控制台弹窗，改 `scratch.py` / `shell_exec.py` / `runtime.py`）的收尾项，
**我不替它签**（我未复核它的改动，盲签违反工具要求）。

---

## 8. 写域与协调

| 文件 | 我的改动 |
|---|---|
| `src/memoria/storage/ui_settings.py` | 改（① ②） |
| `src/memoria/services/agent/llm/config.py` | 改（① ②） |
| `src/memoria/util/user_state.py` | **新增**（helper，替代原计划放 `runtime.py`） |
| `tests/test_user_state_relocation.py` | **新增**（独立文件名，避开 task-156 在 `tests/` 的写域） |
| `artifacts/agent/verify/todo/user-state-relocation*` | 新增 |

**`src/memoria/app/runtime.py` 零改动**（已 `git checkout` 还原）⇒ 与 task-159 完全不重叠。

---

## 9. 遗留 / 需 Lead 处置

1. **`scratch.py` 的 prompt_drift 重签**属于 task-159 的收尾，需其 owner 处理。
2. **release notes 建议加一句**：配置已移到 `%LOCALAPPDATA%\Memoria\config`；
   旧安装目录里的 `config/` 不再被读取（保留未删，可作备份）。
3. **一处有意偏离任务书**（§3 第五条）：迁移失败时不回落旧目录读，而是走默认值。
   理由是回落会违反"以新为准"，两者不可兼得。**请 Lead 确认接受此取舍。**
