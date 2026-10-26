#!/usr/bin/env python3
"""发版前置检查（repo 侧，方案 B 的第一落点 + GitHub Release 三条硬规则机检）。

目的：把「发版前必须有 supervisor 审查」与「GitHub Release 规范」从文档约定变成
**命令拒绝**：规则不过 ⇒ exit 1（缺什么就报什么）。规范靠记忆已经失败过一次
（v0.4.7 / v0.4.8 / v0.5.0 连续三版标题带副标题），所以这里不再依赖记忆。

用法（发版模式：三条硬规则 + 版本三查 + tag/资产）：
  python scripts/agent/release_preflight.py --tag v0.4.8 \\
      --title "Memoria v0.4.8" --body-file artifacts/release-body.md
  python scripts/agent/release_preflight.py --tag v0.4.8 --phase pre ...   # tag 必须尚不存在
  python scripts/agent/release_preflight.py --tag v0.4.8 ... --offline    # 联网项标 SKIP
  python scripts/agent/release_preflight.py --tag v0.4.8 --json

发布后审计（直接核对 GitHub 上「实际发出去的」标题/正文/资产，防「本地改好了但没 PATCH 成功」）：
  python scripts/agent/release_preflight.py --tag v0.4.8 --verify-published
  python scripts/agent/release_preflight.py --tag v0.4.8 --verify-published --release-json rel.json

兼容旧用法（review artifact 检查，语义保持）：
  python scripts/agent/release_preflight.py --version 0.4.8
  python scripts/agent/release_preflight.py --selftest

审查 artifact 契约（supervisor 写）：
  artifacts/agent/verify/supervisor/<anything>.md，front-matter 行：
    version: 0.4.8
    reviewer: <member>
    verdict: pass        # pass | fail
    evidence: <path 或 commit>     # 至少 1 条
  verdict 不是 pass ⇒ 视为未审查通过。

退出码：0 = 无 FAIL（可能含 SKIP；skipped 不算通过）；
        1 = 有 FAIL（任一硬规则不过）；
        2 = 用法错误。

════════════════════════════════════════════════════════════════════════
作者分界（2026-10-25，重要：改文件前先读这段，避免两人同文件冲突）
────────────────────────────────────────────────────────────────────────
① 【已实现，勿删/勿改语义】review artifact 检查 —— 作者 todo-owner
   - 检查项：SUPERVISOR-REVIEW（缺审查/version 不符/verdict≠pass/缺 evidence ⇒ FAIL）、
     VERSION-CONSISTENT、DECISION-TRAIL（WARN）、TAG-NOT-EXISTS（WARN）
   - 对应 `check()` / `find_reviews()` / `parse_review()` / `read_repo_version()`
   - `--selftest` 原四条 fixture（no-artifact / wrong-version / verdict-fail / valid）保留
   - 来源：team 插件方向设计「方案 B 的 repo 侧落点」；用于发版前强制 supervisor 审查。
   - 若需改语义，请与 todo-owner 确认，不要静默重写。

② 【已实现】三条 GitHub Release 规范检查 —— 作者 release-manager（2026-10-25）
   - 口径以 `docs/conventions/version.md`「GitHub Release 规范」章为准：
     * 检查 1 TITLE-EXACT：`title == "Memoria " + tag`（严格字符串相等；禁 startswith/in/正则宽松）
     * 检查 2 BODY-BILINGUAL：`## English` 与 `## 中文` 都存在、English 在前；
       两段有效内容（去标题/分隔线/空行）均 >200 字符（≤200 判 stub）
     * 检查 3 COST-SECTION：中文 `## 造价（Agent 算力）`（全角括号）与
       英文 `## Cost (Agent compute)`（半角括号）都存在；中文造价段含量级关键词
       （元|人民币|CNY|USD|RMB|花费）与统计口径（统计口径|合并统计）；英文造价段含量级关键词；
       成本结构关键词缺失只 WARN（规范要求但非本轮硬判据）
     * 检查 4 ASSETS-COUNT：发布资产 = 2（win64 完整包 + win64-lite 轻量包）；
       发布前无数据 ⇒ SKIP；`--verify-published` 时从 GitHub Release JSON 判 FAIL/PASS
     * 检查 5 VERSION-THREE-WAY：tag 去 v 前缀 == `src/memoria/__version__.py`
       == `Package/VERSION` == `docs/conventions/version.md §1`（当前版本）；
       审计模式改从 tag 提交的 git 对象核验已跟踪的两处（Package/VERSION 未入库，显式说明）
     * 检查 6 TAG-REMOTE：`--phase post`（默认）要求远端 tag 存在；`--phase pre` 要求不存在；
       `--offline` ⇒ SKIP（不计为通过）；ls-remote 不可用且联网时回退 GitHub API refs
     * 检查 7 VERSION-NOTE-PUBLISHED（**仅 `--verify-published`**，release-manager 2026-10-26，
       task-167）：`version.md §1「说明」行` 的「最近已发布 = X.Y.Z」必须 == 本次 tag 版本；
       解析失败（行缺失/措辞改变/无版本号）⇒ **FAIL**（不是 WARN、不是 SKIP，防静默失效）；
       读**工作区** version.md（人实际读到的那份），不读 tag 提交（v0.4.9 tag 提交里写的是 0.4.8，
       正是本次要抓的错误）。
       接入点理由：只有 `--verify-published` 阶段同时拿到「真实 tag + 真实发布状态 + 发布后的文档」；
       pre/post 发生在发布过程中，此时「最近已发布」按定义还是上一版，断言必然误红。
   - supervisor review：release 模式默认 **WARN**（`--require-review` 升级 FAIL；legacy 模式仍 FAIL）。
     **目标状态是硬 FAIL**；翻转条件 = supervisor 角色投入运行 + 至少 1 份合格 review artifact
     （见 version.md §6 第 0 步）。翻转后默认 FAIL，`--allow-missing-review` 才降级。
   - 每条规则都有「必红」fixture（见 `selftest_release()`）；`--selftest` 全绿才算自证
   - 接入点：version.md §6 第 0 步（0a pre / 0b post / 0c verify-published）
   - 裁决（Lead 2026-10-25）：`--tag` 是发布事实、`--version` 是代码事实；两者必须相等。
     未传 `--tag` 时用 `v` + `--version` 合成 tag 并在输出标 WARN。
════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_DIR = ROOT / "artifacts" / "agent" / "verify" / "supervisor"
VERSION_FILE = ROOT / "src" / "memoria" / "__version__.py"
DEFAULT_REPO_SLUG = "Fresh-Tim-Lam/Memoria"

FRONT = re.compile(r"^(version|reviewer|verdict|evidence)\s*:\s*(.+?)\s*$", re.M)

# ══════════════════════════════════════════════════════════════════════
# ① review artifact 检查（作者：todo-owner；release-manager 请勿改语义）
# ══════════════════════════════════════════════════════════════════════


def read_repo_version() -> str | None:
    try:
        text = VERSION_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def parse_review(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fields = {}
    for key, value in FRONT.findall(text):
        fields.setdefault(key, []).append(value.strip().strip("`"))
    return {
        "path": str(path),
        "version": (fields.get("version") or [None])[0],
        "reviewer": (fields.get("reviewer") or [None])[0],
        "verdict": ((fields.get("verdict") or [""])[0]).lower(),
        "evidence": fields.get("evidence") or [],
    }


def find_reviews(review_dir: Path) -> list[dict]:
    if not review_dir.is_dir():
        return []
    out = []
    for p in sorted(review_dir.rglob("*.md")):
        try:
            out.append(parse_review(p))
        except OSError:
            continue
    return out


def check(version: str, review_dir: Path) -> list[dict]:
    checks: list[dict] = []

    repo_version = read_repo_version()
    checks.append({
        "id": "VERSION-CONSISTENT",
        "level": "PASS" if repo_version == version else "FAIL",
        "detail": f"src/memoria/__version__.py = {repo_version!r}；期望 {version!r}",
    })

    reviews = find_reviews(review_dir)
    matching = [r for r in reviews if r["version"] == version]
    passing = [r for r in matching if r["verdict"] == "pass" and r["evidence"]]
    if passing:
        checks.append({
            "id": "SUPERVISOR-REVIEW",
            "level": "PASS",
            "detail": f"找到 {len(passing)} 份通过的审查（{passing[0]['path']}，reviewer={passing[0]['reviewer']}）",
        })
    else:
        reasons = []
        if not reviews:
            reasons.append(f"审查目录为空或不存在：{review_dir}")
        elif not matching:
            reasons.append(f"有 {len(reviews)} 份审查，但无 version={version} 的")
        else:
            for r in matching:
                if r["verdict"] != "pass":
                    reasons.append(f"{r['path']} verdict={r['verdict'] or '缺失'}")
                elif not r["evidence"]:
                    reasons.append(f"{r['path']} 缺 evidence")
        expected = (f"按契约创建 {review_dir}/<name>.md，front-matter 含 "
                    f"version: {version} / reviewer: <member> / verdict: pass / evidence: <path或commit>")
        checks.append({
            "id": "SUPERVISOR-REVIEW",
            "level": "FAIL",
            "detail": "；".join(reasons) + "。 " + expected,
        })

    # decisions：只做 WARN（决策索引目前由 team_audit/decide.py 管，不阻断发版）
    decisions = ROOT / "team" / "decisions.jsonl"
    if decisions.is_file():
        hits = [ln for ln in decisions.read_text(encoding="utf-8", errors="ignore").splitlines()
                if version in ln and ln.strip()]
        if hits:
            checks.append({"id": "DECISION-TRAIL", "level": "PASS",
                           "detail": f"decisions.jsonl 有 {len(hits)} 条含 {version} 的记录"})
        else:
            checks.append({"id": "DECISION-TRAIL", "level": "WARN",
                           "detail": f"decisions.jsonl 无含 {version} 的记录（建议记一条发版决策）"})
    else:
        checks.append({"id": "DECISION-TRAIL", "level": "WARN", "detail": "team/decisions.jsonl 不存在"})

    # tag：发版前不应已存在同名 tag（存在 ⇒ 可能重复发版）
    try:
        proc = subprocess.run(["git", "tag", "-l", f"v{version}"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)
        tag = proc.stdout.strip()
        checks.append({
            "id": "TAG-NOT-EXISTS",
            "level": "WARN" if tag else "PASS",
            "detail": f"v{version} {'已存在：' + tag if tag else '尚不存在（符合预期）'}",
        })
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append({"id": "TAG-NOT-EXISTS", "level": "WARN", "detail": f"git 不可用：{exc}"})

    return checks


def selftest_legacy() -> list[tuple[str, bool]]:
    """① 的原有四条 fixture（语义不变）。"""
    results = []
    tmp = Path(tempfile.mkdtemp(prefix="release-preflight-selftest-"))
    try:
        review_dir = tmp / "supervisor"
        review_dir.mkdir()

        def review_level() -> str:
            checks = check("9.9.9", review_dir)
            for c in checks:
                if c["id"] == "SUPERVISOR-REVIEW":
                    return c["level"]
            return "MISSING"

        results.append(("① no-artifact FAIL", review_level() == "FAIL"))

        (review_dir / "wrong.md").write_text(
            "version: 8.8.8\nreviewer: x\nverdict: pass\nevidence: abc\n", encoding="utf-8")
        results.append(("① wrong-version FAIL", review_level() == "FAIL"))

        (review_dir / "fail-verdict.md").write_text(
            "version: 9.9.9\nreviewer: x\nverdict: fail\nevidence: abc\n", encoding="utf-8")
        results.append(("① verdict-fail FAIL", review_level() == "FAIL"))

        (review_dir / "good.md").write_text(
            "version: 9.9.9\nreviewer: probe\nverdict: pass\nevidence: artifacts/x.md\n", encoding="utf-8")
        results.append(("① valid PASS", review_level() == "PASS"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


# ══════════════════════════════════════════════════════════════════════
# ② GitHub Release 三条硬规则 + 版本三查 + tag/资产（作者：release-manager）
# ══════════════════════════════════════════════════════════════════════

TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)$")
EN_HEAD = re.compile(r"^##\s+English\s*$", re.M)
ZH_HEAD = re.compile(r"^##\s+中文\s*$", re.M)
COST_ZH_HEAD = re.compile(r"^##\s+造价（Agent 算力）\s*$", re.M)
COST_EN_HEAD = re.compile(r"^##\s+Cost \(Agent compute\)\s*$", re.M)
H2_LINE = re.compile(r"^##\s+")
VERSION_ROW = re.compile(
    r"\|\s*当前版本\s*\|\s*\**([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.\-]+)?)\**\s*\|")
# version.md §1「说明」行：| 说明 | 最近已发布 = **0.4.9**（…） |
# 只认「说明」行里的「最近已发布」短语；解析失败按 FAIL（不许静默跳过）。
NOTE_ROW = re.compile(r"^\|\s*说明\s*\|\s*(.*?)\s*\|\s*$", re.M)
NOTE_PUBLISHED = re.compile(
    r"最近已发布\s*[=＝:：]\s*\**\s*v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)")
MAGNITUDE = re.compile(r"(人民币|元|CNY|USD|RMB|花费)")
BASIS = re.compile(r"(统计口径|合并统计)")
STRUCTURE = re.compile(r"(成本结构|cost structure)", re.I)


def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    return tag if tag.startswith("v") else "v" + tag


def tag_version(tag: str) -> str:
    m = TAG_RE.match(tag)
    if not m:
        raise ValueError(f"tag 格式非法：{tag!r}（要求 vX.Y.Z）")
    return m.group(1)


def _level(checks: list[dict], cid: str) -> str:
    for c in checks:
        if c["id"] == cid:
            return c["level"]
    return "MISSING"


def _heading_span(body: str, pattern: re.Pattern) -> tuple[int, int] | None:
    """返回标题行在 lines 中的 (行号, 该行结束后的字符偏移)。"""
    m = pattern.search(body)
    if not m:
        return None
    line_start = body.rfind("\n", 0, m.start()) + 1
    line_end = body.find("\n", m.start())
    if line_end < 0:
        line_end = len(body)
    line_no = body.count("\n", 0, line_start)
    return line_no, line_end + 1


def _split_lines(body: str) -> list[str]:
    return body.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _section_effective_text(lines: list[str], start_line: int, end_line: int | None = None,
                            exclude: list[tuple[int, int]] | None = None) -> str:
    """区段有效内容：去标题行、空行、分隔线（---），保留正文；可排除子区段（如造价段）。"""
    chunk = lines[start_line:end_line]
    skip = set()
    for a, b in exclude or []:
        for i in range(a, b):
            skip.add(i)
    keep = []
    for offset, ln in enumerate(chunk):
        if (start_line + offset) in skip:
            continue
        s = ln.strip()
        if not s:
            continue
        if s == "---":
            continue
        if re.match(r"^#{1,6}\s", s):
            continue
        keep.append(s)
    return "\n".join(keep)


def _next_h2(lines: list[str], start_line: int) -> int | None:
    for i in range(start_line, len(lines)):
        if H2_LINE.match(lines[i]):
            return i
    return None


def _find_line(lines: list[str], pattern: re.Pattern) -> int | None:
    for i, ln in enumerate(lines):
        if pattern.match(ln.rstrip()):
            return i
    return None


def eval_title(tag: str, title: str) -> dict:
    expected = "Memoria " + tag
    if title == expected:
        return {"id": "TITLE-EXACT", "level": "PASS",
                "detail": f"标题严格等于 {expected!r}"}
    hints = []
    if title.startswith(expected):
        hints.append("以正确前缀开头但带了额外内容（副标题/后缀）")
    if "——" in title or " - " in title or "—" in title or "–" in title:
        hints.append("含破折号 → 疑似「版本号 + 一段话」")
    if not title.startswith("Memoria "):
        hints.append("未以 'Memoria ' 开头")
    hint = "；".join(hints) or "字符串不相等"
    return {"id": "TITLE-EXACT", "level": "FAIL",
            "detail": f"标题必须严格等于 {expected!r}，实际 {title!r}（{hint}）。"
                      f"亮点写 body，不写标题。"}


def eval_body(body: str) -> tuple[list[dict], dict]:
    lines = _split_lines(body)
    checks: list[dict] = []
    en_i = _find_line(lines, EN_HEAD)
    zh_i = _find_line(lines, ZH_HEAD)
    metrics: dict = {}

    problems = []
    if en_i is None:
        problems.append("缺 `## English` 标题行")
    if zh_i is None:
        problems.append("缺 `## 中文` 标题行")
    if en_i is not None and zh_i is not None and not (en_i < zh_i):
        problems.append(f"顺序错误：英文段行 {en_i + 1} 在中文段行 {zh_i + 1} 之后（必须英语在前、中文在后）")

    if problems:
        checks.append({"id": "BODY-BILINGUAL", "level": "FAIL", "detail": "；".join(problems)})
        return checks, metrics

    assert en_i is not None and zh_i is not None
    # 造价段行范围（用于从语言块里剔除，避免「一句摘要 + 长造价段」混过 stub 检查）
    cost_ranges: list[tuple[int, int]] = []
    for pat in (COST_EN_HEAD, COST_ZH_HEAD):
        ci = _find_line(lines, pat)
        if ci is not None:
            cend = _next_h2(lines, ci + 1)
            cost_ranges.append((ci, cend if cend is not None else len(lines)))
    # 语言块：EN 标题→中文标题 / 中文标题→文末（含造价段，仅用于报告口径）
    en_block = _section_effective_text(lines, en_i + 1, zh_i)
    zh_block = _section_effective_text(lines, zh_i + 1, None)
    # 语言主内容：语言块剔除造价段之后的有效正文（stub 判定用）
    en_text = _section_effective_text(lines, en_i + 1, zh_i, exclude=cost_ranges)
    zh_text = _section_effective_text(lines, zh_i + 1, None, exclude=cost_ranges)
    en_len, zh_len = len(en_text), len(zh_text)
    metrics = {"en_block_chars": len(en_block), "zh_block_chars": len(zh_block),
               "en_main_chars": en_len, "zh_main_chars": zh_len,
               "en_heading_line": en_i + 1, "zh_heading_line": zh_i + 1}

    stub = []
    if en_len <= 200:
        stub.append(f"英文段主内容仅 {en_len} 字符（≤200 判 stub；不含造价段）")
    if zh_len <= 200:
        stub.append(f"中文段主内容仅 {zh_len} 字符（≤200 判 stub；不含造价段）")
    if stub:
        checks.append({"id": "BODY-BILINGUAL", "level": "FAIL",
                       "detail": "；".join(stub) + "。两段都要完整，不是「英文摘要 + 中文全文」。"})
    else:
        checks.append({"id": "BODY-BILINGUAL", "level": "PASS",
                       "detail": f"英文在前（行 {en_i + 1}）/ 中文在后（行 {zh_i + 1}）；"
                                 f"主内容 EN={en_len} 字符、ZH={zh_len} 字符（均 >200）"})
    return checks, metrics


def eval_cost(body: str) -> list[dict]:
    lines = _split_lines(body)
    zh_i = _find_line(lines, COST_ZH_HEAD)
    en_i = _find_line(lines, COST_EN_HEAD)
    problems = []
    if zh_i is None:
        problems.append("缺中文造价段标题 `## 造价（Agent 算力）`（全角括号）")
    if en_i is None:
        problems.append("缺英文造价段标题 `## Cost (Agent compute)`（半角括号）")
    if problems:
        return [{"id": "COST-SECTION", "level": "FAIL", "detail": "；".join(problems)}]

    assert zh_i is not None and en_i is not None
    zh_end = _next_h2(lines, zh_i + 1)
    en_end = _next_h2(lines, en_i + 1)
    zh_text = _section_effective_text(lines, zh_i + 1, zh_end)
    en_text = _section_effective_text(lines, en_i + 1, en_end)

    sub = []
    if not MAGNITUDE.search(zh_text):
        sub.append("中文造价段缺「量级」关键词（元/人民币/CNY/USD/RMB/花费）")
    if not BASIS.search(zh_text):
        sub.append("中文造价段缺「统计口径」（统计口径/合并统计）")
    if not MAGNITUDE.search(en_text):
        sub.append("英文造价段缺量级关键词（CNY/USD/RMB/元/人民币/花费）")
    if sub:
        return [{"id": "COST-SECTION", "level": "FAIL", "detail": "；".join(sub)}]

    warns = []
    if not STRUCTURE.search(zh_text) and not STRUCTURE.search(en_text):
        warns.append("未出现「成本结构 / cost structure」字样（规范要求一句话成本结构，仅告警）")
    level = "WARN" if warns else "PASS"
    detail = "中英文造价段齐全，含量级与统计口径"
    if warns:
        detail += "；" + "；".join(warns)
    return [{"id": "COST-SECTION", "level": level, "detail": detail}]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _parse_version_py(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def _parse_docs_version(text: str | None) -> str | None:
    if not text:
        return None
    m = VERSION_ROW.search(text)
    return m.group(1) if m else None


def _parse_docs_note_version(text: str | None) -> tuple[str | None, str | None, str | None]:
    """解析 version.md §1「说明」行的「最近已发布 = X.Y.Z」。

    返回 (version, 行原文, 失败原因)：
      - version 非 None ⇒ 解析成功（失败原因为 None）；
      - version 为 None ⇒ 解析失败（失败原因说明缺什么，供 detail 直接展示）。

    设计要点（task-167）：**解析失败必须能被上层判 FAIL**——否则下次有人改措辞，
    这条断言就静默失效，等于没有。因此这里不返回"跳过/未知"，只返回"解析到/为什么解析不到"。
    """
    if not text:
        return None, None, "version.md 缺失或读不到"
    row_m = NOTE_ROW.search(text)
    if not row_m:
        return None, None, "找不到「说明」行（期望表格行 `| 说明 | 最近已发布 = X.Y.Z（…） |`）"
    row = row_m.group(1).strip()
    m = NOTE_PUBLISHED.search(row)
    if not m:
        return None, row, ("「说明」行里无法解析「最近已发布 = X.Y.Z」"
                           "（需保留该短语与版本号；措辞改变会被判 FAIL 而不是跳过）")
    return m.group(1), row, None


def eval_version_note_published(tag: str, root: Path) -> dict:
    """检查 7（仅审计模式）：version.md「说明」行的最近已发布版本 == 本次 tag 版本。

    为什么读**工作区** version.md 而不是 tag 提交里的版本：
      v0.4.9 的 tag 提交里「说明」行写的是「最近已发布 = 0.4.8」——那正是今天被发现的错误。
      若读 tag 提交，等于把"发布当时就错的文档"当作正确基准，会放过本次要抓的缺陷。
      工作区 version.md 才是人（todo-owner）实际读到、会据此排期的那份文档。
    """
    try:
        tv = tag_version(tag)
    except ValueError as exc:
        return {"id": "VERSION-NOTE-PUBLISHED", "level": "FAIL", "detail": str(exc)}

    docs_path = root / "docs" / "conventions" / "version.md"
    text = _read_text(docs_path)
    doc_v, row, why = _parse_docs_note_version(text)
    if doc_v is None:
        snippet = f"；行原文：{row[:160]!r}" if row else ""
        return {"id": "VERSION-NOTE-PUBLISHED", "level": "FAIL",
                "detail": f"{why}{snippet}。解析失败按 FAIL 处理（防格式漂移后静默跳过）；"
                          f"本次 tag={tag}"}
    if doc_v != tv:
        return {"id": "VERSION-NOTE-PUBLISHED", "level": "FAIL",
                "detail": f"version.md §1「说明」行写 最近已发布 = {doc_v!r}，"
                          f"但本次 tag = {tag!r}（版本 {tv!r}）——文档与实际发布不一致，"
                          f"会误导排期/核对；请先把「说明」行更新为 {tv}"
                          f"（行原文：{row[:160]!r}）"}
    return {"id": "VERSION-NOTE-PUBLISHED", "level": "PASS",
            "detail": f"version.md §1「说明」行：最近已发布 = {doc_v!r} == tag {tag!r}"}


def _git_show(root: Path, ref: str, rel_path: str) -> str | None:
    try:
        proc = subprocess.run(["git", "show", f"{ref}:{rel_path}"], cwd=root,
                              capture_output=True, text=True, timeout=20,
                              encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def eval_version_three_way(tag: str, root: Path, mode: str) -> dict:
    """检查 5：tag / __version__.py / Package/VERSION / version.md §1 一致。

    mode='release'：读工作区（Package/VERSION 是构建产物，必须已存在）；
    mode='audit'：从 tag 提交的 git 对象读已跟踪文件（Package/VERSION 未入库 ⇒ 显式说明）。
    """
    try:
        tv = tag_version(tag)
    except ValueError as exc:
        return {"id": "VERSION-THREE-WAY", "level": "FAIL", "detail": str(exc)}

    if mode == "audit":
        repo_txt = _git_show(root, tag, "src/memoria/__version__.py")
        docs_txt = _git_show(root, tag, "docs/conventions/version.md")
        if repo_txt is None and docs_txt is None:
            return {"id": "VERSION-THREE-WAY", "level": "SKIP",
                    "detail": f"本地无 tag {tag} 的 git 对象，无法从发布提交核验版本文件（未判定，不算通过）"}
        repo_v = _parse_version_py(repo_txt)
        docs_v = _parse_docs_version(docs_txt)
        bad = []
        if repo_v != tv:
            bad.append(f"tag 提交内 src/memoria/__version__.py = {repo_v!r}，期望 {tv!r}")
        if docs_v != tv:
            bad.append(f"tag 提交内 version.md §1 = {docs_v!r}，期望 {tv!r}")
        if bad:
            return {"id": "VERSION-THREE-WAY", "level": "FAIL", "detail": "；".join(bad)}
        return {"id": "VERSION-THREE-WAY", "level": "PASS",
                "detail": f"tag {tag} 提交内 __version__.py={repo_v!r}、version.md §1={docs_v!r} 一致；"
                          f"Package/VERSION 未入库，无法从提交核验（已显式说明）"}

    repo_v = _parse_version_py(_read_text(root / "src" / "memoria" / "__version__.py"))
    docs_v = _parse_docs_version(_read_text(root / "docs" / "conventions" / "version.md"))
    pkg_txt = _read_text(root / "Package" / "VERSION")
    pkg_v = pkg_txt.strip() if pkg_txt is not None else None
    values = {"tag": tv, "__version__.py": repo_v, "version.md §1": docs_v, "Package/VERSION": pkg_v}
    bad = []
    for name, value in values.items():
        if value is None:
            bad.append(f"{name} 缺失/读不到")
        elif value != tv:
            bad.append(f"{name} = {value!r}，期望 {tv!r}")
    shown = ", ".join(f"{k}={v!r}" for k, v in values.items())
    if bad:
        return {"id": "VERSION-THREE-WAY", "level": "FAIL",
                "detail": "；".join(bad) + f"。实测：{shown}"}
    return {"id": "VERSION-THREE-WAY", "level": "PASS", "detail": f"四处一致：{shown}"}


def eval_assets(tag: str, release_meta: dict | None, offline: bool) -> dict:
    if release_meta is None:
        return {"id": "ASSETS-COUNT", "level": "SKIP",
                "detail": "无发布资产数据（发布前正常；发布后请用 --verify-published 核对）。"
                          "SKIP 不算通过"}
    assets = release_meta.get("assets") or []
    names = [str(a.get("name", "")) for a in assets]
    problems: list[str] = []
    warns: list[str] = []
    if len(assets) != 2:
        problems.append(f"资产数量 = {len(assets)}（要求 2：win64 完整包 + lite 轻量包）")
    full_pat = re.compile(rf"^Memoria-{re.escape(tag)}-win64\.zip$")
    lite_pat = re.compile(rf"^Memoria-{re.escape(tag)}-(?:win64-)?lite\.zip$")
    full = [n for n in names if full_pat.match(n)]
    lite = [n for n in names if lite_pat.match(n)]
    unknown = [n for n in names if not full_pat.match(n) and not lite_pat.match(n)]
    if unknown:
        problems.append(f"资产名不符合 {tag} 命名规范：{unknown}"
                        f"（期望 Memoria-{tag}-win64.zip + Memoria-{tag}-win64-lite.zip / -lite.zip）")
    if names and not full:
        problems.append(f"缺 win64 完整包（实际 {names}）")
    if names and not lite:
        problems.append(f"缺 lite 轻量包（实际 {names}）")
    if lite and not any("win64-lite" in n for n in lite):
        warns.append(f"lite 包名为 {lite}；canonical 是 `Memoria-{tag}-win64-lite.zip`"
                     f"（v0.4.7–v0.5.0 历史漂移命名，已发布不改名；新发布按 canonical，仅告警）")
    if problems:
        return {"id": "ASSETS-COUNT", "level": "FAIL", "detail": "；".join(problems)}
    level = "WARN" if warns else "PASS"
    detail = f"2/2 资产成对：{names}"
    if warns:
        detail += "；" + "；".join(warns)
    return {"id": "ASSETS-COUNT", "level": level, "detail": detail}


def _repo_slug(root: Path) -> str:
    try:
        proc = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                              capture_output=True, text=True, timeout=10)
        url = proc.stdout.strip()
        m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return DEFAULT_REPO_SLUG


def _http_json(url: str, timeout: int = 25) -> dict | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "memoria-release-preflight",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (固定 https URL)
        return json.loads(resp.read().decode("utf-8"))


def fetch_release_meta(tag: str, root: Path) -> dict | None:
    slug = _repo_slug(root)
    url = f"https://api.github.com/repos/{slug}/releases/tags/{tag}"
    try:
        return _http_json(url)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _git_ls_remote(root: Path, tag: str) -> tuple[str, str | None, str]:
    """返回 (status, sha, detail)；status ∈ ok|absent|error。"""
    try:
        proc = subprocess.run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
                              cwd=root, capture_output=True, text=True, timeout=25,
                              encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as exc:
        return "error", None, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        return "error", None, msg[-1] if msg else f"exit={proc.returncode}"
    out = proc.stdout.strip()
    if not out:
        return "absent", None, "ls-remote 无该 tag"
    sha = out.split()[0]
    return "ok", sha, f"ls-remote 可见 {tag} → {sha}"


def _api_tag_sha(tag: str, root: Path) -> tuple[str, str | None, str]:
    slug = _repo_slug(root)
    url = f"https://api.github.com/repos/{slug}/git/refs/tags/{tag}"
    try:
        data = _http_json(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "absent", None, "GitHub API 404（tag 不存在）"
        return "error", None, f"GitHub API HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return "error", None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return "error", None, "GitHub API 返回非对象"
    obj = data.get("object") or {}
    return "ok", obj.get("sha"), f"GitHub API 可见 {tag} → {obj.get('sha')}"


def eval_tag_remote(tag: str, root: Path, offline: bool, phase: str,
                    release_meta: dict | None = None) -> dict:
    """检查 6：phase=post 要求远端 tag 存在；phase=pre 要求不存在。"""
    local = None
    try:
        proc = subprocess.run(["git", "tag", "-l", tag], cwd=root,
                              capture_output=True, text=True, timeout=10)
        local = proc.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass

    if offline:
        return {"id": "TAG-REMOTE" if phase == "post" else "TAG-NOT-EXISTS", "level": "SKIP",
                "detail": f"--offline：跳过远端 tag 核验（本地 tag={local or '无'}）。"
                          f"SKIP 不算通过"}

    status, sha, detail = _git_ls_remote(root, tag)
    if status == "error":
        status2, sha2, detail2 = _api_tag_sha(tag, root)
        if status2 in ("ok", "absent"):
            status, sha, detail = status2, sha2, f"{detail2}（ls-remote 不可用：{detail}）"
        else:
            return {"id": "TAG-REMOTE" if phase == "post" else "TAG-NOT-EXISTS", "level": "SKIP",
                    "detail": f"远端不可达，无法判定 tag 是否存在（ls-remote: {detail}；"
                              f"API: {detail2}）。SKIP 不算通过"}

    exists = status in ("ok", "absent") and status == "ok"
    if phase == "pre":
        if exists:
            return {"id": "TAG-NOT-EXISTS", "level": "FAIL",
                    "detail": f"发版前远端 tag {tag} 已存在（{detail}）——覆盖已发布版本危险；"
                              f"先升版本号，不要复用 tag"}
        return {"id": "TAG-NOT-EXISTS", "level": "PASS",
                "detail": f"发版前远端 tag {tag} 尚不存在（{detail}）"}
    if not exists:
        return {"id": "TAG-REMOTE", "level": "FAIL",
                "detail": f"远端 tag {tag} 不存在（{detail}）——先 push tag 再建 Release"}
    if release_meta is not None:
        meta_tag = release_meta.get("tag_name")
        if meta_tag and meta_tag != tag:
            return {"id": "TAG-REMOTE", "level": "FAIL",
                    "detail": f"Release JSON tag_name={meta_tag!r} 与目标 tag {tag!r} 不一致"}
    # 远端 sha 与本地 tag 对象比对（辅助信号：tag 被覆盖/本地 tag 过期）
    local_obj = None
    try:
        proc = subprocess.run(["git", "rev-parse", tag], cwd=root, capture_output=True,
                              text=True, timeout=10, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            local_obj = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    if sha and local_obj and local_obj != sha:
        return {"id": "TAG-REMOTE", "level": "WARN",
                "detail": f"{detail}；但本地 tag 对象 {local_obj[:12]} 与远端 {sha[:12]} 不同"
                          f"（本地 tag 可能过期/被重建，发布前请确认）"}
    return {"id": "TAG-REMOTE", "level": "PASS", "detail": detail}


def run_release_checks(cfg: dict) -> tuple[list[dict], dict]:
    """release / audit 两种模式的检查集合。返回 (checks, metrics)。"""
    tag = cfg["tag"]
    root: Path = cfg["root"]
    mode = cfg.get("mode", "release")
    title = cfg.get("title") or ""
    body = cfg.get("body") or ""
    checks: list[dict] = [eval_title(tag, title)]
    body_checks, metrics = eval_body(body)
    checks += body_checks
    checks += eval_cost(body)
    checks.append(eval_assets(tag, cfg.get("release_meta"), cfg.get("offline", False)))
    checks.append(eval_version_three_way(tag, root, mode))
    if mode == "audit":
        # 检查 7 只在发布后审计跑：见 eval_version_note_published / 报告「接入点理由」
        checks.append(eval_version_note_published(tag, root))
    checks.append(eval_tag_remote(tag, root, cfg.get("offline", False),
                                  cfg.get("phase", "post"), cfg.get("release_meta")))

    if mode == "release":
        # 复用 ① 的 review artifact 检查（语义不变）；剔除被 ② 取代的两项
        try:
            legacy = check(tag_version(tag), Path(cfg["review_dir"]))
        except ValueError:
            legacy = []
        keep = [c for c in legacy if c["id"] in ("SUPERVISOR-REVIEW", "DECISION-TRAIL")]
        if not cfg.get("require_review", False) or cfg.get("allow_missing_review", False):
            for c in keep:
                if c["id"] == "SUPERVISOR-REVIEW" and c["level"] == "FAIL":
                    c["level"] = "WARN"
                    c["detail"] = ("[未启用硬门禁] " + c["detail"]
                                   + "（加 --require-review 可升级为 FAIL）")
        checks += keep
    return checks, metrics


def summarize(checks: list[dict]) -> dict:
    failed = [c for c in checks if c["level"] == "FAIL"]
    skipped = [c for c in checks if c["level"] == "SKIP"]
    warned = [c for c in checks if c["level"] == "WARN"]
    return {"ok": not failed, "failed": [c["id"] for c in failed],
            "skipped": [c["id"] for c in skipped], "warned": [c["id"] for c in warned]}


def _print_checks(header: str, checks: list[dict], metrics: dict | None, as_json: bool,
                  payload_extra: dict | None = None) -> int:
    summary = summarize(checks)
    if as_json:
        out = {"header": header, "checks": checks, "metrics": metrics or {}, **summary}
        if payload_extra:
            out.update(payload_extra)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if summary["ok"] else 1

    print(header)
    for c in checks:
        print(f"  [{c['level']:4}] {c['id']}: {c['detail']}")
    if metrics:
        print(f"  正文口径：EN 块 {metrics.get('en_block_chars')} 字符 / "
              f"ZH 块 {metrics.get('zh_block_chars')} 字符（去标题/分隔线/空行）")
    if summary["ok"]:
        if summary["skipped"]:
            print(f"结论：PASS-WITH-SKIPS（{len(checks)} 项检查，"
                  f"{len(summary['skipped'])} 项 SKIP：{', '.join(summary['skipped'])}；"
                  f"SKIP 不算通过，需人工确认）")
        else:
            print(f"结论：PASS（{len(checks)} 项全过，可继续发版）")
        if summary["warned"]:
            print(f"  告警：{', '.join(summary['warned'])}")
        return 0
    print(f"结论：FAIL（{len(summary['failed'])} 项阻断：{', '.join(summary['failed'])}）"
          f"—— 不得发布")
    return 1


# ══════════════════════════════════════════════════════════════════════
# ② selftest：每条规则都有「必红」fixture（改坏 ⇒ FAIL ⇒ 还原 ⇒ PASS）
# ══════════════════════════════════════════════════════════════════════

SELFTEST_TAG = "v9.9.9"
SELFTEST_TITLE = "Memoria v9.9.9"
SELFTEST_NOTE_ROW = "| 说明 | 最近已发布 = **9.9.9**（2026-10-25，tag `v9.9.9` → `deadbeef`） |"


def _fixture_version_md(note_row: str | None, current: str = "9.9.9") -> str:
    """构造最小 version.md（§1 表格）；note_row=None ⇒ 故意不写「说明」行。"""
    lines = [
        "# 版本规范",
        "",
        "## 1. 当前版本",
        "",
        "| 项 | 值 |",
        "|----|----|",
        f"| 当前版本 | **{current}** |",
    ]
    if note_row is not None:
        lines.append(note_row)
    lines += ["| 版本阶段 | 0.x（未稳定，接口可变更） |"]
    return "\n".join(lines) + "\n"
SELFTEST_BODY = """# Memoria v9.9.9

