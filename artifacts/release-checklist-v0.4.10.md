# Memoria v0.4.10 发版检查清单（草稿 · 不发布）

> **状态**：材料已备好，等 Lead/人授权后才执行。**本清单不改版本文件、不 commit。**
> **作者**：release-manager（2026-10-26，2026-10-27 按设计纠正更新）。
> **关联**：`artifacts/release-body-v0.4.10.md`（Release 正文）、
> `artifacts/release-cost-v0.4.10.md`（造价底稿）、
> `docs/conventions/version.md §6`（三步门禁）、`docs/conventions/release-copy.md`（宣传口径）、
> `docs/design/release-format.md`（格式门禁 A–E）、`docs/guides/operations.md §5.1`（资产命名）。

---

## 0. 版本号判断：**PATCH → `0.4.10`**（建议，最终由人定）

**结论：建议 0.4.10（PATCH），不是 MINOR。**

依据 `version.md §2` 的人 2026-10-25 硬规则：

```
MINOR 位只给「架构级 / 范式级」变更：执行载体 / 架构范式 / 外部契约形态发生根本变化
PATCH = 其余全部（能力增量 / 功能批次 / 缺陷修复 / 文档治理）
反例：0.5.0 曾把 S1–S5「agent 能力架构重构」当 MINOR 发布，被人裁决撤回
```

本版：KG 可视化 v0、检查更新/下载安装包、发布包格式保证、11 个用户可见修复、2 个 R0、
工程治理 —— **全是能力增量与修复，没有执行载体/架构范式/外部契约形态的根本变化**
⇒ 与「S1–S5 归 0.4.x」同判例，且人明确「宁可 PATCH，不要膨胀 MINOR」。

⚠️ 版本号属 **L4 人权限**；改 `src/memoria/__version__.py` 必须有人的明确授权，Lead 回报中披露。

---

## 1. 前置：版本与文档（人授权后，按 `version.md §6` 第 1–2 步）

```text
□ 人明确授权 0.4.10
□ src/memoria/__version__.py     __version__ = "0.4.10"   （唯一事实源；人权限）
□ docs/conventions/version.md §1 | 当前版本 | **0.4.10** |
□ docs/conventions/version.md §1 | 说明 | 最近已发布 = **0.4.10**（…）
      ⇒ 必须更新：`--verify-published` 的 VERSION-NOTE-PUBLISHED 严格校验它 == tag
□ docs/conventions/version.md §7 追加 0.4.10 CHANGELOG 行
□ README 徽标（如惯例需要）
□ 不得手改 Package/**、pyproject version（构建派生）
```

## 2. 构建

```powershell
packaging\build_release.cmd --no-clean
```

```text
□ 退出码 0；日志 [memoria.build] version=0.4.10
□ Package\VERSION == 0.4.10；Package\manifest.json.version == 0.4.10
□ Package\Memoria.exe.config 在位（P06 不可省）
□ 启动 Package\Memoria.exe 冒烟：窗口标题 v0.4.10，无 crash.log
```

> **注意**：`Package/config/agent.json`（含人的真实 API key）与 `ui-settings.json`
> **保留不动** —— 那是人本地测试用的（2026-10-27 人明确要求）。**打包时剥离**，见 §3。

---

## 3. 打包：从 Package 生成**干净 zip**（剥离私有配置）

### 3.1 设计纠正（2026-10-27）

- 发布物是 **zip**，不是 `Package/` 目录；`Package/` 是人的本地测试构建（可以有真实 key）。
- ⇒ 打包时把私有文件**剥离**，而不是要求人删掉自己的测试配置。
- 规则（`packaging/make_release_zip.py` 已实现）：
  ```
  顶层排除：logs/  cache/  __pycache__/  .git/
  顶层文件排除：.gitkeep  frameless-ok.txt  window-diag.txt  release-manifest.json
  config/ 只允许：config/README.txt（agent.json / ui-settings.json 一律不进 zip）
  lite 变体：再排除 hf/
  ```

### 3.2 打包命令（full + lite 各一个，清单自动生成）

```powershell
python packaging/make_release_zip.py --variant full --version 0.4.10 `
    --out artifacts/Memoria-v0.4.10-win64.zip
python packaging/make_release_zip.py --variant lite --version 0.4.10 `
    --out artifacts/Memoria-v0.4.10-win64-lite.zip
```

