# 发布包格式保证落地报告（task-181 · 缩小范围后）

> **作者**：arch-contract。
> **范围变更**：人裁决「算了不管了，给厕所上锁，**保证发布包格式**就好了」
> ⇒ 原 Ed25519 签名/公钥固定/信任链方案**全部放弃**，改为只做格式 + 完整性。

---

## 0. 结论

**纯格式+完整性方案已落地，25 个测试全绿，T-fmt-11 已证红，真实 Package 端到端验证通过。**

| 项 | 结果 |
|---|---|
| 清单生成 + A–D 校验 + 客户端入口 | ✅ |
| T-fmt-1..11 | ✅ **25 passed** |
| **T-fmt-11 证红** | ✅ 破坏 sha256 比对 ⇒ 必红（1 failed） |
| 真实 Package 端到端 | ✅ 404 文件生成清单，目录/zip 双形态 PASS |
| team_audit | ✅ **FAIL=0** |
| pytest 全量 | 7 failed —— **全部来自并行任务，与我无关**（§6 有证据） |

---

## 1. 范围回退（按人裁决执行）

**已删除**（不再需要）：
- `src/memoria/services/verify/ed25519.py`（纯 Python Ed25519）
- `src/memoria/services/verify/trusted_keys.py`（pinned 公钥）
- `scripts/agent/sign_release.py`（签名工具）
- `tests/test_release_signing.py`（T-sig-1..5 全部作废）
- `docs/design/release-signing.md`（含密码学内容的设计文档）
- `.gitignore` 的全部改动（**已 `git checkout` 归零**，无私钥了不该留守卫）

---

## 2. 交付物

| 文件 | 作用 |
|---|---|
| `src/memoria/services/verify/manifest.py` | 清单构建 + A–D 校验 + `verify_package()` 客户端入口 |
| `scripts/agent/release_manifest.py` | 生成 `release-manifest.json` |
| `scripts/agent/release_format_gate.py` | 发布门禁（A–E，`exit 1` 硬失败） |
| `docs/design/release-format.md` | 设计文档（**含诚实边界**） |
| `tests/test_release_format.py` | 25 个测试 |

**全部是新增文件**，未修改任何既有文件（`git status` 无 `M`）。

---

## 3. A–D 检查项

| 项 | 内容 |
|---|---|
| **A 结构** | 顶层恰为 required ∪ optional；必含齐全；禁止条目不得存在 |
| **B 双向** | 清单每个文件存在且 sha256/bytes 一致；**包内每个文件都被声明** |
| **C 一致** | `VERSION` == `manifest.version` == `--expect-version` |
| **D zip 卫生** | 无重复条目 / 无路径穿越 / 条目集合==清单 / 无 EOCD 尾随 |
| **E** | 任一不过 ⇒ `exit 1` |

退出码：`0` 通过 / `1` 失败 / `2` NOT_RUN / `3` 用法错误（遵守 org.md B3-e）。

---

## 4. ⚠️ 诚实边界（硬要求，已写进文档 + 代码注释）

### 保护
格式错误 / 缺文件 / 多余文件（夹带）/ zip 结构异常 / 传输损坏 / 下载不完整

### **不保护**
**有意篡改** —— 攻击者可替换包内文件**并重算清单哈希**，无签名则察觉不到。

### 表述纪律
- ✅ 正确：「**已校验包结构与完整性（不含数字签名）**」
- ❌ 禁止：「防篡改」「安全」「已签名」「不可伪造」

**核查结果**：文档与代码里所有「防篡改/安全/已签名」出现处，**全部在"禁止使用"的规则说明里**，
无宣传性表述（已 grep 验证）。

---

## 5. T-fmt-11 证红记录（Lead 明确要求）

```
故意把 sha256 比对改成 `if False and ...`
  ⇒ test_T_fmt_11_tampered_manifest_hash_detected FAILED（1 failed, 24 passed）
还原
  ⇒ 25 passed
```

⇒ 这条守卫**能证明双向校验真的在工作**，不是"写完就绿"的摆设。

---

## 6. pytest 7 个失败：全部来自并行任务（有证据）

```
FAILED test_console_no_window.py::test_all_src_subprocess_launches_use_helper
FAILED test_doc_anchors.py::[def _agent_kb / agent_session_delete / ...]（5 个）
FAILED test_settings_agent_sections.py::test_tab_set_is_seven_with_agent_and_without_plugins
```

**三条证据证明与我无关**：
1. **我的改动全是新增文件**（`git status` 里我名下无任何 `M`）；
2. `test_console_no_window` 的失败点在 `memoria/services/update.py:748` ——
   该文件是**未跟踪的新增文件**（`??`），mtime **23:09:26**，晚于我的 `manifest.py`（23:07:48），
   属 task-180（更新机制）正在写的代码；
3. `test_doc_anchors` / `test_settings_agent_sections` 依赖 `ui.py` / `i18n/*.js` / `graph-settings.js`
   等并行改动，均不在我的写域。

⇒ **我的 25 个测试单独跑全绿**（`pytest tests/test_release_format.py` ⇒ 25 passed）。

---

## 7. 实施中发现并修掉的三个真实缺陷

| # | 缺陷 | 怎么发现 | 修法 |
|---|---|---|---|
| 1 | **清单自身被算进"未声明文件"** | 用真实工具把 `Package/` 整个压成 zip ⇒ 门禁误报 `release-manifest.json` 未声明 | 自引用悖论：清单自身排除在未声明判定外 |
| 2 | **真实 Package 有 3 个运行时残留**（`.gitkeep` / `frameless-ok.txt` / `window-diag.txt`） | 在真实 Package 副本上跑门禁 | 列为**禁止项**（不放宽预期集合去容纳） |
| 3 | **VERSION 带 BOM 假报版本不一致** | Windows `Set-Content -Encoding UTF8` 写 BOM | 用 `utf-8-sig` 读 |

> 第 1、2 条**只在真实产物上跑才会暴露** —— 纯单测的人造目录不会触发。
> 其中第 2 条是有价值的实际发现：那两个 `.txt` 是**运行时诊断日志**，内含维护者本机绝对路径与窗口坐标。

---

## 8. 真实 Package 端到端结果

```
① 生成清单：404 个文件（真实 Package 副本，只读复制到 %TEMP%）
② 目录形态门禁：PASS
③ 清单登记的确切 zip：PASS
④ 内容相同但重新打包的 zip：FAIL（asset sha256 不符 —— 预期，钉住确切资产）
⑤ 往 zip 塞未声明文件：FAIL（zip 中存在未在清单声明的条目）
```

---

## 9. 一个需要 Lead 知道的语义设计

`manifest.asset.sha256` 记的是**打包后 zip 的字节哈希**。因此：
- **发布门禁**必须传 `check_asset_bytes=True`（钉住"发出去的正是这一份"）；
- **客户端只想校验内容、容忍重打包**时传 `False`（T-fmt-4 的场景）。

两种语义都实现了，且**写进了参数 docstring**（避免后人写反）。

---

## 10. 未做 / 后续

| 项 | 说明 |
|---|---|
| 接入 `release_preflight.py` | 本任务只提供门禁脚本；是否作为发版步骤的强制一环，需 Lead 接 |
| 打包工具统一 | 实测 PowerShell 与 Python 打出的 zip 都能被严格读取；建议发布统一用 Python（本项目 `packaging/` 已是） |
| 完全防篡改 | 需数字签名信任链，本次被明确放弃；若将来重提需重新评估密钥管理与 TOFU |
