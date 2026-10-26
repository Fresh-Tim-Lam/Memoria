# 发布包格式保证（v0 · task-181）

> **作者**：arch-contract。
> **来源**：人的裁决 ——
> 「算了不管了，给厕所上锁，**保证发布包格式**就好了」
> （此前评估过 Ed25519 签名/公钥固定/信任链，被明确放弃；本方案**不含任何密码学**）

---

## 0. 一句话

> **发布时生成一份全量文件清单（每个文件的 sha256 + 字节数），发布门禁拿清单与真实产物双向对账；
> 对不上就发不出去。** 客户端可用同一套函数校验下载到的包。

**这是"给厕所上锁"**：锁住最容易出事的那道门（格式错、缺文件、多文件、zip 损坏），
**不建**高成本的密码学信任链。

---

## 1. ⚠️ 诚实边界（**必读，且禁止绕过**）

### 本方案保护

| 场景 | 怎么抓到 |
|---|---|
| 发布时格式错误（顶层缺失/多余条目） | A 结构校验 |
| 打包缺文件 | B 双向校验（清单声明的必须存在） |
| 多余文件 / 夹带 | B 双向校验（包内每个文件都必须在清单里） |
| zip 结构异常（重复条目 / 路径穿越 / EOCD 尾随） | D zip 卫生 |
| 传输损坏 / 下载不完整 | 逐文件 sha256 + 资产级 bytes/sha256 |

### 本方案**不**保护

| 不保护 | 为什么 |
|---|---|
| **有意篡改** | **攻击者可以替换包内文件并重算清单里的哈希。** 没有数字签名，客户端**察觉不到**这种替换。 |

### ⇒ 表述纪律（**硬要求**）

- ✅ 正确表述：**「已校验包结构与完整性（不含数字签名）」**
- ❌ **禁止**出现：「防篡改」「安全」「已签名」「不可伪造」

**为什么这条重要**：本项目已经多次出现"声明≠事实"的问题
（例如"99.2% 最终恒为 100% ⇒ 门禁永不触发 = 门禁不存在"）。
如果文档或 UI 让用户以为"有校验 = 防篡改"，那是**给了假安全感** ——
比不做校验更糟，因为用户会因此放弃其它防护手段（如核对官方渠道）。

---

## 2. 组成

| 文件 | 作用 |
|---|---|
| `src/memoria/services/verify/manifest.py` | 清单构建 + A–D 四类校验 + 客户端入口 `verify_package()` |
| `scripts/agent/release_manifest.py` | 生成 `release-manifest.json` |
| `scripts/agent/release_format_gate.py` | 发布门禁（任一不过 ⇒ `exit 1`） |
| `docs/design/release-format.md` | 本文档 |

### 2.1 清单格式

```json
{
  "schema": "memoria-release-manifest/v1",
  "format_version": 1,
  "version": "0.4.10",
  "built_at": "2026-10-26T...",
  "asset": { "name": "Memoria-v0.4.10-win64-lite.zip", "bytes": 123456789, "sha256": "..." },
  "layout": { "required": [...], "optional": [...], "forbidden": [...] },
  "files": [ { "path": "lib/a.py", "sha256": "...", "bytes": 1234 }, ... ]
}
```

**注意**：`asset.sha256` 记的是**打包后 zip 的字节哈希** ⇒ 重新打包（换压缩级别）会让它变化。
这是**有意的**：发布门禁必须钉住"发出去的正是这一份资产"。
客户端若只想校验内容、容忍重打包，用 `verify_package(..., check_asset_bytes=False)`。

### 2.2 规范化字节（为什么还要写死）

`canonical_bytes()` = **键排序 + 无空格 + 单个结尾 LF + UTF-8**。

**目的不是签名**（没有签名），而是**可复现 / 可 diff / 可复核**：
同一份内容在任何机器上算出同一串字节 ⇒ 两个人各自生成清单可以直接 `diff`，
review 时看到的是**真实差异**，而不是被键序、空格、CRLF 差异淹没。

（Windows 的 CRLF、`indent` 产生的空格、dict 插入顺序都会改变字节 —— 这些是纯噪声。）

---

## 3. 发布门禁检查项（A–E）

| 项 | 内容 |
|---|---|
| **A 结构** | 顶层恰为 `required ∪ optional`；必含齐全；禁止条目不得存在 |
| **B 双向** | 清单每个文件在包中存在且 sha256/bytes 一致；**包内每个文件都被声明**（无夹带） |
| **C 一致** | `VERSION` == `manifest.version` == `--expect-version`（release 标题版本） |
| **D zip 卫生** | 无同名重复条目 / 无路径穿越 / 条目集合==清单 / 无 EOCD 后尾随数据 |
| **E** | 任一条不满足 ⇒ **`exit 1`**（硬失败，不许降级 WARN） |

### 3.1 顶层预期集合（按实测定）

**必含**：`Memoria.exe`、`VERSION`、`manifest.json`、`lib/`、`resources/`、`config/`、`hf/`
**可选**：`README.txt`、`Memoria.exe.config`、`release-manifest.json`
**禁止**：`logs/`、`cache/`、`__pycache__/`、`.git/`、`.gitkeep`、`frameless-ok.txt`、`window-diag.txt`