输出（每个 zip 同目录自动生成 `<zip 名>.manifest.json`，清单**来自 zip 条目**）：

```text
□ artifacts/Memoria-v0.4.10-win64.zip          + .manifest.json
□ artifacts/Memoria-v0.4.10-win64-lite.zip     + .manifest.json
□ 打包脚本自检 PASS（结构 / 双向哈希 / 版本 / zip 卫生 / 敏感内容）
□ zip 内无 config/agent.json、无 config/ui-settings.json、无 .gitkeep / logs/
□ zip 内 config/ 只有 README.txt
```

### 3.3 双保险：单独再跑一次格式门禁（两个 zip 都要过）

```powershell
python scripts/agent/release_format_gate.py --zip artifacts/Memoria-v0.4.10-win64.zip --expect-version 0.4.10
python scripts/agent/release_format_gate.py --zip artifacts/Memoria-v0.4.10-win64-lite.zip --expect-version 0.4.10
```

```text
□ 两个都 exit 0，输出「已校验包结构与完整性（不含数字签名）」
□ 若 FAIL：按提示修（私有配置 / key / 结构 / 哈希 / 版本）
```

> ⚠️ 门禁**只扫 zip，不扫 Package/**：扫 Package 必然命中人的测试 key（误报）。
> 敏感扫描判据：私有配置条目、`sk-…` 形态、JSON 里 `"api_key": "<长值>"`。
> 不会无差别扫字面量 `api_key` —— 应用自身设置代码引用该键名（`agent-config` 等），
> 无差别扫会误报所有版本（已实测）。

---

## 4. 三步门禁（`version.md §6` 第 0 步，缺一不可；**含 FORMAT-GATE**）

### 0a. tag push 之前（远端 tag 必须不存在）

```powershell
python scripts/agent/release_preflight.py --tag v0.4.10 --phase pre `
    --title "Memoria v0.4.10" --body-file artifacts/release-body-v0.4.10.md
```

```text
□ exit 0
□ TITLE-EXACT / BODY-BILINGUAL / COST-SECTION / VERSION-THREE-WAY PASS
□ TAG-NOT-EXISTS PASS（远端 v0.4.10 尚不存在）
□ 预期 WARN：SUPERVISOR-REVIEW（当前 WARN 级，见 §7）、DECISION-TRAIL
```

### 0b. tag push 之后、建 Release 之前

```powershell
git tag -a v0.4.10 -m "Memoria v0.4.10"
git push origin v0.4.10

python scripts/agent/release_preflight.py --tag v0.4.10 --phase post `
    --title "Memoria v0.4.10" --body-file artifacts/release-body-v0.4.10.md
```

```text
□ exit 0
□ FORMAT-GATE PASS：**两个 zip 都被校验**（full + lite，各对本 zip 清单）
□ TAG-REMOTE PASS（tag 存在且与本地 tag 对象一致）
□ 其余同 0a；ASSETS-COUNT 发布前为 SKIP（不算通过）
```

### 0c. 建 Release + 上传资产之后（**不可省**）

```powershell
python scripts/agent/release_preflight.py --tag v0.4.10 --verify-published
```

```text
□ exit 0（TAG-REMOTE / ASSETS-COUNT 此时必须 PASS，不再是 SKIP）
□ TITLE 严格 == "Memoria v0.4.10"
□ EN 在前、ZH 在后；两段主内容 >200 字符；中英造价段齐全
□ 资产 2/2 成对：Memoria-v0.4.10-win64.zip + Memoria-v0.4.10-win64-lite.zip
□ VERSION-NOTE-PUBLISHED PASS（version.md §1「说明」行 == 0.4.10）
□ PUBLISHED-ASSET：线上资产与本地 zip 清单一致（大小 + 可用时的 sha256）
```

历史教训：v0.4.7 / v0.4.8 都是「建完没有核对实际 name」；0c 不是可选步骤。

---

## 5. Release 创建与资产上传

```text
□ 标题：恰好 `Memoria v0.4.10`（无副标题；TITLE-EXACT 校验）
□ 正文：artifacts/release-body-v0.4.10.md（英文在前、中文在后，含中英造价段）
□ 资产 1：Memoria-v0.4.10-win64.zip       + 同名 .manifest.json（清单不必上传，本地留证）
□ 资产 2：Memoria-v0.4.10-win64-lite.zip  + 同名 .manifest.json
□ 两个资产都 state=uploaded；非 draft / 非 prerelease
□ 上传建议 `curl.exe -X POST -T <file>`（历史实测比 urllib 快；大文件约 1 MB/s）
```

---

## 6. 回滚方案（R1 不可逆操作前置声明）

```text
1. 删除远端 Release（DELETE /repos/Fresh-Tim-Lam/Memoria/releases/<id>，连带资产）
2. 删除远端 tag：git push origin :refs/tags/v0.4.10
3. 删除本地 tag：git tag -d v0.4.10
4. 版本号回退：src/memoria/__version__.py → 0.4.9；version.md §1/§7 回退
5. 重建 0.4.9 产物：packaging\build_release.cmd
6. 已下载用户无法召回 —— 这是发版不可逆的固有部分
```
**不移动任何历史 tag。**

---

## 7. 已知状态（不假装关闭）

| 项 | 状态 |
|---|---|
| supervisor review | **WARN** 级（角色未投入运行，0 份 artifact）；目标硬 FAIL，翻转条件见 `version.md §6` |
| 更新机制 | 真机 WebView2 + **mock** GitHub Releases 验证；真实 GitHub 发布路径未端到端跑过 |
| 格式门禁边界 | 只校验结构与完整性，**无数字签名** ⇒ 不防「替换+重算哈希」；不扫描 Package/（会误报本地测试 key） |
| KG U-KGV-2 | 基准 nodeRadius ≠ 6 时 75 %–165 % 随基准缩放；固定 6 px 仍为备选（未决） |
| 资产命名 | v0.4.7/v0.4.8 的 `-lite.zip` 属历史漂移；**本版必须 canonical `-win64-lite.zip`** |

---

## 8. 需要人确认的只剩

1. **版本号 0.4.10（PATCH）** —— 版本号属人权限，理由见 §0。
2. （已由人裁决，无需再问）`Package/config` 真实 key 保留用于本地测试；打包时剥离，zip 内只留 config/README.txt。

---

## 9. 本清单中的实测证据（2026-10-26/27）

```
① 旧 v0.4.9 已发布 lite zip（泄露版，366 条目）→ 新格式门禁 **FAIL（exit 1）**：
   ✗ zip 包含禁止的顶层条目：['.gitkeep']
   ✗ zip 的 config/ 含私有文件（只允许 config/README.txt）：['config/agent.json','config/ui-settings.json']
   ✗ zip 含私有配置条目（不得随包）：config/agent.json
   ✗ zip 含私有配置条目（不得随包）：config/ui-settings.json
   ⇒ 证明"事故版本会被新门禁拦住"（不是纸上推演）。

② 真实 Package（**保留人的真 key**）→ 新打包流程重建：
   - lite：363 条目，无 config/ 私有文件、无 .gitkeep、无 logs/，打包自检 PASS
   - full：402 条目，同上
   - 两个 clean zip 单独跑格式门禁均 **PASS（exit 0）**
   - 旧版 366/405 → 差 3 = .gitkeep + config/agent.json + config/ui-settings.json
   - Package/config/agent.json **仍在**（证明没有破坏人的本地测试工作流）

③ 人为把 config/agent.json 塞进 clean zip 副本 ⇒ 门禁 **FAIL**（pytest 固化：
   test_gate_rejects_key_injected_zip；另有 test_packer_strips_private_config_but_package_keeps_it
   同时证明"Package 保留 key / zip 剥离 / 塞回去必红"）。

④ 合成 `--phase post`（临时 repo-root = 0.4.10，artifacts 放 full+lite 两个干净 zip）：
   FORMAT-GATE PASS：已校验 2 个发布 zip 的结构与完整性（不含数字签名）
   （full 与 lite 并存不再互相冲突：各自对本 zip 的清单校验）。

⑤ 发布候选门禁（2026-10-27 实测）：`release_preflight --selftest` PASS（54 项）；
   `tests/test_release_format.py` 33 passed；`team_audit` FAIL=0。
   全仓 pytest：1642 passed / 2 failed —— 两个失败来自**并行任务**未提交的 splash/CSS 改动
   （`tests/test_checkbox_dot_style.py` 与 `tests/test_splash_animation.py`），
   与本版发布材料/打包修复无关；发布前须等该并行任务收口后重跑全绿。
```
