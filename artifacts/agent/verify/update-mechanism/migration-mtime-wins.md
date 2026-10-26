# 用户态迁移策略修复：按 mtime 较新者胜（task-179）

> **作者**：arch-contract。**性质**：真缺陷修复（升级会丢用户设置），版本更新机制的前置条件。
> **纪律**：不 commit；`Package/**` 只读；不删任何用户文件。

---

## 0. 结论

**根因已修，且比"改成 mtime 优先"多做了一步——必须 per-key 合并，不能 per-file 覆盖。**

| 项 | 结果 |
|---|---|
| T-mig-1..7 | ✅ **12 passed**（含 per-key 3 条） |
| 证红 | ✅ 改前 **5 failed**，含 T-mig-1/1b/5 与两条 per-key |
| T-mig-6 真机 | ✅ **PASS**（真实 Package + 真实用户态副本） |
| pytest | **1570 passed**（基线 1547） |
| team_audit | **FAIL=0** |

---

## 1. 根因（我核实了 Lead 的实测）

| 文件 | Package（安装目录） | 用户态 | 谁更新 |
|---|---|---|---|
| `agent.json` | **10-26 18:13** | 09-24 13:59 | **Package** |
| `ui-settings.json` | **10-26 19:41** | 10-25 01:28 | **Package** |

旧实现（`ui_settings.py` / `llm/config.py` 各一处）：
```python
if target.is_file():
    return    # ← 用户态有文件就直接返回，完全不看 mtime
```
⇒ 用户当前跑的是 task-160 之前的旧构建（一直在写 `install_root()/config`），
新构建首次启动时用户态已存在 ⇒ **Package 侧 18:13 那次更新被静默丢弃**。

---

## 2. ★ 关键设计判断：**必须 per-key，不能 per-file**（我实测后定）

**实测两份真实 `agent.json` 的键集合不同**：

```
Package : api_key, base_url, model, status_refresh_ms, timeout_s                    （5 键）
用户态  : api_key, base_url, enabled, model, script_use_bundled,
          status_refresh_ms, timeout_s, transcript_mode                            （8 键）
```

| 键 | Package | 用户态 | 处理 |
|---|---|---|---|
| `api_key` | **sk-18eb75f7**（新） | sk-7ac67dbd（旧） | 取 Package（mtime 新） |
| `enabled` | **缺** | True | **保留用户态** |
| `script_use_bundled` | **缺** | True | **保留用户态** |
| `transcript_mode` | **缺** | normal | **保留用户态** |

⇒ **若按 per-file 整文件覆盖**：Package 更新就盖过去 ⇒ **用户态独有的 3 个键全部丢失**
——**这比原缺陷更糟**（原缺陷只丢 api_key 更新，整文件覆盖会丢 3 个键 + 用户显式关掉的开关）。

⇒ **必须 per-key 合并**。这是本任务最关键的设计判断，也是 Lead 让我"你判断并说明理由"的地方。

---

## 3. 实现

### 3.1 共享合并函数（`src/memoria/util/user_state.py`）

```python
def merge_by_mtime(*, current, incoming, current_mtime, incoming_mtime) -> (dict, list[str])
```

**三条规则**：
1. **只在一侧存在的键** ⇒ 一律保留（并集）——"不丢东西"的底线；
2. **两侧都有且值相同** ⇒ 保留原值，**不因 mtime 不同而改写**（避免无谓写盘/churn）；
3. **两侧都有但值不同** ⇒ 取 **mtime 较新**一方；**mtime 相等或不可判 ⇒ 保守保留 current**。

返回 `(merged, adopted_keys)` —— `adopted_keys` 供写可观测日志（"采纳了哪边、几项"）。

`file_mtime()` 读失败返回 **`None` 而非 `0`** ——`0` 会假装"很旧"，导致错误地采纳另一侧。

### 3.2 两处消费方