## English

This fixture release adds a machine-checked release gate. The gate validates that
the title is exactly the version string, that the body is bilingual with English
before Chinese, and that the cost section states a magnitude and an accounting
basis. It runs offline; network-dependent checks are reported as skipped and are
never counted as passed.

## Cost (Agent compute)

- **Magnitude**: roughly **CNY 100-200** (estimate, not itemised).
- **Accounting basis**: this fixture is counted as one block.
- **Cost structure (one line)**: most of the spend went to repeatable verification.

---

## 中文

本 fixture 用来证明发版门禁真的会拒绝违规：标题必须严格等于版本号字符串，正文必须
英文在前、中文在后，且必须包含造价段（量级 + 统计口径 + 成本结构）。检查器可离线运行，
联网项会显式标记为 skipped，skipped 不算通过；任何一条硬规则不满足都必须 exit 1。
另外，中文段主内容必须与英文段同量级完整，不能只留一句摘要然后靠造价段凑长度，
这正是本 fixture 要守住的边界：stub 判定只看语言主内容，造价段另算。

## 造价（Agent 算力）

- **量级**：约 **100–200 元人民币**（估算，非逐项计量）。
- **统计口径**：本 fixture 合并统计，仅用于自证。
- **成本结构（一句话）**：主要花在可重复验证上。
"""


def _fixture_env(tmp: Path, note_row: str | None = SELFTEST_NOTE_ROW) -> dict:
    """建一个最小临时仓库（含 origin bare remote）+ 合规正文/审查/发布数据。

    note_row：version.md §1「说明」行内容；None ⇒ 不写该行（用于"无法解析必红" fixture）。
    """
    root = tmp / "repo"
    (root / "src" / "memoria").mkdir(parents=True)
    (root / "docs" / "conventions").mkdir(parents=True)
    (root / "Package").mkdir(parents=True)
    (root / "src" / "memoria" / "__version__.py").write_text(
        '__version__ = "9.9.9"\n', encoding="utf-8")
    (root / "docs" / "conventions" / "version.md").write_text(
        _fixture_version_md(note_row), encoding="utf-8")
    (root / "Package" / "VERSION").write_text("9.9.9\n", encoding="utf-8")

    def git(*args: str, cwd: Path = root) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              text=True, timeout=30, encoding="utf-8", errors="replace")

    git("init", "-q")
    git("config", "user.email", "selftest@example.invalid")
    git("config", "user.name", "release-preflight-selftest")
    git("add", "-A")
    git("commit", "-q", "-m", "fixture")
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], capture_output=True, timeout=30)
    git("remote", "add", "origin", str(bare))

    review_dir = tmp / "supervisor"
    review_dir.mkdir()
    (review_dir / "review.md").write_text(
        "version: 9.9.9\nreviewer: fixture\nverdict: pass\n"
        "evidence: artifacts/agent/verify/fixture.md\n", encoding="utf-8")
    meta = {
        "tag_name": SELFTEST_TAG,
        "name": SELFTEST_TITLE,
        "body": SELFTEST_BODY,
        "assets": [
            {"name": "Memoria-v9.9.9-win64.zip"},
            {"name": "Memoria-v9.9.9-win64-lite.zip"},
        ],
    }
    return {"root": root, "bare": bare, "review_dir": review_dir, "meta": meta,
            "git": git}


def _cfg(env: dict, **overrides) -> dict:
    cfg = {
        "tag": SELFTEST_TAG,
        "title": SELFTEST_TITLE,
        "body": SELFTEST_BODY,
        "root": env["root"],
        "review_dir": env["review_dir"],
        "mode": "release",
        "phase": "post",
        "offline": False,
        "release_meta": env["meta"],
        "require_review": True,
    }
    cfg.update(overrides)
    return cfg


def _push_tag(env: dict, tag: str = SELFTEST_TAG) -> None:
    env["git"]("tag", "-a", tag, "-m", "fixture tag")
    env["git"]("push", "-q", "origin", tag)


def selftest_release() -> list[tuple[str, bool]]:
    results: list[tuple[str, bool]] = []
    tmp = Path(tempfile.mkdtemp(prefix="release-preflight-release-selftest-"))
    try:
        env = _fixture_env(tmp)
        _push_tag(env)

        def levels(cfg: dict) -> dict:
            checks, metrics = run_release_checks(cfg)
            return {"checks": checks, "metrics": metrics,
                    "levels": {c["id"]: c["level"] for c in checks},
                    "summary": summarize(checks)}

        # ── 合规基线：必须全 PASS（exit 0） ──
        base = levels(_cfg(env))
        results.append(("② 合规基线 exit 0（全部非 FAIL）", base["summary"]["ok"]))
        results.append(("② 合规基线标题 PASS", base["levels"].get("TITLE-EXACT") == "PASS"))
        results.append(("② 合规基线双语 PASS", base["levels"].get("BODY-BILINGUAL") == "PASS"))
        results.append(("② 合规基线造价 PASS", base["levels"].get("COST-SECTION") == "PASS"))
        results.append(("② 合规基线资产 PASS", base["levels"].get("ASSETS-COUNT") == "PASS"))
        results.append(("② 合规基线版本三查 PASS", base["levels"].get("VERSION-THREE-WAY") == "PASS"))
        results.append(("② 合规基线 tag post PASS", base["levels"].get("TAG-REMOTE") == "PASS"))

        # ── 检查 1：标题必红（复现 v0.4.7/0.4.8/0.5.0 的真实违规形态） ──
        for name, bad_title in [
            ("② 检查1 副标题（—— 收摊）必红",
             "Memoria v9.9.9 —— 收摊"),
            ("② 检查1 英文副标题必红",
             "Memoria v9.9.9 - agent capability architecture (S1-S5)"),
            ("② 检查1 后缀必红", "Memoria v9.9.9 (hotfix)"),
        ]:
            r = levels(_cfg(env, title=bad_title))
            results.append((name, r["levels"].get("TITLE-EXACT") == "FAIL"
                            and not r["summary"]["ok"]))
        # 还原后必须重新 PASS
        results.append(("② 检查1 还原后 PASS",
                        levels(_cfg(env))["levels"].get("TITLE-EXACT") == "PASS"))

        # ── 检查 2：双语结构必红 ──
        lines = SELFTEST_BODY.split("\n")
        iz = lines.index("## 中文")
        ie = lines.index("## English")
        head = lines[:ie]
        en_part = lines[ie:iz]
        zh_part = lines[iz:]
        swapped = "\n".join(head + zh_part + [""] + en_part)
        r = levels(_cfg(env, body=swapped))
        results.append(("② 检查2 中文在前必红", r["levels"].get("BODY-BILINGUAL") == "FAIL"))

        stub_body = SELFTEST_BODY.replace(
            "This fixture release adds a machine-checked release gate. The gate validates that\n"
            "the title is exactly the version string, that the body is bilingual with English\n"
            "before Chinese, and that the cost section states a magnitude and an accounting\n"
            "basis. It runs offline; network-dependent checks are reported as skipped and are\n"
            "never counted as passed.",
            "Short stub.")
        assert stub_body != SELFTEST_BODY
        r = levels(_cfg(env, body=stub_body))
        results.append(("② 检查2 英文 stub 必红", r["levels"].get("BODY-BILINGUAL") == "FAIL"))

        no_en = SELFTEST_BODY.replace("## English", "## Intro")
        r = levels(_cfg(env, body=no_en))
        results.append(("② 检查2 缺英文段必红", r["levels"].get("BODY-BILINGUAL") == "FAIL"))
        results.append(("② 检查2 还原后 PASS",
                        levels(_cfg(env))["levels"].get("BODY-BILINGUAL") == "PASS"))

        # ── 检查 3：造价段必红 ──
        no_cost_zh = SELFTEST_BODY[:SELFTEST_BODY.index("## 造价（Agent 算力）")]
        r = levels(_cfg(env, body=no_cost_zh))
        results.append(("② 检查3 缺中文造价段必红", r["levels"].get("COST-SECTION") == "FAIL"))

        no_mag = SELFTEST_BODY.replace("约 **100–200 元人民币**", "约 **100–200**")
        assert no_mag != SELFTEST_BODY
        r = levels(_cfg(env, body=no_mag))
        results.append(("② 检查3 无量级必红", r["levels"].get("COST-SECTION") == "FAIL"))

        no_basis = SELFTEST_BODY.replace(
            "- **统计口径**：本 fixture 合并统计，仅用于自证。", "- **统计说明**：仅用于自证。")
        assert no_basis != SELFTEST_BODY
        r = levels(_cfg(env, body=no_basis))
        results.append(("② 检查3 无统计口径必红", r["levels"].get("COST-SECTION") == "FAIL"))

        no_cost_en = SELFTEST_BODY.replace("## Cost (Agent compute)", "## Cost")
        r = levels(_cfg(env, body=no_cost_en))
        results.append(("② 检查3 缺英文造价段必红", r["levels"].get("COST-SECTION") == "FAIL"))
        results.append(("② 检查3 还原后 PASS",
                        levels(_cfg(env))["levels"].get("COST-SECTION") == "PASS"))

        # ── 检查 5：版本三查必红 ──
        (env["root"] / "src" / "memoria" / "__version__.py").write_text(
            '__version__ = "9.9.8"\n', encoding="utf-8")
        r = levels(_cfg(env))
        results.append(("② 检查5 __version__.py 不符必红",
                        r["levels"].get("VERSION-THREE-WAY") == "FAIL"))
        (env["root"] / "src" / "memoria" / "__version__.py").write_text(
            '__version__ = "9.9.9"\n', encoding="utf-8")
        (env["root"] / "Package" / "VERSION").write_text("9.9.8\n", encoding="utf-8")
        r = levels(_cfg(env))
        results.append(("② 检查5 Package/VERSION 不符必红",
                        r["levels"].get("VERSION-THREE-WAY") == "FAIL"))
        (env["root"] / "Package" / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        r = levels(_cfg(env))
        results.append(("② 检查5 还原后 PASS",
                        r["levels"].get("VERSION-THREE-WAY") == "PASS"))

        # ── 检查 4：资产数必红（用合成 Release JSON） ──
        one = dict(env["meta"])
        one["assets"] = [{"name": "Memoria-v9.9.9-win64.zip"}]
        r = levels(_cfg(env, release_meta=one))
        results.append(("② 检查4 资产数量=1 必红", r["levels"].get("ASSETS-COUNT") == "FAIL"))
        bad_name = dict(env["meta"])
        bad_name["assets"] = [{"name": "Memoria-v9.9.9-win64.zip"},
                              {"name": "Memoria-v9.9.9.zip"}]
        r = levels(_cfg(env, release_meta=bad_name))
        results.append(("② 检查4 资产名不符必红", r["levels"].get("ASSETS-COUNT") == "FAIL"))
        r = levels(_cfg(env, release_meta=None))
        results.append(("② 检查4 无数据 SKIP（不算 FAIL）",
                        r["levels"].get("ASSETS-COUNT") == "SKIP" and r["summary"]["ok"]))

        # ── 检查 6：tag 必红/必绿 ──
        env2 = _fixture_env(tmp / "env2")
        r = levels(_cfg(env2))
        results.append(("② 检查6 post 远端无 tag 必红", r["levels"].get("TAG-REMOTE") == "FAIL"))
        env2["git"]("tag", "-a", SELFTEST_TAG, "-m", "x")
        env2["git"]("push", "-q", "origin", SELFTEST_TAG)
        r = levels(_cfg(env2))
        results.append(("② 检查6 post 远端有 tag 必绿", r["levels"].get("TAG-REMOTE") == "PASS"))
        r = levels(_cfg(env2, phase="pre"))
        results.append(("② 检查6 pre 远端有 tag 必红", r["levels"].get("TAG-NOT-EXISTS") == "FAIL"))
        r = levels(_cfg(env2, offline=True))
        results.append(("② 检查6 offline SKIP（不算通过）",
                        r["levels"].get("TAG-REMOTE") == "SKIP"
                        and r["levels"].get("TAG-REMOTE") != "PASS"))

        # ── 检查 7：version.md「说明」行 vs tag（仅 audit/verify-published 模式） ──
        def audit_levels(env_: dict, **overrides) -> dict:
            return levels(_cfg(env_, mode="audit", require_review=False, **overrides))

        def write_note(env_: dict, note_row: str | None) -> None:
            (env_["root"] / "docs" / "conventions" / "version.md").write_text(
                _fixture_version_md(note_row), encoding="utf-8")

        r = audit_levels(env)
        results.append(("② 检查7 正常态（说明行=tag）必绿",
                        r["levels"].get("VERSION-NOTE-PUBLISHED") == "PASS"
                        and r["summary"]["ok"]))

        # 发布模式不跑该检查（只在 verify-published 阶段有意义）
        results.append(("② 检查7 发布模式不含该检查",
                        "VERSION-NOTE-PUBLISHED" not in levels(_cfg(env))["levels"]))

        # 说明行写旧版本、tag 更新 ⇒ 必红（复现今天真实错误：tag v0.4.9、说明写 0.4.8）
        write_note(env, "| 说明 | 最近已发布 = **9.9.8**（旧版本 fixture） |")
        r = audit_levels(env)
        note = next(c for c in r["checks"] if c["id"] == "VERSION-NOTE-PUBLISHED")
        results.append(("② 检查7 说明行写旧版本必红",
                        note["level"] == "FAIL" and not r["summary"]["ok"]))
        results.append(("② 检查7 必红 detail 同时给出两侧实际值",
                        "9.9.8" in note["detail"] and "v9.9.9" in note["detail"]))
        write_note(env, SELFTEST_NOTE_ROW)
        results.append(("② 检查7 不一致后还原必绿",
                        audit_levels(env)["levels"].get("VERSION-NOTE-PUBLISHED") == "PASS"))

        # 说明行格式改成无法解析 ⇒ 必红（不许静默跳过）
        write_note(env, "| 说明 | 最近发布：见变更记录 |")
        r = audit_levels(env)
        note = next(c for c in r["checks"] if c["id"] == "VERSION-NOTE-PUBLISHED")
        results.append(("② 检查7 说明行不可解析必红",
                        note["level"] == "FAIL" and not r["summary"]["ok"]))
        results.append(("② 检查7 不可解析 detail 明确写「无法解析」",
                        "无法解析" in note["detail"]))
        write_note(env, SELFTEST_NOTE_ROW)
        results.append(("② 检查7 不可解析后还原必绿",
                        audit_levels(env)["levels"].get("VERSION-NOTE-PUBLISHED") == "PASS"))

        # 整行缺失 ⇒ 必红（不是跳过）
        env_missing = _fixture_env(tmp / "env-note-missing", note_row=None)
        _push_tag(env_missing)
        r = audit_levels(env_missing)
        note = next(c for c in r["checks"] if c["id"] == "VERSION-NOTE-PUBLISHED")
        results.append(("② 检查7 缺「说明」行必红",
                        note["level"] == "FAIL" and "找不到" in note["detail"]))

        # 读的是【工作区】文档而不是 tag 提交：tag 提交里写旧版本、工作区修正后必须绿
        env_stale_commit = _fixture_env(
            tmp / "env-note-stale-commit",
            note_row="| 说明 | 最近已发布 = **9.9.8**（tag 提交里是旧值） |")
        _push_tag(env_stale_commit)
        r = audit_levels(env_stale_commit)
        results.append(("② 检查7 基线（tag 提交旧值）必红",
                        r["levels"].get("VERSION-NOTE-PUBLISHED") == "FAIL"))
        write_note(env_stale_commit, SELFTEST_NOTE_ROW)  # 只改工作区、不 commit/tag
        r = audit_levels(env_stale_commit)
        results.append(("② 检查7 只修工作区即可绿（证明读工作区，不读 tag 提交）",
                        r["levels"].get("VERSION-NOTE-PUBLISHED") == "PASS"))

        # ── 输出格式/退出码：失败汇总必须 ok=False ──
        r = levels(_cfg(env, title="Memoria v9.9.9 —— x"))
        results.append(("② FAIL 时 summary.ok=False", r["summary"]["ok"] is False))
        results.append(("② FAIL 时 failed 列表含 TITLE-EXACT",
                        r["summary"]["failed"] == ["TITLE-EXACT"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def selftest() -> int:
    print("SELFTEST（发版门禁：每条硬规则都必须有『必红』fixture）")
    results = selftest_legacy() + selftest_release()
    ok = all(passed for _, passed in results)
    for name, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print("SELFTEST " + ("PASS" if ok else "FAIL") + f"（{len(results)} 项）")
    return 0 if ok else 1


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════


def _legacy_main(args: argparse.Namespace) -> int:
    """旧用法：仅 review artifact / 版本一致性检查（① 语义不变）。"""
    version = args.version or read_repo_version()
    if not version:
        print("FAIL: 无法确定版本（--version 未给且读不到 __version__.py）", file=sys.stderr)
        return 1
    checks = check(version, Path(args.review_dir))
    failed = [c for c in checks if c["level"] == "FAIL"]
    if args.json:
        print(json.dumps({"version": version, "checks": checks, "ok": not failed},
                         ensure_ascii=False, indent=2))
    else:
        print(f"发版前置检查（legacy review 模式）：version={version}")
        for c in checks:
            print(f"  [{c['level']:4}] {c['id']}: {c['detail']}")
        print("结论：" + ("PASS（可继续发版）" if not failed else f"FAIL（{len(failed)} 项阻断）"))
    return 0 if not failed else 1


def _load_release_json(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"用法错误：--release-json 读取失败：{exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("用法错误：--release-json 必须是 GitHub Release 对象（JSON object）")
    return data


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="发版前置检查：GitHub Release 三条硬规则 + 版本三查 + tag/资产 + supervisor 审查")
    ap.add_argument("--tag", help="发布标识 tag（vX.Y.Z）；release/audit 模式必需（或 --version 降级合成）")
    ap.add_argument("--version", help="仓库版本 X.Y.Z；缺省读 src/memoria/__version__.py")
    ap.add_argument("--title", help="GitHub Release 标题（release 模式必需）")
    ap.add_argument("--body-file", help="GitHub Release 正文文件路径（release 模式必需）")
    ap.add_argument("--review-dir", default=str(DEFAULT_REVIEW_DIR), help="审查 artifact 目录")
    ap.add_argument("--require-review", action="store_true",
                    help="release 模式下把缺失 supervisor 审查升级为 FAIL（默认 WARN）")
    ap.add_argument("--allow-missing-review", action="store_true",
                    help="仅在 supervisor 已就绪需临时降级时使用（为翻转后的默认 FAIL 预留）")
    ap.add_argument("--phase", choices=["pre", "post"], default="post",
                    help="pre=发版前（远端 tag 必须不存在）；post=发布后（远端 tag 必须存在，默认）")
    ap.add_argument("--offline", action="store_true",
                    help="跳过联网项（远端 tag / 发布资产），显式标记 SKIP；SKIP 不算通过")
    ap.add_argument("--verify-published", action="store_true",
                    help="发布后审计模式：从 GitHub Release JSON 核对实际标题/正文/资产")
    ap.add_argument("--release-json", help="离线回放 GitHub Release JSON（配合 --verify-published）")
    ap.add_argument("--repo-root", help="仓库根目录（默认本文件所在仓库；测试 fixture 用）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--selftest", action="store_true", help="自证红/绿（临时 fixture，离线）")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    root = Path(args.repo_root).resolve() if args.repo_root else ROOT
    review_dir = Path(args.review_dir)

    # 发布后审计模式
    if args.verify_published:
        if not args.tag:
            ap.error("--verify-published 需要 --tag vX.Y.Z")
        try:
            tag = normalize_tag(args.tag)
            tag_version(tag)
        except ValueError as exc:
            ap.error(str(exc))
        meta = _load_release_json(args.release_json) if args.release_json else None
        if meta is None:
            if args.offline:
                ap.error("--verify-published --offline 需要 --release-json（离线回放）")
            meta = fetch_release_meta(tag, root)
            if meta is None:
                checks = [{"id": "RELEASE-DATA", "level": "SKIP",
                           "detail": "无法取得 GitHub Release 数据（网络失败）；未判定，不算通过"}]
                return _print_checks(f"发布后审计：{tag}", checks, None, args.json,
                                     {"mode": "audit", "tag": tag})
        title = meta.get("name") or ""
        body = meta.get("body") or ""
        cfg = {"tag": tag, "title": title, "body": body, "root": root, "mode": "audit",
               "phase": "post", "offline": args.offline, "release_meta": meta,
               "review_dir": review_dir, "require_review": False}
        checks, metrics = run_release_checks(cfg)
        return _print_checks(f"发布后审计（GitHub 实际状态）：tag={tag}", checks, metrics,
                             args.json, {"mode": "audit", "tag": tag,
                                         "release_url": meta.get("html_url")})

    # 发版模式：--title/--body-file/--tag 任一出现即进入
    release_mode = bool(args.tag or args.title or args.body_file)
    if not release_mode:
        return _legacy_main(args)

    if not args.body_file:
        ap.error("release 模式需要 --body-file <path>")
    body_path = Path(args.body_file)
    body = _read_text(body_path)
    if body is None:
        ap.error(f"用法错误：读不到 --body-file {body_path}")

    tag = None
    warn_synthesized = False
    if args.tag:
        try:
            tag = normalize_tag(args.tag)
            tag_version(tag)
        except ValueError as exc:
            ap.error(str(exc))
    else:
        version = args.version or read_repo_version()
        if not version:
            ap.error("缺 --tag，且无法从 src/memoria/__version__.py 读到 --version")
        tag = normalize_tag(version)
        warn_synthesized = True
    if not args.title:
        ap.error("release 模式需要 --title \"Memoria vX.Y.Z\"")

    checks, metrics = None, None
    cfg = {"tag": tag, "title": args.title, "body": body, "root": root, "mode": "release",
           "phase": args.phase, "offline": args.offline, "release_meta": None,
           "review_dir": review_dir, "require_review": args.require_review,
           "allow_missing_review": args.allow_missing_review}
    checks, metrics = run_release_checks(cfg)
    if warn_synthesized:
        checks.append({"id": "TAG-SYNTHESIZED", "level": "WARN",
                       "detail": f"未传 --tag，按 --version 合成 {tag}（发版事实应以 tag 为准）"})
    if args.release_json:
        meta = _load_release_json(args.release_json)
        checks = [c for c in checks if c["id"] != "ASSETS-COUNT"]
        checks.append(eval_assets(tag, meta, args.offline))
        checks = sorted(checks, key=lambda c: ["TITLE-EXACT", "BODY-BILINGUAL", "COST-SECTION",
                                                "ASSETS-COUNT", "VERSION-THREE-WAY",
                                                "VERSION-NOTE-PUBLISHED",
                                                "TAG-REMOTE", "TAG-NOT-EXISTS"].index(c["id"])
                        if c["id"] in ["TITLE-EXACT", "BODY-BILINGUAL", "COST-SECTION",
                                       "ASSETS-COUNT", "VERSION-THREE-WAY",
                                       "VERSION-NOTE-PUBLISHED",
                                       "TAG-REMOTE", "TAG-NOT-EXISTS"] else 99)
    return _print_checks(f"发版前置检查（release 模式，phase={args.phase}）：tag={tag}",
                         checks, metrics, args.json,
                         {"mode": "release", "tag": tag, "phase": args.phase})


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
