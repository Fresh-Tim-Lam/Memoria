"""B-danger-1 v2.1 三点内容修正（① 独占定义 ③ R1 谁可执行 ④ 变更记录）

按锚点定位替换（不依赖跨行字面量），每步断言命中，失败即中止。
"""
import io
import re
import sys

P = "docs/guides/lead-dispatch-rules.md"
src = io.open(P, encoding="utf-8", newline="").read()

NEW1 = """### 1. 共享 vs 独占（默认为共享）
```
【默认】工作区是共享的 —— 任何成员都可能正在编辑任何文件。

【独占】唯一可机检的条件：文件位于【独立 worktree】内。
  · worktree 内默认为独占，前提是【路径唯一】（按「成员+任务」命名，如 %TEMP%/wt-<member>-<task>）
  · 若同一 worktree 被多人共用 ⇒ 仍按共享处理，并显式声明使用期
  · 判定只看「是否独立 worktree 路径（+唯一性）」⇒ 拦截器也只认这一条

【为什么删掉了 v2 原稿的「git status 干净 + Lead 授予 exclusive_paths」这条】
  · `git status` 【看不到编辑器未保存 buffer】⇒ "干净"不等于"没人在改"
  · `exclusive_paths` 在 dispatch-log 里【没有这个字段/校验】⇒ 写了也没有机检
  ⇒ 留着它就是「看起来有闸」的假保护（正是 PD-1 的形态）

【共享区要独占怎么办】⇒ 降级为【派发纪律】，不是机检条件：
  Lead 在派发时明确声明该文件归谁、其他成员不得碰（可在 dispatch-log 记 declared_owner 备查），
  但【不作为 guard 判定依据】—— guard 对共享区一律 deny。
```
"""

NEW3 = """### 5. R1 例外流程（确实需要临时回滚验证时）
```
【谁可执行】仅 **Lead** 可发起 R1 例外；成员需要 Lead 授权后才可执行，
            且必须在 dispatch-log 留痕（未留痕即视为违规）。
【记录内容】dispatch-log `phase=risk` + 完整命令 + 理由 + 执行前 sha256 快照
【事后】做差集核对，并把核对结论【写回同一条 dispatch-log 记录】；
        若丢了他人改动 ⇒ 按 R1 事故上报（不得静默重写）
```
"""

CHANGELOG_ADD = """
### B-danger-1 v2.1（2026-10-26，据 steward SF-056 审计 4 点）

| 项 | 修正 |
|---|---|
| ① worktree「天然独占」过强 | 改为「默认独占 + 路径唯一（成员+任务）；共用则按共享处理并显式声明」 |
| ② 删除独占条件 (a) | `git status` 看不到未保存 buffer；`exclusive_paths` 无字段/校验 ⇒ 留着是「看起来有闸」的假保护。共享区独占降级为**派发纪律**，guard 只认独立 worktree |
| ③ R1 例外未写「谁可执行」 | 写明：仅 Lead 可发起；成员需 Lead 授权 + dispatch-log 留痕；差集结论写回同一记录 |
| ④ 位置可发现性差 | 已从文件末尾移到 **§1 之后**，并在 §0 加醒目指针 |
"""


def replace_section(text: str, heading: str, new_body: str) -> str:
    """把 `heading` 开头的 ### 小节整体替换为 new_body（到下一个 ### 或 ## 为止）。"""
    m = re.search(r"^" + re.escape(heading) + r".*$", text, re.MULTILINE)
    if not m:
        sys.exit("ABORT: 找不到小节 " + heading)
    start = m.start()
    rest = text[m.end():]
    nxt = re.search(r"^(### |## )", rest, re.MULTILINE)
    end = m.end() + (nxt.start() if nxt else len(rest))
    return text[:start] + new_body + text[end:]


before_len = len(src)
src = replace_section(src, "### 1. 共享 vs 独占", NEW1)
src = replace_section(src, "### 5. R1 例外流程", NEW3)
assert "exclusive_paths" in src and "【为什么删掉了 v2 原稿" in src, "① 未生效"
assert "仅 **Lead** 可发起 R1 例外" in src, "③ 未生效"

# ④ 变更记录追加
if "B-danger-1 v2.1" not in src:
    src = src.rstrip("\n") + "\n" + CHANGELOG_ADD
assert "B-danger-1 v2.1" in src, "④ 未生效"

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("  OK: ①③④ 已应用；长度 %d -> %d" % (before_len, len(src)))
