# SOURCE-LICENSE — pilot 语料来源与许可（单标注草案）

> **状态**：`single_annotator_draft`；IAA 未做；0.5 保持 HOLD。本文件是 pilot 语料包的**来源/许可唯一记录**。
> **结论**：源 = **OpenStax《Introduction to Business》(1e) Chapter 1**，许可 **CC BY 4.0（SPDX `CC-BY-4.0`）**，**Tier A 可发布**（C0 C2 / R-C0-3）。
> **核验日期**：2026-11-05（Asia/Shanghai）。**核验方式**：`curl` HTTP GET（浏览器 UA，不执行页面脚本），记录 HTTP 状态码 + HTML `<title>` + 原始字节 sha256；机器记录见 `artifacts/corpus/pilot/source/fetch-log.json`。

## 1. 选源与 Tier 判定

| 项 | 值 |
|---|---|
| 书名 | Introduction to Business |
| 版本 | 1e（`https://openstax.org/books/introduction-business/pages/1-introduction`；该页标题 "Ch. 1 Introduction - Introduction to Business \| OpenStax"） |
| 出版方 | OpenStax（Rice University 非营利项目） |
| 章节 | Chapter 1: Understanding Economic Systems and Business（1.1–1.8 + Key Terms + Summary of Learning Outcomes） |
| 许可 | **CC BY 4.0**（Creative Commons Attribution 4.0 International） |
| SPDX | `CC-BY-4.0` |
| Tier | **A 可发布**（CC BY，允许再分发/改编，需署名 + 许可声明 + 修改标注） |
| 语言 | en（英文；中文检索/偏移未在本 pilot 验证，见 §7） |
| 正文快照 | `artifacts/corpus/pilot/source/chapter.txt`（sha256 `51b51337…`，126,372 chars） |
| 原始快照 | `artifacts/corpus/pilot/source/raw/*.html`（11 个正文页，逐字节保存） |
| 机器许可证据 | `artifacts/corpus/pilot/source/license-evidence.json`、`fetch-log.json` |

**许可声明原文（book preface，HTTP 200 + 标题已核验）**：

> "Introduction to Business is licensed under a Creative Commons Attribution 4.0 International (CC BY) license, which means that you can distribute, remix, and build upon the content, as long as you provide attribution to OpenStax and its content contributors."
>
> — `https://openstax.org/books/introduction-business/pages/preface`（title: *Preface - Introduction to Business | OpenStax*；HTTP 200；本地快照 `source/raw/preface.html`）

**图表许可原文（同一 preface）**：

> "In Introduction to Business, art contains attribution to its title, creator or rights holder, host platform, and license within the caption. Because the art is openly licensed, anyone may reuse the art as long as they provide the same attribution to its original source."

处理：**本 pilot 发布包不重分发任何图片文件**；`chapter.txt` 只保留 caption/credit 文本（属 CC BY 4.0 正文的一部分）。正文中可见的逐图许可示例：`Exhibit 1.1 … (Credit: Marco Verch /flickr / Attribution 2.0 Generic (CC BY 2.0))`、`Exhibit 1.4 … (Attribution: Copyright Rice University, OpenStax, under CC-BY 4.0 license)`。若未来发布包含图片的版本，必须逐图保留 caption 中的 credit + license（可能混有 CC BY 2.0 等第三方许可）。

## 2. 正文页核验表（11 页；全部 HTTP 200 + 标题）

方法：`curl -A "<browser UA>" -o raw/<page>.html https://openstax.org/books/introduction-business/pages/<page>`；状态码由 curl `%{http_code}` 记录；标题由 HTML `<title>` 正则提取；`verified_at` 为本地落盘时间（见 `fetch-log.json`）。