| 文件 | 改动 |
|---|---|
| `src/memoria/storage/ui_settings.py` | `_migrate_from_install_dir()` 改为 per-key 合并 + 原子写 |
| `src/memoria/services/agent/llm/config.py` | `_migrate_agent_config_from_install_dir()` 同上 |

**保持不变**（task-160 既定约束）：
- **只复制不删**（Package 侧文件永不删除、内容不改动）；
- 显式 `MEMORIA_CONFIG_DIR` / `MEMORIA_AGENT_CONFIG` ⇒ 跳过迁移；
- 任何异常只记 warn，**不影响启动**。

### 3.3 可观测

```python
logger.info("agent.json 合并完成：从旧安装目录采纳 %d 项 %s（旧文件保留未删）", len(adopted), adopted)
logger.warning("agent.json 合并跳过（解析失败，保留用户态现有内容）：%s", exc)
```

---

## 4. 证红 → 证绿（Lead 要求"先证红"）

### 4.1 改前：**5 failed**（当前实现下必红）

```
FAILED test_T_mig_1_package_newer_wins_ui_settings
FAILED test_T_mig_1b_package_newer_wins_agent_config
FAILED test_T_mig_5_idempotent_across_three_starts
FAILED test_per_key_merge_preserves_user_only_keys
FAILED test_per_key_merge_pkg_only_keys_are_added
```

### 4.2 改后：**12 passed**

覆盖 T-mig-1 / 1b / 2 / 3 / 3b / 4 / 5 / 7 + per-key 3 条 + 显式目录不回退。

---

## 5. T-mig-6 真机（**我按 Lead 给的场景真跑**）

脚本：`artifacts/agent/verify/update-mechanism/migration-tmig6-realmachine.py`
**安全边界**：`Package/config/**` 与真实用户态**只读复制**，全部操作在 `%TEMP%` 内，结束即删。

```
=== 升级前（真实数据，只读）===
  Package : mtime=1793009588  api_key=sk-18eb75f7430…
  用户态  : mtime=1790229595  api_key=sk-7ac67dbd7a8…
  Package 更新: True
  用户态独有键: ['enabled', 'script_use_bundled', 'transcript_mode']

=== 升级后（模拟结果）===
  用户态 api_key: sk-7ac67dbd7a8… → sk-18eb75f7430…
  用户态键数: 8 → 8
  [OK] 采纳 Package 侧更新的 api_key（18:13 那次改动不丢）
  [OK] 用户态独有键全部保留
  [OK] Package 独有的键补入
  [OK] Package 侧文件未被删除
== RESULT: PASS ==
```

⇒ **用真实数据证明：18:13 那次 api_key 更新不再丢失，且用户态独有的 3 个键一个不少。**

---

## 6. 一处需要 Lead 知道的契约变更（旧测试被改写）

`tests/test_user_state_relocation.py` 里有 2 个测试断言的是 **task-160 的旧契约**
（"两边都有 ⇒ 以用户态为准"）。task-179 把契约改成 "mtime 较新者胜"，
这 2 个测试因此红。

**我没有删它们，而是按新契约改写**：
- `test_both_exist_new_wins_for_*` → `test_both_exist_equal_mtime_keeps_user_*`
- 改法是**显式把两边 mtime 设成相等**，让它们继续守"**mtime 相等 ⇒ 保守保留用户态**"这一分支。

⇒ 新契约的"较新者胜"由 T-mig-1/2 覆盖；"相等 ⇒ 保守"由改写后的用例覆盖。**两个分支都有守卫，没有丢覆盖。**

---

## 7. 遗留 / 建议

1. **UI 可观测**：目前只写 logger。若希望用户能感知"设置已合并"，需要前端在启动时读该日志或由 RPC 返回合并摘要（v1）。
2. **mtime 的语义局限**（登记为未知）：若用户在旧构建里改了设置后**系统时钟回拨**，mtime 可能反而更旧 ⇒ 会保守保留用户态（丢失那次改动）。概率低，但**mtime 不是内容级证据**。
3. 完成本任务后，**task-181（签名协议）** 可继续。
