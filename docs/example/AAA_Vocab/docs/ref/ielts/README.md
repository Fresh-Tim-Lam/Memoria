# docs/ref/ielts —— 雅思写作「判别资料」本地持久化清单

> **用途**：存放批改判定所依据的**官方原始资料**（band descriptors、评分标准、官方样卷与考官评语），供 `docs/ielts_band_descriptors.md` 与 `docs/writing_evaluator.md` 引用。
> **原则**：只存官方来源，不存二手转述；每份都标注原始 URL 与获取方式。

---

## 1. 清单与拉取状态

| 文件 | 内容 | 状态 | 来源 |
|---|---|---|---|
| `ielts-writing-band-descriptors.pdf` | **写作 band descriptors 全本**（Task 1/2，9 档，9 页，107 KB，Updated May 2023） | ✅ **完整留档** | `https://ielts.org/cdn/ielts-guides/ielts-writing-band-descriptors.pdf`（经 IDP 官方镜像下载） |
| `key-assessment-criteria.md` | **四项标准各自在考什么**（官方 4 页文本，逐字转写） | ✅ 全文 | `https://ielts.org/cdn/Guides/ielts-writing-key-assessment-criteria.pdf` |
| `ielts-academic-writing-sample-tasks-2023.pdf` | **官方样卷原件**（26 页，1.43 MB，含 12 份样卷 + 考官评语） | ✅ **完整留档**（用户提供） | `https://ielts.org/cdn/Sample-tests/ielts-academic-writing-sample-tasks-2023.pdf` |
| `ielts-academic-writing-sample-tasks-2023.vlm.md` | **vlm 引擎提取**（37.6 KB）——**读样卷正文用这版**（手写体识别质变可读）；⚠️ 个别页会生成幻觉表格 | ✅ 全文 | 由本目录 PDF 以 `-b vlm-engine` 提取 |
| `ielts-academic-writing-sample-tasks-2023.extracted.md` | **pipeline 引擎提取**（35.4 KB）——手写正文大量乱码，但**不出幻觉**，作交叉核对 | ✅ 全文 | 由本目录 PDF 以 `-b pipeline -m txt` 提取 |
| `sample-tasks-and-examiner-comments.md` | 官方样卷题面 1A/1B/1C/2A/2B（补齐前所获的题面文本，保留备查） | ⚠️ 部分（题面完整、评语仅引子） | 同上 |
| — | General Training 样卷（24 页） | ❌ **未提供**（本库备考 A 类，暂不需要） | — |

> **可引用性铁律**：band descriptors 与 *Key Assessment Criteria* 为**印刷原文**，可直接引用；**考官评语**为印刷体、提取干净，**可直接引用**；**样卷正文是手写体**，两个提取版本都是**机器识别所得、非官方发布文本**——读正文用 `.vlm.md`，但引用前须回原 PDF 核对。

## 2. 抓取通道的实测结论（供后来者省时间）

| 通道 | 结果 |
|---|---|
| 直接 `urllib` / `Invoke-WebRequest` 下载 `ielts.org/cdn/**` | ❌ **403**（多组浏览器 UA / Referer 均被 WAF 拦） |
| 直接下载 `cdn.ielts.org`、S3 镜像 `ielts-web-static/production/` | ❌ **403** |
| 直接下载 `chinaielts.org` | ❌ 返回 989 字节**混淆 JS 反爬**脚本，非 PDF |
| IDP 官方镜像 `assets.ctfassets.net` | ✅ **可用**（band descriptors 由此获得） |
| **WebFetch 工具** | ✅ **可用**（能读 ielts.org 的 PDF 并转文本），但**输出上限约 15 KB**，26 页样卷只能取到前段 |

> 结论：**PDF 走 IDP 镜像，文本走 WebFetch**；ielts.org 自家的直链在本机不可下载。

## 3. 缺件与补齐记录

| 件 | 状态 |
|---|---|
| `ielts-academic-writing-sample-tasks-2023.pdf` | ✅ **已补齐**（用户提供，1.43 MB），已用 MinerU 全量提取，12 份样卷的考官评语写入 `docs/ielts_band_descriptors.md` §6.1 / §6.2 |
| `ielts-general-training-writing-sample-tasks-2023.pdf`（24 页） | ❌ 未提供。本库备考 **A 类**，GT 的书信类材料暂不需要；若将来需要，浏览器另存到本目录即可，我再补 §6 |

**补齐流程（已验证可行）**：放好 PDF → 用 MinerU `pipeline -m txt` 提取（本机 `D:\Python\python.exe` + `D:\AAA_Courses\mineru_deps`）→ 提取结果以 `.extracted.md` 名并存本目录 → 抽 `## Band X` 段落得到「样卷档位 + 考官评语」→ 写入规范 §6。

## 4. 版本与更新

官方 band descriptors 页脚标注 **Updated May 2023**。官方更新时（页脚日期变化）需重新拉取并同步 `docs/ielts_band_descriptors.md` **§2.1 / §3.1 / §4** 的官方原文（该规范重构为 Part 1 / Part 2 分册后，原文分散在这三节）。