| # | page | HTTP | 标题（截断） | sha256（前 16） |
|---|---|---|---|---|
| 1 | `1-introduction` | 200 | Ch. 1 Introduction - Introduction to Business \| OpenStax | `b1413b6cf01c253a` |
| 2 | `1-1-the-nature-of-business` | 200 | 1.1 The Nature of Business - Introduction to Business \| OpenStax | `f27d95cb36f43bb6` |
| 3 | `1-2-understanding-the-business-environment` | 200 | 1.2 Understanding the Business Environment - Introduction to Business \| OpenStax | `1ff2682cb34edbd7` |
| 4 | `1-3-how-business-and-economics-work` | 200 | 1.3 How Business and Economics Work - Introduction to Business \| OpenStax | `2ff657e37a96ede4` |
| 5 | `1-4-macroeconomics-the-big-picture` | 200 | 1.4 Macroeconomics: The Big Picture - Introduction to Business \| OpenStax | `376308e5d3597937` |
| 6 | `1-5-achieving-macroeconomic-goals` | 200 | 1.5 Achieving Macroeconomic Goals - Introduction to Business \| OpenStax | `90f68cd12bbe9ef6` |
| 7 | `1-6-microeconomics-zeroing-in-on-businesses-and-consumers` | 200 | 1.6 Microeconomics: Zeroing in on Businesses and Consumers - Introduction to Business \| OpenStax | `bbb20b2b5443bb46` |
| 8 | `1-7-competing-in-a-free-market` | 200 | 1.7 Competing in a Free Market - Introduction to Business \| OpenStax | `76a81e4ab282e267` |
| 9 | `1-8-trends-in-the-business-environment-and-competition` | 200 | 1.8 Trends in the Business Environment and Competition - Introduction to Business \| OpenStax | `c0243a332a4b60a4` |
| 10 | `1-key-terms` | 200 | Ch. 1 Key Terms - Introduction to Business \| OpenStax | `e861c1293cb8124e` |
| 11 | `1-summary-of-learning-outcomes` | 200 | Ch. 1 Summary of Learning Outcomes - Introduction to Business \| OpenStax | `97ead8fa24262cb2` |
| — | `preface`（许可证据） | 200 | Preface - Introduction to Business \| OpenStax | `0fd35bae67be982e` |

完整 URL、字节数、`verified_at`、本地路径与全量 sha256：`source/fetch-log.json`。

## 3. 许可定义核验（4 条证据）

| 证据类型 | URL | HTTP | 标题 | 本地文件 |
|---|---|---|---|---|
| 图书许可声明 | `https://openstax.org/books/introduction-business/pages/preface` | 200 | Preface - Introduction to Business \| OpenStax | `source/raw/preface.html` |
| SPDX 许可定义 | `https://spdx.org/licenses/CC-BY-4.0.html` | 200 | Creative Commons Attribution 4.0 International \| Software Package Data Exchange (SPDX) | `source/evidence/spdx-cc-by-4.0.html` |
| 许可通俗说明 | `https://choosealicense.com/licenses/cc-by-4.0/` | 200 | Creative Commons Attribution 4.0 International \| Choose a License | `source/evidence/choosealicense-cc-by-4.0.html` |
| 仓库 LICENSE 原文 | `https://cdn.jsdelivr.net/gh/openstax/osbooks-introduction-business@main/LICENSE`（GitHub raw 在本环境超时，改用 jsDelivr CDN 拉取同一仓库文件） | 200（纯文本） | —（文本首行为 "Attribution 4.0 International"，正文为 CC BY 4.0 法律条款） | `source/evidence/osbooks-introduction-business-LICENSE.txt` |

**已知上游文案不一致（必须记录）**：同一仓库的 `README.md` 写 "available under the Creative Commons Attribution-NonCommercial-ShareAlike License"，与仓库 `LICENSE` 文件正文（CC BY 4.0）及**出版前言页**（CC BY 4.0）不一致。本 pilot **以出版前言页 + 仓库 LICENSE 文件正文为准**判定 Tier A；README 旧文案视为上游残留，不据此降级，也**不据此宣称无风险**——发布前应由法务/OpenStax 确认（未关闭项 U-1）。

**未能直连核验的 URL（不冒充 200）**：`https://creativecommons.org/licenses/by/4.0/` 在本环境连接超时（与 C0a 记录一致）。本包不把该 URL 记为已核验；许可身份由 SPDX 页 + 图书前言 + 仓库 LICENSE 三条 200 证据共同支撑。

## 4. 逐文档许可字段（C2）