> **依据**：在真实 `Package/`（复制到 `%TEMP%`，只读）上跑门禁，**实际抓到**后三项非预期条目 ——
> 它们是运行时诊断日志（内含本机绝对路径与窗口坐标）与占位文件。
> 处理方式是**把它们列为禁止项**，而**不是**放宽预期集合去容纳它们
> （那等于把运行残留合法化，下次还会混进发布包）。

### 3.2 退出码契约（org.md B3-e）

```
0 = 全部检查已执行且通过
1 = 执行了但有检查失败
2 = NOT_RUN（前置条件缺失，如 Package/zip 不存在 —— 不等于通过）
3 = 用法错误
```

---

## 4. 客户端入口（供 task-180 更新机制调用）

```python
from memoria.services.verify.manifest import verify_package

result = verify_package(downloaded_zip_or_dir, manifest, check_asset_bytes=True)
if not result.ok:
    # result.failures 是可直接展示给用户的具体原因列表
    ...
```

| 参数 | 目录形态 | zip 形态 |
|---|---|---|
| `path` | Package 目录 | 发布 zip |
| `check_asset_bytes` | 不适用 | `True`=钉住确切资产（下载完整性）；`False`=只校验内容（容忍重打包） |
| `expected_version` | 传则校验版本 | 同左 |

**不做的事**：不验证数字签名（没有签名），因此**不能察觉有意篡改 + 重算哈希**。

---

## 5. 验收覆盖（T-fmt-1..11）

| 用例 | 内容 | 结果 |
|---|---|---|
| T-fmt-1 | 缺必含条目 ⇒ 失败 | ✅ |
| T-fmt-2 | 多一个未声明文件 ⇒ 失败 | ✅ |
| T-fmt-3 | 版本三方不一致 ⇒ 失败 | ✅ |
| T-fmt-4 | **只重新压缩（内容不变）⇒ 通过** | ✅ （`check_asset_bytes=False`） |
| T-fmt-5 | zip 内改 1 字节 ⇒ 失败 | ✅ |
| T-fmt-6 | zip 多塞未声明文件 ⇒ 失败 | ✅ |
| T-fmt-7 | zip 删一个文件 ⇒ 失败 | ✅ |
| T-fmt-8 | 同名重复条目 ⇒ 失败 | ✅ |
| T-fmt-9 | 路径穿越 `../evil` ⇒ 失败 | ✅ |
| T-fmt-10 | EOCD 后尾随数据 ⇒ 失败 | ✅ |
| **T-fmt-11** | **【先证红】改清单 sha256 一位 ⇒ 回读必红** | ✅ **已证红** |

### 5.1 T-fmt-11 的证红记录（Lead 要求"先证红"）

```
故意破坏 sha256 比对（改为 `if False and ...`）
  ⇒ test_T_fmt_11_tampered_manifest_hash_detected FAILED（1 failed, 24 passed）
还原
  ⇒ 25 passed
```

⇒ **这个用例不是"写完就绿"的假守卫**：它能证明双向校验真的在工作。

### 5.2 真机端到端（真实 Package 副本）

```
真实 Package（复制到 %TEMP%，只读）
  ① 生成清单：404 个文件
  ② 目录形态门禁：PASS（已校验包结构与完整性（不含数字签名））
  ③ 清单登记的确切 zip：PASS
  ④ 内容相同但重新打包的 zip：FAIL（asset sha256 不符 —— 预期的，钉住确切资产）
  ⑤ 往 zip 塞未声明文件：FAIL（zip 中存在未在清单声明的条目）
```

---

## 6. 实施中发现并修掉的三个真实缺陷

| # | 缺陷 | 怎么发现的 | 修法 |
|---|---|---|---|
| 1 | **清单自身被算进"未声明文件"** | 用真实工具把 `Package/` 整个压成 zip 后门禁误报 `release-manifest.json` 未声明 | 自引用悖论：清单自身排除在"未声明"判定之外（`HASH_SKIP_TOP_FILES`） |
| 2 | **真实 Package 里有 3 个运行时残留** | 在真实 Package 副本上跑门禁 | 列为**禁止项**（不放宽预期集合） |
| 3 | **VERSION 带 BOM 时假报版本不一致** | Windows `Set-Content -Encoding UTF8` 会写 BOM | 用 `utf-8-sig` 读 |

> 第 1、2 条都是"只在真实产物上跑才会暴露"的问题 —— 纯单测人造目录不会触发。

---

## 7. 与"版本更新机制"（task-180）的关系

本模块提供 `verify_package()`，task-180 在下载完成后调用它：
- 下载不完整 / 传输损坏 ⇒ `bytes` / `sha256` 不符 ⇒ 拒绝安装；
- 包结构不对 ⇒ 拒绝安装；
- **不能**发现"渠道被换包且攻击者重算了清单"（无签名）。

---

## 8. 未做 / 后续

| 项 | 说明 |
|---|---|
| 接进 `release_preflight.py` | 本任务只提供门禁脚本；是否作为发版流程的强制一步，需 Lead/维护者接入 |
| zip 打包工具一致性 | 实测 PowerShell `CreateFromDirectory` 与 Python `zipfile` 打出的 zip 都能正常严格读取；但**发布应统一用 Python 打包**，避免工具差异（本项目 `packaging/` 已是 Python） |
| 完全防篡改 | 需要数字签名的信任链（本次被明确放弃）；若将来重提，需重新评估密钥管理与 TOFU 边界 |
