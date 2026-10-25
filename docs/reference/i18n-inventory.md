# UI 界面文案清单（i18n Inventory）

> **用途**：登记桌面应用**前端界面**全部含中文的用户可见文案与定位（文件+行号），作为 i18n 迁移（抽键→语言包）与后续新增 UI 自查的依据。
> **目标读者**：项目负责人 / AI Agent（迁移文案、新增 UI、审阅语言包前必查）。
> **关联文档**：[i18n.md](../conventions/i18n.md)（语言系统维护规范）；[docs-management.md](../conventions/docs-management.md)（docs 组织规则）。
> **范围/边界**：仅统计 `src/memoria/ui/static/app/` 下 index.html、app/js/*.js、app/css 的 `content:` 文案；**不含** lib/vendor/mathjax 第三方库、纯注释文件（lexer/parser/ast 等中文均为注释，不属界面文案）；后端 Python 返回给界面的消息（document.py/import_engine.py/ui.py 等）为另一分区，机制落地后另行登记。
> **剔除规则**：开发日志（`console.*` / `syncLog` / `log(` / `.note?.(` 等封装调用；i18n.md §2 非界面文案）；HTML 中已挂 `data-i18n`/`data-i18n-attr` 的静态节点（行内含标记即视为已迁移，中文仅为默认值/占位）。
> **生成**：`python scripts/scan_ui_strings.py`（确定性输出，可重复执行覆盖本文）。状态口径：`☐ 未迁移` 表示仍硬编码中文；迁移为 `t('key')` 后人工将对应文件状态置 `✔ 已迁移`（脚本重跑会重置，可在本文末尾「迁移记录」人工维护）。
> 生成日期：2026-10-25

## 统计总览

| 文件 | 含中文候选行数 | 状态 |
|------|------|------|
| `src/memoria/ui/static/app/js/review-manage.js` | 34 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/review-summon.js` | 16 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/review-modal.js` | 15 | ☐ 未迁移 |
| `src/memoria/ui/static/app/index.html` | 12 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/agent-panel.js` | 6 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/agent-question.js` | 1 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/app.js` | 1 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/edit-handler.js` | 1 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/keys-debug.js` | 1 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/net-settings.js` | 1 | ☐ 未迁移 |
| `src/memoria/ui/static/app/js/plugins-settings.js` | 1 | ☐ 未迁移 |
| **合计** | **89** | — |

## 逐文件清单

### src/memoria/ui/static/app/js/review-manage.js

- L16: : "error", code: "no_bridge", message: "桥不可用" });
- L29: const TYPE_ZH = { basic: "基础", cloze: "挖空", reverse: "反向", mcq: "选择", gapfill: "填空", short: "简答"
- L52: '<span class="-review-manage-title">复习卡管理</span>' +
- L54: e="button" class="-btn" id="-rm-review">批量复习</button>' +
- L55: tton" class="-btn primary" id="-rm-new">新建卡</button>' +
- L56: class="-icon-btn" id="-rm-close" title="关闭" aria-label="关闭">×</button>' +
- L60: t type="search" id="-rm-q" placeholder="搜索 card_id / 卡面…">' +
- L61: '<select id="-rm-type"><option value="">全部类型</option>' + typeOptions() + "</select>" +
- L83: if (!kb) { flash("请先打开知识库"); return; }
- L85: tatus !== "ok") { flash(res.message 丨丨 "加载失败"); return; }
- L105: if (count) count.textContent = "共 " + S.cards.length + " 张" + (list.length !== S.cards.length ? "，筛选出
- L109: ML = '<div class="-review-manage-empty">没有复习卡' + (S.cards.length ? "（筛选无结果）" : "，点右上「新建卡」创建") + "</div>";
- L152: (dis ? '<span class="-rm-badge-dis">已禁用</span>' : "") +
- L157: data-rm-enter="' + esc(c.card_id) + '">进入</button>' +
- L158: " data-rm-edit="' + esc(c.card_id) + '">编辑</button>' +
- L159: "' + (dis ? "0" : "1") + '">' + (dis ? "启用" : "禁用") + "</button>" +
- L160: r" data-rm-del="' + esc(c.card_id) + '">删除</button>' +
- L178: ="-review-manage-title" id="-rmf-title">新建卡</span>' +
- L179: lass="-icon-btn" id="-rmf-close" title="关闭" aria-label="关闭">×</button>' +
- L182: t type="text" id="-rmf-id" placeholder="唯一 id，如 vocab-001"></label>' +
- L183: '<label class="-rm-field">类型<select id="-rmf-type">' + typeOptions() + "</select></label>" +
- L184: '<label class="-rm-field">正面（front）<textarea id="-rmf-front" rows="3"></textarea></label>' +
- L185: '<label class="-rm-field">背面（back）<textarea id="-rmf-back" rows="3"></textarea></label>' +
- L186: '<label class="-rm-field">来源（source，可选）<input type="text" id="-rmf-source"></label>' +
- L187: '<div class="-rm-form-hint">选择题/填空题的 options/answer 等扩展字段在编辑时原样保留；如需精调可用 agent 工具 review_cards_ups
- L190: on" class="-btn primary" id="-rmf-save">保存</button>' +
- L191: ="button" class="-btn" id="-rmf-cancel">取消</button>' +
- L206: or("#-rmf-title").textContent = card ? "编辑卡 " + cid : "新建卡";
- L233: if (!row.card_id) { flash("card_id 不能为空"); return; }
- L234: if (!row.front) { flash("正面 front 不能为空"); return; }
- L241: tatus !== "ok") { flash(res.message 丨丨 "保存失败"); return; }
- L248: if (!global.confirm("删除卡片「" + cid + "」？卡定义会被移除（学习进度保留）。")) return;
- L250: tatus !== "ok") { flash(res.message 丨丨 "删除失败"); return; }
- L256: tatus !== "ok") { flash(res.message 丨丨 "操作失败"); return; }

### src/memoria/ui/static/app/js/review-summon.js

- L30: : "error", code: "no_bridge", message: "桥不可用" });
- L89: n-open" id="-review-summon-open" title="打开来源" aria-label="打开来源">' + esc(T("review.openSource")) + "</button>"
- L291: t"><span class="-review-spinner"></span>判分中…</div>'); } renderGrade(false);
- L349: el.textContent = n > 0 ? "还有 " + n + " 张" : "";
- L454: "请判分复习卡 `" + cid + "`（开放题，judge:agent）。\n【题目】\n" + front + "\n\n【用户作答】\
- L455: "请分析作答质量、给出判分，然后用 `review_feedback_add` 写入 feedback（你的分析文字）、verdict（cor
- L460: <div class="-review-summon-verdict-bad">判分触发失败：' + esc((res && (res.message 丨丨 res.code)) 丨丨 "未知") + "</div>")
- L463: <div class="-review-summon-verdict-bad">判分触发失败：' + esc(String((e && e.message) 丨丨 e)) + "</div>");
- L485: <div class="-review-summon-verdict-bad">判分超时：agent 未返回分析，请到会话查看</div>');
- L506: <div class="-review-summon-verdict-bad">判分超时：agent 未返回分析，请到会话查看</div>');
- L532: w-feedback-reply" rows="2" placeholder="进一步反馈…"></textarea>' +
- L533: imary" id="-review-feedback-reply-send">发送</button>' +
- L541: "用户对复习卡 `" + cid + "` 的判分给出了进一步反馈：\n" + reply +
- L542: "\n请用 `review_attempts_list` 读取该卡完整记录，回应这条反馈（可修正判分），并用 `review_feedback_a
- L554: <div class="-review-summon-verdict-bad">反馈记录失败</div>');
- L557: t"><span class="-review-spinner"></span>判分中…</div>');

### src/memoria/ui/static/app/js/review-modal.js

- L48: ror", code: "apiUnavailable", message: "桥不可用" });
- L163: tn--sm" id="-review-open-source" title="打开来源" aria-label="打开来源">' + esc(T("review.openSource")) + "</button>"
- L164: s="-icon-btn" id="-review-close" title="关闭" data-i18n-attr="title:dialog.closeTitle">×</button>' +
- L697: t"><span class="-review-spinner"></span>判分中…</div>';
- L833: "请判分复习卡 `" + cid + "`（开放题，judge:agent）。\n【题目】\n" + front + "\n\n【用户作答】\
- L834: "请分析作答质量、给出判分，然后用 `review_feedback_add` 写入 feedback（你的分析文字）、verdict（cor
- L839: view-verdict-label -review-verdict-bad">判分触发失败：' + esc((res && (res.message 丨丨 res.code)) 丨丨 "未知") + "</div>";
- L842: view-verdict-label -review-verdict-bad">判分触发失败：' + esc(String((e && e.message) 丨丨 e)) + "</div>";
- L874: view-verdict-label -review-verdict-bad">判分超时：agent 未返回分析，请到会话查看</div>';
- L922: w-feedback-reply" rows="2" placeholder="进一步反馈…"></textarea>' +
- L923: imary" id="-review-feedback-reply-send">发送</button>' +
- L931: "用户对复习卡 `" + cid + "` 的判分给出了进一步反馈：\n" + reply +
- L932: "\n请用 `review_attempts_list` 读取该卡完整记录，回应这条反馈（可修正判分），并用 `review_feedback_a
- L944: showVerdictError("反馈记录失败", "");
- L948: t"><span class="-review-spinner"></span>判分中…</div>';

### src/memoria/ui/static/app/index.html

- L15: // 首帧前定主题，避免"深色闪一下"：localStorage 快路径（磁盘设置由 theme-mode.js 随后同步）
- L26: // 2026-10-22 修（task-63 期间发现的发布级 bug）：
- L27: //   真实教材大量使用 `\boldsymbol`（数字通信原理 语料 1,101 次 / 15 篇；08 章 527 次），
- L28: //   而 vendor 目录 `vendor/mathjax/es5/input/tex/extensions/` **没有 boldsymbol
- L29: //   ⇒ MathJax `autoload` 遇到 `\boldsymbol` 就去 fetch 该文件 ⇒ 404
- L30: //   ⇒ 整个 `typesetPromise` 被拒绝 ⇒ **全部公式都不排版**（只有一行 console 日志，用户不可见）。
- L31: //   实测复现：预览视图下打开 08 章 → 20s 后 mjx=0；source 下打开再切 preview → mjx=2850。
- L33: //   处置（两层，都不需要补 vendor 文件）：
- L34: //   ① `[+]` 只保留 vendor 真实存在的 6 个扩展（缺失的 4 个不再强制加载）；
- L35: //   ② 用宏把 `\boldsymbol`/`\bm` 映射到 `\mathbf` —— 宏已定义 ⇒ autoload 不再触发 fetch，
- L36: //      公式整体正常排版；粗体符号退化为 `\mathbf`（希腊小写/部分符号的粗体效果会丢失，
- L37: //      属可接受的降级，远好于"整篇公式不显示"）。

### src/memoria/ui/static/app/js/agent-panel.js

- L7144: (code === "RESOURCE_TOO_LARGE") return "资源文件过大（上限 20 MiB）";
- L7145: == "UNSUPPORTED_RESOURCE_TYPE") return "只支持 PDF / Word(.docx) / TXT / Markdown";
- L7147: String((res && res.message) 丨丨 "") 丨丨 "资源上传失败";
- L7188: showAttachError("资源文件过大（上限 20 MiB）：" + String(files[i].name 丨丨 ""));
- L7200: return "（用户拖入了以下资料文件，请用 read_resource 工具按需读取其内容）\n" +
- L7227: showAttachError("不支持的文件类型：" + String(others[0].name 丨丨 "") + "（可拖入图片或 PDF / Word / TXT

### src/memoria/ui/static/app/js/agent-question.js

- L35: : "error", code: "no_bridge", message: "桥不可用" });

### src/memoria/ui/static/app/js/app.js

- L8475: cap.textContent = "图";

### src/memoria/ui/static/app/js/edit-handler.js

- L843: var msg = "剪切已从文档移除，但写入剪贴板失败：内容可能无法粘贴。";

### src/memoria/ui/static/app/js/keys-debug.js

- L113: " 丨 自第 " + (p + 1) + " 行起 丨 删除 " + removed.length + " 行 / 新增 " + added.len

### src/memoria/ui/static/app/js/net-settings.js

- L27: : "error", code: "no_bridge", message: "桥不可用" });

### src/memoria/ui/static/app/js/plugins-settings.js

- L28: : "error", code: "no_bridge", message: "桥不可用" });

## 迁移记录

| 日期 | 文件/区域 | 动作 | 结果 |
|------|------|------|------|
|（初始生成）| 全部 | 盘点登记 | — |