| 字段 | 值 |
|---|---|
| license | CC BY 4.0 |
| SPDX | CC-BY-4.0 |
| redistribution | 允许（含再分发/改编），需给 OpenStax 及贡献者署名、附许可声明、标注修改、不暗示背书 |
| attribution | "Introduction to Business, OpenStax, Rice University, CC BY 4.0"（完整 NOTICE 见 `source/NOTICE.md`） |
| db_right | CC BY 4.0 已涵盖 sui generis 数据库权；本包仅取 1 章文本，未做数据库批量抽取 |
| fair_use | 不适用（直接获得 Tier A 许可，不依赖 fair use） |
| pii_risk | 未发现；轻量正则扫描（邮箱/电话）0 命中，见 `validate_pilot.py` 的 `source.pii_scan`。**Presidio 未安装/未运行**（未关闭项 U-2） |
| consent_basis | 不适用（公开出版教材，无个人数据） |
| evidence_url | 见 §2/§3；机器记录 `fetch-log.json` |
| checked_at | 2026-11-05T11:47–11:48（+08:00） |

## 5. Tier B/C 候选淘汰记录（证明“只选 Tier A”）

以下候选在选源阶段被检查并**淘汰**，其内容**未进入**本包（不存快照、不进 golden）：

| 候选 | 许可（该书 preface 实测） | 判定 |
|---|---|---|
| OpenStax Biology 2e | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA) | Tier B，淘汰 |
| OpenStax Psychology 2e | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax Introduction to Sociology 3e | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax College Physics 2e | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax U.S. History | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax Principles of Management | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax Introductory Statistics 2e | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax Principles of Economics 3e / Macroeconomics 3e / Microeconomics 3e | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax Entrepreneurship / Principles of Marketing / Organizational Behavior / Business Ethics / College Success / Contemporary Mathematics / Lifespan Development / Introduction to Philosophy / Principles of Finance | CC BY-NC-SA 4.0 | Tier B，淘汰 |
| OpenStax Chemistry 2e / Calculus | 仓库 LICENSE = CC BY-NC-SA | Tier B，淘汰 |

> 注：上述许可判定来自对应书 `pages/preface` 的 200 页面文本（2026-11-05 本机核验）；本包只保留判定结论与书名，不保留其正文。

## 6. 修改（modification）声明

相对原书网页版，本 pilot 做了以下**技术性修改**（CC BY 4.0 §3(a)(1)(B) 要求标注修改）：

1. 从 11 个正文页的 `#main-content` 抽取纯文本；删除 script/style/svg/导航；空白字符归一（连续空白 → 单空格，NBSP → 空格）；线性化为块序列并以空行分隔；
2. 未改写任何原句措辞；未增删正文语义内容（仅丢弃 `Concept Check`/案例等未纳入 KP 的部分不改变快照的完整性：快照仍包含这些块）；
3. 新增内容（KP/语义边/负例/query/标注）由 Memoria corpus pilot 创作，**不是** OpenStax 内容；
4. 抽取脚本与坐标规则版本化：`scripts/corpus/build_source_snapshot.py`（`corpus-pilot-source-snapshot/v1`）。

## 7. 复验命令（可复核）

```powershell
# 1) 重新抓取任一正文页，比较 HTTP 状态/标题（不覆盖快照）
curl.exe -s -o NUL -w "%{http_code}`n" -A "<browser UA>" https://openstax.org/books/introduction-business/pages/1-1-the-nature-of-business
# 2) 校验本包（含 raw sha256、许可证据、Tier、span 越界、2× 可复现）
python scripts/corpus/validate_pilot.py
```

## 8. 未关闭项（如实记录）

| # | 项 | 说明 |
|---|---|---|
| U-1 | 上游 README 文案与 LICENSE/前言不一致 | 以出版前言 + LICENSE 正文判 Tier A；发布前建议法务/OpenStax 确认 |
| U-2 | Presidio 正式 PII 扫描未运行 | 仅轻量正则 + 人工确认无 PII；Presidio 依赖未安装 |
| U-3 | CC 官方许可页连通性 | `creativecommons.org` 本环境超时；用 SPDX/ChooseALicense/仓库 LICENSE 替代证据，未冒充 200 |
| U-4 | 中文语料/UTF-8 中文偏移 | 本 pilot 为英文源，未验证中文 span/INCEpTION 导出；C0 O-C0-2 仍未关闭 |
| U-5 | 法律意见 | DB-right/fair-use 的逐法域意见未取得；当前结论基于 CC BY 4.0 文本 |
