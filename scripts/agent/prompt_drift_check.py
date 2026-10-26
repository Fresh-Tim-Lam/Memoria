#!/usr/bin/env python3
"""知识库 Agent 提示词漂移机检（task-151）。

目的（唯一 KPI）：**下次代码改了行为而提示词没跟上时，本脚本必须 exit 1。**
不靠"提示词写得漂亮"，靠五类可复跑、可必红的检查：

  C1 distribution_integrity  分发完整性
     - `kb_agent.py` 的 FILE_MAP / REFERENCE_DOCS 每个源文件存在、非空、可解析；
     - README 声明的文件 = 实际分发的文件（双向）；
     - 提示词里写 `.memoria/agent/<名>` 必须是真实落点；
     - `resources/agent-prompts/**` 无"未归类的孤儿文件"（防隐藏分发路径）；
     - 打包白名单（packaging/build.py）覆盖每个分发源（防发布态"内置资源缺失"）。

  C2 symbol_reference        代码符号引用校验（本项目最有价值的一条）
     - 提示词反引号里的 工具名 / RPC 名 / 字段名 / 代码路径 / KB 路径 / 斜杠枚举，
       必须在代码或仓库里真实存在；
     - `fsrs.py` 子命令与 flag 必须与脚本 argparse 一致；
     - 未归类的 token 记 INFO（不静默放过，也不误红）。

  C3 forbidden_syntax        禁止教"会被代码剥离"的语法
     - 从 `edge_types.py` 读出已注册的 wikilink 边类型片段；
     - 从 `kb_build.py` 确认这些片段**真的**会被 strip；
     - 提示词若把它当推荐写法教（同一行无"遗留/剥离/不要"等限定词）⇒ FAIL；
     - 反向：代码不再剥离而提示词还说会剥离 ⇒ WARN（说明旧结论过期）。

  C4 version_stamp           版本戳 + 依赖指纹锁
     - 每个分发的提示词 md 头部有 `<!-- spec-version: X.Y.Z -->`，等于 `kb_agent.SPEC_VERSION`；
     - `<!-- spec-deps: path@sha12, ... -->` 里每个依赖存在且当前 sha256 前 12 位一致；
       **依赖一变就红**，强制"代码改了 ⇒ 提示词必须复核并重签指纹"；
     - `<!-- reviewed-on: YYYY-MM-DD -->`。

  C5 staleness               陈旧告警
     - reviewed-on 超过 N 天（默认 90）⇒ WARN；
     - 声明依赖的最近变更时间（git 提交时间优先，无 git 用 mtime）比 reviewed-on 新
       超过 N 天 ⇒ WARN（C4 指纹没变时才会走到这里）。

退出码（task-158/PD-1 起）：
  0 = 全部检查已执行且无 FAIL（可含 WARN/INFO）；
  1 = 有 FAIL（提示词漂移）；
  2 = **有检查未能执行**（NOT_RUN：输入不可读/依赖缺失/检查自身异常）——「跳过 ≠ 通过」；
  3 = 用法错误。
`--json` 的 `summary.status ∈ {ok, fail, not_run}` 与退出码一一对应；team_audit 对 not_run 判 FAIL。

自测：`python scripts/agent/prompt_drift_check.py --selftest`
      —— 每条检查都有一份必红 fixture；fixture 不红 ⇒ selftest 自己红。

接入（已落地）：`scripts/agent/team_audit.py::check_prompt_drift` 以子进程消费 `--json`；
脚本缺失/崩溃/超时/无输出/输出不可解析/NOT_RUN 一律在 team_audit 报 FAIL（静默跳过 = 门禁失效）。

维护（提示词 owner 改完提示词后）：
  1. 更新内容；
  2. `python scripts/agent/prompt_drift_check.py --print-deps <依赖路径...>` 拿新 sha12；
  3. 改头部 spec-version / spec-deps / reviewed-on；
  4. 跑本脚本到 exit 0。

## 依赖指纹变更后的**重签流程**（C4 红时必须按此走，禁止直接手改指纹变绿）

C4 的副作用是"代码一改就红"。红本身不是错——它要求 owner 复核"这条提示词里依赖该文件的断言是否仍然成立"。
为了不让重签退化成"红就改数字"，提供两条命令（**逐条确认 + 留痕**）：

```bash
# 1) 只读：列出所有提示词的依赖变更 + 每条变更的 git 证据 + 该文件要复核的小节清单
python scripts/agent/prompt_drift_check.py --recheck-deps

# 2) 重签：必须【显式列出】本次复核过的变更依赖（逐条确认），并写一句复核说明；
#    note < 10 字 ⇒ 拒绝；漏列任一变更依赖 ⇒ 拒绝（不许"一把全签"）；
#    成功后把 from→to 指纹与 note 追加到 artifacts/agent/verify/todo/prompt-drift-recheck-log.jsonl
python scripts/agent/prompt_drift_check.py --resign resources/agent-prompts/kb-spec.zh-CN.md \
    --dep src/memoria/graph/kb_build.py \
    --note "复核 §4 边剥离语义与 §8 常见坑，代码只改注释"
```

`--resign` 后会自动重跑检查并给出结论（仍可能有别的 FAIL，需继续处理）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

KB_AGENT_REL = "src/memoria/services/kb_agent.py"
EDGE_TYPES_REL = "src/memoria/graph/edge_types.py"
KB_BUILD_REL = "src/memoria/graph/kb_build.py"
LINK_MD_REL = "src/memoria/services/link_md.py"
FSRS_REL = "resources/agent-prompts/fsrs.py"
RENDER_CORE_REL = "src/memoria/ui/static/app/js/surface/render-core.js"
PACKAGING_REL = "packaging/build.py"

FAIL = "FAIL"
NOT_RUN = "NOT_RUN"  # 检查无法执行（输入不可读/依赖缺失/自身异常）——「跳过 ≠ 通过」
WARN = "WARN"
INFO = "INFO"
_SEV_ORDER = {FAIL: 0, NOT_RUN: 1, WARN: 2, INFO: 3}

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NOT_RUN = 2
EXIT_USAGE = 3

STALE_DAYS_DEFAULT = 90

REPO_PATH_PREFIXES = ("docs/", "src/", "scripts/", "resources/", "packaging/", "tests/", "config/")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
SLASH_LIST = re.compile(r"^[a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)+$")
STAMP_MD = re.compile(r"<!--\s*spec-version:\s*(\d+\.\d+\.\d+)\s*-->")
STAMP_PY = re.compile(r"^#\s*spec-version:\s*(\d+\.\d+\.\d+)\s*$", re.M)
DEPS_MD = re.compile(r"<!--\s*spec-deps:\s*(.*?)\s*-->")
DEPS_PY = re.compile(r"^#\s*spec-deps:\s*(.*)$", re.M)
REVIEWED = re.compile(r"<!--\s*reviewed-on:\s*(\d{4}-\d{2}-\d{2})\s*-->|^#\s*reviewed-on:\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)
WIKILINK_TYPE = re.compile(r"\[\[[^\[\]\n]*#([A-Za-z][A-Za-z0-9_-]*)\]\]")
LEGACY_QUALIFIERS = ("遗留", "剥离", "不要", "禁止", "已废弃", "会被", "重写", "legacy", "deprecated")
CARD_TYPES = frozenset({"basic", "cloze", "reverse"})

# 应由应用维护、**不由安装器分发**的 `.memoria/agent/**` 子项（README 必须说明归属）。
APP_OWNED_AGENT_NAMES = frozenset(
    {"capabilities.json", "skills", "sessions", "backups", "scratch", "attachments"}
)
# `resources/agent-prompts/**` 里不参与 KB 分发、供应用内 RPC 读取的内部资源。
# 判定依据见 audit 报告 §3：ui.get_agent_prompt 读 `organize.{lang}.md`。
APP_INTERNAL_ASSETS = {
    "organize.zh-CN.md": "ui.py::get_agent_prompt（程序内整理提示词弹窗，单一事实源）",
}

# 隐藏分发路径探测的"已人工核验"清单（仍然扫描；命中只记 INFO 并写明理由，不静默跳过）。
# PD-3 的要求是"不再无条件跳过危险位置"，不是"把它们变成永远免检"——核验理由必须可读。
HIDDEN_SCAN_REVIEWED = {
    "packaging/build.py": "打包态整目录随包（不是 KB 分发路径；KB 分发仍由 FILE_MAP 白名单决定）",
    "scripts/agent/prompt_drift_check.py": "本检查脚本自身（自引用误报）",
}


def prompt_doc_rels(ctx: "Ctx") -> list[str]:
    """全部"提示词文档"的仓库相对路径：分发 md + 应用内部提示词 md。

    C2/C3/C4/C5 都按这一份清单跑；`APP_INTERNAL_ASSETS` 只有在文件真实存在时才纳入，
    这样"内部提示词被删/改名"由 C1 的引用证据检查负责，而不是这里静默跳过。
    """
    rels: list[str] = []
    for src_name, _dst in ctx.kb_agent.get("FILE_MAP") or ():
        if str(src_name).endswith(".md"):
            rels.append(f"resources/agent-prompts/{src_name}")
    for name in APP_INTERNAL_ASSETS:
        rel = f"resources/agent-prompts/{name}"
        if (ctx.repo / rel).is_file():
            rels.append(rel)
    return rels


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    evidence: str = ""

    def as_dict(self) -> dict:
        return {"check": self.check, "severity": self.severity, "message": self.message, "evidence": self.evidence}


@dataclass
class Ctx:
    repo: Path
    kb_agent: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    not_run_checks: list = field(default_factory=list)
    _src_text: str | None = None
    _edge_types: dict | None = None

    # ── 基础 ────────────────────────────────────────────────────────────
    def add(self, check: str, severity: str, message: str, evidence: str = "") -> None:
        self.findings.append(Finding(check, severity, message, evidence))

    def not_run(self, check: str, message: str, evidence: str = "") -> None:
        """登记一次「检查无法执行」。

        PD-1（task-158）：**跳过 ≠ 通过**。任何因输入不可读/依赖缺失/自身异常而没跑的
        检查，必须产出 NOT_RUN finding（而不是 WARN/静默），最终 exit 非 0。
        """
        self.findings.append(Finding(check, NOT_RUN, message, evidence))
        if check not in self.not_run_checks:
            self.not_run_checks.append(check)

    def read(self, rel: str) -> str | None:
        try:
            return (self.repo / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def src_text(self) -> str:
        """src/memoria 下的代码正文（排除 vendor / 缓存；用于符号存在性校验）。"""
        if self._src_text is not None:
            return self._src_text
        chunks: list[str] = []
        base = self.repo / "src" / "memoria"
        if base.is_dir():
            for path in base.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in (".py", ".js", ".mjs", ".json"):
                    continue
                rel = str(path.relative_to(self.repo)).replace("\\", "/")
                if "/vendor/" in rel or "/node_modules/" in rel or "__pycache__" in rel:
                    continue
                try:
                    if path.stat().st_size > 2_000_000:
                        continue
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
        self._src_text = "\n".join(chunks)
        return self._src_text

    # ── 常量/权威解析 ───────────────────────────────────────────────────
    def edge_types(self) -> dict:
        """从 edge_types.py 读 EDGE_TYPES / WIKILINK_HINT_ALIASES（不 import）。

        真实代码里 `EDGE_TYPES = frozenset({EDGE_CONTAIN, ...})`，`ast.literal_eval`
        求不了 Name 引用，故先用"简单字符串常量表"解析，再解析集合字面量。
        """
        if self._edge_types is not None:
            return self._edge_types
        out = {"edge_types": set(), "aliases": set()}
        text = self.read(EDGE_TYPES_REL) or ""
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            consts: dict[str, str] = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        consts[node.targets[0].id] = node.value.value

            def _eval(node: ast.AST) -> set[str] | None:
                if isinstance(node, ast.Name):
                    return {consts[node.id]} if node.id in consts else None
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    return {node.value}
                if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
                    items: set[str] = set()
                    for element in node.elts:
                        part = _eval(element)
                        if part:
                            items |= part
                    return items
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("frozenset", "set", "tuple", "list"):
                    if node.args:
                        return _eval(node.args[0])
                return None

            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                if "EDGE_TYPES" in names:
                    value = _eval(node.value)
                    if value:
                        out["edge_types"] = value
                if "WIKILINK_HINT_ALIASES" in names:
                    try:
                        out["aliases"] = {str(k) for k in ast.literal_eval(node.value)}
                    except (ValueError, TypeError, SyntaxError):
                        pass
        self._edge_types = out
        return out

    def tool_names(self) -> set[str]:
        """MCP 工具面 + 进程内工具名（均为真实注册名）。"""
        names: set[str] = set()
        mcp = self.read("src/memoria/services/agent/mcp_server.py") or ""
        names.update(re.findall(r'"name"\s*:\s*"([a-z][a-z0-9_]*)"', mcp))
        kb_tools = self.read("src/memoria/services/agent/tools/kb.py") or ""
        names.update(re.findall(r'\bname="([a-z][a-z0-9_]*)"', kb_tools))
        return names

    def fsrs_subcommands(self) -> set[str]:
        text = self.read(FSRS_REL) or ""
        return set(re.findall(r'add_parser\(\s*"([a-z][a-z0-9_-]*)"', text))

    def image_attrs(self) -> set[str]:
        text = self.read(RENDER_CORE_REL) or ""
        match = re.search(r"支持\s+([a-z][a-z0-9/-]*)", text)
        if match:
            return {part for part in match.group(1).split("/") if part}
        return set()

    def deps_of(self, text: str) -> tuple[list[tuple[str, str]], str | None]:
        """解析 spec-deps 头：[(path, sha12)] + 原始行。"""
        match = DEPS_MD.search(text) or DEPS_PY.search(text)
        if not match:
            return [], None
        entries: list[tuple[str, str]] = []
        for raw in match.group(1).split(","):
            item = raw.strip()
            if not item:
                continue
            if "@" in item:
                path, digest = item.rsplit("@", 1)
            else:
                path, digest = item, ""
            entries.append((path.strip(), digest.strip().lower()))
        return entries, match.group(1).strip()


# ══════════════════════════════════════════════════════════════════════
# 常量装载
# ══════════════════════════════════════════════════════════════════════
def load_kb_agent(repo: Path) -> dict:
    """用 AST 读 kb_agent.py 的常量，**不 import**（避免副作用/依赖）。"""
    path = repo / KB_AGENT_REL
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    out = {
        "path": path,
        "text": text,
        "FILE_MAP": None,
        "REFERENCE_DOCS": None,
        "KIT_VERSION": None,
        "SPEC_VERSION": None,
        "KIT_FILE": ".kit.json",
        "REVIEW_DIRNAME": "review",
    }
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        for name in names:
            if name in ("FILE_MAP", "REFERENCE_DOCS"):
                try:
                    out[name] = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    pass
            elif name in ("KIT_VERSION", "SPEC_VERSION", "KIT_FILE", "REVIEW_DIRNAME"):
                try:
                    out[name] = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    pass
    return out


# ══════════════════════════════════════════════════════════════════════
# C1 分发完整性
# ══════════════════════════════════════════════════════════════════════
def check_distribution(ctx: Ctx) -> None:
    check = "distribution_integrity"
    info = ctx.kb_agent
    file_map = info.get("FILE_MAP")
    ref_docs = info.get("REFERENCE_DOCS")
    if not file_map:
        ctx.add(check, FAIL, "kb_agent.py 中没有可解析的 FILE_MAP（分发链路消失？）", KB_AGENT_REL)
        return
    if not ref_docs:
        ctx.add(check, WARN, "kb_agent.py 中没有可解析的 REFERENCE_DOCS", KB_AGENT_REL)

    src_dir = ctx.repo / "resources" / "agent-prompts"
    dst_names: list[str] = []
    src_names: list[str] = []
    for pair in file_map:
        if not (isinstance(pair, (tuple, list)) and len(pair) == 2):
            ctx.add(check, FAIL, f"FILE_MAP 条目形状非法：{pair!r}", KB_AGENT_REL)
            continue
        src_name, dst_name = str(pair[0]), str(pair[1])
        src_names.append(src_name)
        dst_names.append(dst_name)
        path = src_dir / src_name
        if not path.is_file():
            ctx.add(check, FAIL, f"分发源文件不存在：resources/agent-prompts/{src_name}", str(path))
            continue
        if path.stat().st_size == 0:
            ctx.add(check, FAIL, f"分发源文件为空：resources/agent-prompts/{src_name}", str(path))
            continue
        raw = path.read_bytes()
        if path.suffix == ".md":
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                ctx.add(check, FAIL, f"分发源文件不是合法 UTF-8：{src_name}（{exc}）", str(path))
        elif path.suffix == ".py":
            try:
                compile(raw.decode("utf-8"), str(path), "exec")
            except (UnicodeDecodeError, SyntaxError) as exc:
                ctx.add(check, FAIL, f"分发源 Python 文件无法解析：{src_name}（{exc}）", str(path))

    for pair in ref_docs or ():
        if not (isinstance(pair, (tuple, list)) and len(pair) == 2):
            ctx.add(check, FAIL, f"REFERENCE_DOCS 条目形状非法：{pair!r}", KB_AGENT_REL)
            continue
        src_name, dst_name = str(pair[0]), str(pair[1])
        dst_names.append(dst_name)
        path = ctx.repo / "docs" / "reference" / src_name
        if not path.is_file():
            ctx.add(check, FAIL, f"随包参考文档不存在：docs/reference/{src_name}", str(path))
        elif path.stat().st_size == 0:
            ctx.add(check, FAIL, f"随包参考文档为空：docs/reference/{src_name}", str(path))

    if len(set(dst_names)) != len(dst_names):
        dupes = sorted({n for n in dst_names if dst_names.count(n) > 1})
        ctx.add(check, FAIL, f"分发落点文件名重复（会互相覆盖）：{dupes}", KB_AGENT_REL)
    for name in dst_names:
        if name.startswith(str(info.get("REVIEW_DIRNAME") or "review") + "/"):
            ctx.add(check, FAIL, f"分发落点不得落在 review/ 下（永不被覆盖）：{name}", KB_AGENT_REL)

    # README 声明 ↔ 实际分发（双向）
    readme = None
    for src_name, dst_name in file_map:
        if str(dst_name) == "README.md":
            readme = ctx.read(f"resources/agent-prompts/{src_name}")
            break
    readme_rel = "resources/agent-prompts/<README 源>"
    if readme is None:
        ctx.not_run(check, "未找到分发到 README.md 的源文件，目录声明无法核对（跳过≠通过）", readme_rel)
    else:
        claimed = set(re.findall(r"^\|\s*`([^`]+)`\s*\|", readme, re.M))
        dst_set = set(dst_names)
        kit_file = str(info.get("KIT_FILE") or ".kit.json")
        review_dir = str(info.get("REVIEW_DIRNAME") or "review")
        known_app = {kit_file} | {f"{review_dir}/{x}" for x in ("cards.json", "progress.json")}
        for item in sorted(claimed):
            top = item.split("/")[0].rstrip("*").rstrip("/")
            if item in dst_set or item in known_app or item in APP_OWNED_AGENT_NAMES or top in APP_OWNED_AGENT_NAMES:
                continue
            if item.startswith(f"{review_dir}/") or item.startswith(".memoria/"):
                continue
            ctx.add(check, FAIL, f"README 声明的文件既不在分发清单也没有归属说明：{item}", readme_rel)
        for dst in sorted(dst_set):
            if dst == "README.md":
                continue
            if dst not in claimed:
                ctx.add(check, FAIL, f"分发文件未在 README 目录表中声明：{dst}", readme_rel)

    # 提示词里引用的 .memoria/agent/<名> 必须是真实落点
    dst_set = set(dst_names)
    for src_name in src_names:
        if not src_name.endswith(".md"):
            continue
        text = ctx.read(f"resources/agent-prompts/{src_name}") or ""
        for match in re.finditer(r"\.memoria/agent/([A-Za-z0-9_.-]+)", text):
            name = match.group(1)
            if name in dst_set or name in APP_OWNED_AGENT_NAMES or name in (str(info.get("KIT_FILE")),):
                continue
            if name.startswith(str(info.get("REVIEW_DIRNAME") or "review")):
                continue
            ctx.add(
                check,
                FAIL,
                f"提示词引用了不存在的 .memoria/agent/{name}（分发清单里没有）",
                f"resources/agent-prompts/{src_name}",
            )

    # 孤儿资源（PD-4：**递归**，不再只看顶层）：目录里有、但既不分发也不在"内部资源"白名单
    if src_dir.is_dir():
        on_disk = {
            str(p.relative_to(src_dir)).replace("\\", "/")
            for p in src_dir.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix != ".pyc"
            and not any(part.startswith(".") for part in p.relative_to(src_dir).parts)
        }
        for name in sorted(on_disk - set(src_names) - set(APP_INTERNAL_ASSETS)):
            ctx.add(
                check,
                WARN,
                f"resources/agent-prompts/{name} 未被 FILE_MAP 分发，也未登记为应用内部资源"
                "（可能是隐藏分发路径或死文件，须人工归类）",
                str(src_dir / name),
            )
        ui_text = ctx.read("src/memoria/presentation/api/ui.py")
        if ui_text is None:
            ctx.not_run(check, "无法读取 ui.py，内部资源引用证据无法核对（跳过≠通过）",
                        "src/memoria/presentation/api/ui.py")
        else:
            for name, why in APP_INTERNAL_ASSETS.items():
                if name in on_disk and why.split("::")[0] not in ui_text:
                    ctx.add(check, WARN, f"内部资源 {name} 的引用证据失效（{why} 未在代码中找到）", str(src_dir / name))

    # 隐藏分发路径探测（PD-3：不再跳过 kb_agent/ui.py/build.py —— 恰是最可能藏目录扫描的位置）
    for rel in ("src/memoria", "packaging", "scripts"):
        base = ctx.repo / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in (".py", ".js", ".mjs"):
                continue
            rel_path = str(path.relative_to(ctx.repo)).replace("\\", "/")
            if "/vendor/" in rel_path or "/node_modules/" in rel_path or "__pycache__" in rel_path:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                ctx.not_run(check, f"隐藏分发路径探测无法读取文件：{rel_path}（{exc}）", rel_path)
                continue
            if "agent-prompts" not in text:
                continue
            if re.search(r"iterdir\(|rglob\(|glob\(", text):
                if rel_path in HIDDEN_SCAN_REVIEWED:
                    ctx.add(
                        check,
                        INFO,
                        f"隐藏分发路径探测命中已核验文件（非 KB 分发路径）：{rel_path}"
                        f"（理由：{HIDDEN_SCAN_REVIEWED[rel_path]}）",
                        rel_path,
                    )
                else:
                    ctx.add(
                        check,
                        WARN,
                        f"疑似按目录扫描分发 agent-prompts 的代码：{rel_path}"
                        "（若真存在，本检查的覆盖口径需改为目录全量）",
                        rel_path,
                    )

    # 打包白名单：发布态缺一个源文件 ⇒ install_kb_agent 直接报"内置资源缺失"
    packaging = ctx.read(PACKAGING_REL)
    if packaging is None:
        ctx.not_run(check, f"未找到 {PACKAGING_REL}，随包白名单无法核对（跳过≠通过）", PACKAGING_REL)
    else:
        for src_name in src_names:
            if f"agent-prompts/{src_name}" not in packaging:
                ctx.add(
                    check,
                    FAIL,
                    f"分发源未登记进打包白名单：agent-prompts/{src_name}（发布态会报内置资源缺失）",
                    PACKAGING_REL,
                )
        for src_name, _ in ref_docs or ():
            if f"docs/{src_name}" not in packaging:
                ctx.add(
                    check,
                    FAIL,
                    f"随包参考文档未登记进打包白名单：docs/{src_name}",
                    PACKAGING_REL,
                )


# ══════════════════════════════════════════════════════════════════════
# C2 代码符号引用校验
# ══════════════════════════════════════════════════════════════════════
def _kb_path_ok(
    ctx: Ctx,
    token: str,
    allowed_kb_prefixes: set[str],
    dst_set: set[str],
    code: str,
) -> tuple[bool, str]:
    norm = token.replace("\\", "/").rstrip("。，、；：,.;:")
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return False, "空路径"
    # 目录整体引用（`.memoria/**` / `.memoria/` / `review/**`）只看前缀
    if norm.endswith("/**") or norm.endswith("/"):
        prefix = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
        if parts[0] == "review":
            return ("review" in code or "review" in allowed_kb_prefixes), "代码中无 review 目录"
        return (prefix in allowed_kb_prefixes), f"前缀 {prefix!r} 不在代码已知 KB 路径集合"
    # review/*：允许的复习数据文件由 fsrs.py/代码字面量决定
    if parts[0] == "review":
        leaf = parts[1] if len(parts) > 1 else ""
        fsrs_text = ctx.read(FSRS_REL) or ""
        if leaf and (leaf in code or leaf in fsrs_text):
            return True, ""
        return False, f"review/{leaf} 不是代码中出现的复习数据文件"
    if any(ch in norm for ch in "<>*") or re.search(r"[\u4e00-\u9fff]", norm):
        prefix = "/".join(parts[:2])
        return (prefix in allowed_kb_prefixes), f"前缀 {prefix!r} 不在代码已知 KB 路径集合"
    joined = "/".join(parts[:2])
    if joined not in allowed_kb_prefixes:
        return False, f"前缀 {joined!r} 不在代码已知 KB 路径集合"
    if len(parts) >= 3 and parts[1] == "agent":
        leaf = parts[2]
        if leaf in dst_set or leaf in APP_OWNED_AGENT_NAMES:
            return True, ""
        if leaf.endswith((".json", ".md", ".py")):
            return False, f".memoria/agent/{leaf} 不是分发落点也不是应用管理项"
    return True, ""


def check_symbols(ctx: Ctx) -> None:
    check = "symbol_reference"
    info = ctx.kb_agent
    dst_set = {str(dst) for _, dst in (info.get("FILE_MAP") or ())}
    dst_set.update(str(dst) for _, dst in (info.get("REFERENCE_DOCS") or ()))
    edge = ctx.edge_types()
    tools = ctx.tool_names()
    fsrs_subs = ctx.fsrs_subcommands()
    img_attrs = ctx.image_attrs()
    code = ctx.src_text()
    allowed_kb_prefixes = set()
    for match in re.finditer(r"\.memoria[/\\]([A-Za-z0-9_.-]+)", code):
        allowed_kb_prefixes.add(".memoria/" + match.group(1))
    allowed_kb_prefixes.add("review")
    docs_kb = ""
    for rel in ("docs/design/kb-agent.md",):
        docs_kb += (ctx.read(rel) or "")

    prompt_rels = prompt_doc_rels(ctx)
    kit_file = str(info.get("KIT_FILE") or ".kit.json")
    preview_text = ctx.read("docs/reference/preview-formats.md") or ""

    for rel in prompt_rels:
        text = ctx.read(rel)
        if text is None:
            ctx.not_run(check, f"无法读取提示词文档：{rel}（跳过≠通过）", rel)
            continue
        unclassified: list[str] = []
        for span in sorted(set(CODE_SPAN.findall(text))):
            token = span.strip().rstrip("。，、；：,.;:)").replace("[]", "")
            if not token or token.startswith("[[") or token.startswith("<!--"):
                continue
            if re.search(r"[\u4e00-\u9fff]", token):
                continue
            # 只校验"像符号"的 token；纯 Markdown 语法（`![..](..)`、`##`、`*.md`）不在此列
            if not re.fullmatch(r"[A-Za-z_<][A-Za-z0-9_./@#*<>-]*", token):
                continue
            # 0) 分发落点名 / 已知运行期文件：直接算真实存在
            if token in dst_set or token in (kit_file, "README.md") or token in APP_OWNED_AGENT_NAMES:
                continue
            # 占位符（<name>.md / skills/**）：不是可校验的具体路径
            if "<" in token or "*" in token:
                continue
            # 仓库路径
            if token.startswith(REPO_PATH_PREFIXES):
                clean = re.sub(r":\d+(?:-\d+)?$", "", token)
                if "**" in clean:
                    clean = clean.split("**")[0].rstrip("/")
                target = ctx.repo / clean
                if not target.exists():
                    ctx.add(check, FAIL, f"提示词引用的仓库路径不存在：{token}", rel)
                continue
            # KB 路径
            if token.startswith(".memoria/") or token.startswith("review/"):
                ok, why = _kb_path_ok(ctx, token, allowed_kb_prefixes, dst_set, code)
                if not ok:
                    ctx.add(check, FAIL, f"提示词引用的知识库路径不存在或未登记：{token}（{why}）", rel)
                continue
            # 图像路径前缀（./ 与 ../ 的语义由渲染权威文档决定）
            if token in ("./", "../"):
                if token not in preview_text:
                    ctx.add(check, FAIL, f"路径前缀 {token} 在渲染权威文档中找不到依据", rel)
                continue
            if token.startswith("./") or token.startswith("../"):
                ctx.add(check, WARN, f"相对路径写法未校验：{token}", rel)
                continue
            # 斜杠枚举（如 width/enlarge/align）——必须先于通用相对路径分支
            if SLASH_LIST.match(token):
                bad = [
                    seg
                    for seg in token.split("/")
                    if seg not in edge["edge_types"]
                    and seg not in img_attrs
                    and seg not in fsrs_subs
                    and seg not in tools
                    and seg not in CARD_TYPES
                    and seg not in code
                ]
                if bad:
                    ctx.add(
                        check,
                        FAIL,
                        f"斜杠枚举里有代码中不存在的符号：{'/'.join(bad)}（原文 {token}）",
                        rel,
                    )
                continue
            # 相对示例路径（subdir/topic-c.md）不具可校验性 ⇒ 记 INFO（不误红）
            if "/" in token:
                unclassified.append(token)
                continue
            # 文件名（`.md/.json/.py/.yaml`）：必须出现在分发清单、应用项或代码字面量里
            if token.endswith((".md", ".json", ".py", ".yaml")):
                if token in code:
                    continue
                ctx.add(check, FAIL, f"提示词提到的文件名在代码/分发清单中不存在：{token}", rel)
                continue
            # 点分字段路径（range.end.snippet / links.edge_type）：**每一段**都校验（PD-2）
            # 旧实现只校验 snake_case 段 ⇒ `range.fakeCamelField` 隐形放行。
            if "." in token and "/" not in token and not token.endswith((".md", ".json", ".py", ".yaml")):
                segs = [seg for seg in token.split(".") if seg]
                bad = [
                    seg
                    for seg in segs
                    if seg not in code and seg not in edge["edge_types"] and seg not in img_attrs
                ]
                if bad:
                    ctx.add(
                        check,
                        FAIL,
                        f"点分字段里有代码中不存在的符号：{'.'.join(bad)}（原文 {token}）",
                        rel,
                    )
                continue
            # snake_case 标识符 / RPC 名 / 字段名
            if SNAKE.match(token):
                if token in code or token in edge["edge_types"]:
                    continue
                ctx.add(check, FAIL, f"提示词提到的符号在代码中不存在：{token}", rel)
                continue
            # 已知单词类
            if token in edge["edge_types"] or token in fsrs_subs or token in tools:
                continue
            if token in CARD_TYPES:
                if token not in docs_kb:
                    ctx.add(check, FAIL, f"卡片类型 {token!r} 在设计文档中也找不到（无权威来源）", rel)
                continue
            if token in img_attrs:
                continue
            if token.startswith("--"):
                fsrs_text = ctx.read(FSRS_REL) or ""
                if token not in fsrs_text:
                    ctx.add(check, FAIL, f"命令行 flag 在 fsrs.py 中不存在：{token}", rel)
                continue
            if re.fullmatch(r"[a-z][a-z0-9-]*", token):
                unclassified.append(token)
                continue
            unclassified.append(token)
        if unclassified:
            ctx.add(
                check,
                INFO,
                f"有 {len(unclassified)} 个反引号 token 未归类（未做存在性校验）："
                + ", ".join(sorted(set(unclassified))[:12]),
                rel,
            )

    # fsrs.py 命令行块：子命令与 flag 必须与 argparse 一致
    fsrs_text = ctx.read(FSRS_REL)
    if fsrs_text is None:
        ctx.not_run(check, f"无法读取 {FSRS_REL}，fsrs 子命令/参数校验无法执行（跳过≠通过）", FSRS_REL)
        fsrs_text = ""
    for rel in prompt_rels:
        text = ctx.read(rel)
        if text is None:
            ctx.not_run(check, f"无法读取提示词文档：{rel}（跳过≠通过）", rel)
            continue
        for match in re.finditer(r"fsrs\.py\s+([a-z][a-z0-9-]*)", text):
            sub = match.group(1)
            if sub not in fsrs_subs:
                ctx.add(check, FAIL, f"提示词教了 fsrs.py 不存在的子命令：{sub}", rel)
        for line in text.splitlines():
            if "fsrs.py" not in line:
                continue
            for flag in re.findall(r"(--[a-z][a-z0-9-]*)", line):
                if flag not in fsrs_text:
                    ctx.add(check, FAIL, f"提示词教了 fsrs.py 不存在的参数：{flag}", rel)

    # 规范章节号引用：prompt 里的 `§N.M` 必须在 kb-spec 中真实存在（防重编号漂移）
    spec_text = ""
    spec_rel = ""
    for src_name, dst in info.get("FILE_MAP") or ():
        if str(dst) == "kb-spec.zh-CN.md":
            spec_rel = f"resources/agent-prompts/{src_name}"
            spec_text = ctx.read(spec_rel) or ""
    if not spec_text:
        ctx.not_run(check, "无法读取 kb-spec 提示词，章节引用校验无法执行（跳过≠通过）", spec_rel or "resources/agent-prompts/kb-spec.zh-CN.md")
    if spec_text:
        spec_sections = set(re.findall(r"^#{2,3}\s+(\d+(?:\.\d+)?)[.、\s]", spec_text, re.M))
        for rel in prompt_rels:
            text = ctx.read(rel)
            if text is None:
                ctx.not_run(check, f"无法读取提示词文档：{rel}（跳过≠通过）", rel)
                continue
            if rel.endswith("kb-spec.zh-CN.md"):
                continue
            for ref in sorted(set(re.findall(r"§(\d+(?:\.\d+)?)", text))):
                if ref not in spec_sections:
                    ctx.add(check, FAIL, f"提示词引用的规范章节 §{ref} 在 kb-spec 中不存在", rel)


# ══════════════════════════════════════════════════════════════════════
# C3 禁止教"会被代码剥离"的语法
# ══════════════════════════════════════════════════════════════════════
# PD-5：豁免词必须"紧邻"该语法 —— 同一位置窗口内，且语法与限定词之间不能夹句读分隔。
# 旧实现是"同一行任意位置出现限定词 ⇒ 整行豁免"，`[[某#contain]]，不要写错别字` 会因此放行。
PROXIMITY_CHARS = 24
_PROXIMITY_BREAKS = ("，", ",", "；", ";", "。", "！", "？", "\n")


def _qualifier_near(line: str, syntax_start: int, syntax_end: int) -> bool:
    """语法附近是否有豁免词（同一窗口 + 中间无句读分隔）。"""
    for word in LEGACY_QUALIFIERS:
        cursor = 0
        while True:
            pos = line.find(word, cursor)
            if pos < 0:
                break
            cursor = pos + 1
            if pos >= syntax_end:
                if pos - syntax_end > PROXIMITY_CHARS:
                    continue
                between = line[syntax_end:pos]
            elif pos + len(word) <= syntax_start:
                if syntax_start - (pos + len(word)) > PROXIMITY_CHARS:
                    continue
                between = line[pos + len(word):syntax_start]
            else:
                continue  # 与语法重叠，不算
            if not any(ch in between for ch in _PROXIMITY_BREAKS):
                return True
    return False


def check_forbidden_syntax(ctx: Ctx) -> None:
    check = "forbidden_syntax"
    edge = ctx.edge_types()
    aliases = edge["aliases"] | edge["edge_types"]
    if not aliases:
        ctx.not_run(
            check,
            "无法从 edge_types.py 读取边类型片段集合，C3 无法执行（跳过≠通过）",
            EDGE_TYPES_REL,
        )
        return
    build_text = ctx.read(KB_BUILD_REL)
    link_text = ctx.read(LINK_MD_REL)
    if build_text is None or link_text is None:
        ctx.not_run(
            check,
            "无法读取 kb_build.py / link_md.py，正文剥离行为无法判定（跳过≠通过）",
            f"{KB_BUILD_REL} / {LINK_MD_REL}",
        )
        return
    strip_active = "strip_known_wikilink_edge_hints(" in build_text and "def strip_known_wikilink_edge_hints" in link_text
    if not strip_active:
        ctx.add(
            check,
            WARN,
            "代码已不再剥离正文 wikilink 边类型片段，但提示词里的『遗留会被剥离』结论可能过期",
            f"{KB_BUILD_REL} / {LINK_MD_REL}",
        )

    for rel in prompt_doc_rels(ctx):
        text = ctx.read(rel)
        if text is None:
            ctx.not_run(check, f"无法读取提示词文档：{rel}（跳过≠通过）", rel)
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in WIKILINK_TYPE.finditer(line):
                hint = match.group(1).lower()
                if hint not in aliases:
                    continue
                if _qualifier_near(line, match.start(), match.end()):
                    continue
                if not strip_active:
                    continue
                ctx.add(
                    check,
                    FAIL,
                    f"提示词把会被构建剥离的语法当推荐写法教：{match.group(0)}"
                    "（代码会把它迁移后从正文删除；要标边类型请写 sidecar edges[]）",
                    f"{rel}:{lineno}",
                )


# ══════════════════════════════════════════════════════════════════════
# C4 版本戳 + 依赖指纹锁
# ══════════════════════════════════════════════════════════════════════
def _sha12(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def check_version_stamps(ctx: Ctx) -> None:
    check = "version_stamp"
    info = ctx.kb_agent
    spec_version = str(info.get("SPEC_VERSION") or "")
    kit_version = str(info.get("KIT_VERSION") or "")
    if not spec_version:
        ctx.add(check, FAIL, "kb_agent.py 中没有 SPEC_VERSION", KB_AGENT_REL)
        return
    for rel in prompt_doc_rels(ctx):
        src_name = rel.rsplit("/", 1)[-1]
        text = ctx.read(rel)
        if text is None:
            ctx.not_run(check, f"无法读取提示词文档：{rel}（跳过≠通过）", rel)
            continue
        head = "\n".join(text.splitlines()[:14])
        stamp_md = STAMP_MD.search(head)
        if not stamp_md:
            ctx.add(check, FAIL, f"缺少版本戳（头部 14 行内无 <!-- spec-version: X.Y.Z -->）：{src_name}", rel)
        elif stamp_md.group(1) != spec_version:
            ctx.add(
                check,
                FAIL,
                f"版本戳 {stamp_md.group(1)} 与 kb_agent.SPEC_VERSION {spec_version} 不一致（{src_name}）",
                rel,
            )
        if not REVIEWED.search(head):
            ctx.add(check, FAIL, f"缺少 <!-- reviewed-on: YYYY-MM-DD -->（{src_name}）", rel)
        deps, _raw = ctx.deps_of(head)
        if not deps:
            ctx.add(check, FAIL, f"缺少 <!-- spec-deps: path@sha12, ... -->（依赖指纹锁，{src_name}）", rel)
            continue
        for dep_path, dep_digest in deps:
            target = ctx.repo / dep_path
            if not dep_path or not target.is_file():
                ctx.add(check, FAIL, f"spec-deps 声明的依赖不存在：{dep_path}", rel)
                continue
            current = _sha12(target)
            if not re.fullmatch(r"[0-9a-f]{8,64}", dep_digest):
                ctx.add(check, FAIL, f"spec-deps 指纹格式非法：{dep_path}@{dep_digest}", rel)
            elif not current.startswith(dep_digest.lower()):
                ctx.add(
                    check,
                    FAIL,
                    "依赖已变更，提示词可能脱节：先跑 `--recheck-deps` 复核相关断言，"
                    "再按 `--resign <文件> --dep <依赖> --note <复核说明>` 逐条重签指纹。"
                    f" {dep_path} 记录 @{dep_digest}，当前 @{current}",
                    rel,
                )
    if kit_version and spec_version and not kit_version:
        ctx.add(check, WARN, "KIT_VERSION 为空", KB_AGENT_REL)


# ══════════════════════════════════════════════════════════════════════
# C5 陈旧告警
# ══════════════════════════════════════════════════════════════════════
def _git_commit_date(repo: Path, rel: str) -> date | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%cs", "--", rel],
            capture_output=True,
            text=True,
            encoding="utf-8",  # Windows 默认 cp1252 解码会在非 ASCII 输出上抛 UnicodeDecodeError
            errors="replace",
            timeout=15,
        )
        if out.returncode == 0 and out.stdout.strip():
            return date.fromisoformat(out.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def check_staleness(ctx: Ctx, now: date, stale_days: int = STALE_DAYS_DEFAULT) -> None:
    check = "staleness"
    for rel in prompt_doc_rels(ctx):
        text = ctx.read(rel)
        if text is None:
            ctx.not_run(check, f"无法读取提示词文档：{rel}（跳过≠通过）", rel)
            continue
        head = "\n".join(text.splitlines()[:14])
        match = REVIEWED.search(head)
        if not match:
            continue
        raw_date = match.group(1) or match.group(2)
        try:
            reviewed = date.fromisoformat(raw_date)
        except ValueError:
            ctx.add(check, FAIL, f"reviewed-on 不是合法日期：{raw_date}", rel)
            continue
        age = (now - reviewed).days
        if age > stale_days:
            ctx.add(
                check,
                WARN,
                f"提示词已 {age} 天未复核（reviewed-on {raw_date}，阈值 {stale_days} 天）",
                rel,
            )
        deps, _raw = ctx.deps_of(head)
        for dep_path, _digest in deps:
            target = ctx.repo / dep_path
            if not target.is_file():
                continue
            changed = _git_commit_date(ctx.repo, dep_path)
            if changed is None:
                changed = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).date()
            lag = (changed - reviewed).days
            if lag > stale_days:
                ctx.add(
                    check,
                    WARN,
                    f"依赖 {dep_path} 的最近变更（{changed.isoformat()}）比 reviewed-on "
                    f"（{raw_date}）新 {lag} 天，提示词可能已过期",
                    rel,
                )


# ══════════════════════════════════════════════════════════════════════
# 运行 / 输出
# ══════════════════════════════════════════════════════════════════════
_CHECK_FUNCS = (
    ("distribution_integrity", check_distribution),
    ("symbol_reference", check_symbols),
    ("forbidden_syntax", check_forbidden_syntax),
    ("version_stamp", check_version_stamps),
)


def run_checks(ctx: Ctx, now: date | None = None, stale_days: int = STALE_DAYS_DEFAULT) -> list[Finding]:
    """跑全部检查。**任何检查自身异常都转成 NOT_RUN（不是崩溃、也不是静默跳过）**。"""
    for name, func in _CHECK_FUNCS:
        try:
            func(ctx)
        except Exception as exc:  # noqa: BLE001 —— PD-1：自身异常=未执行，必须可见
            ctx.not_run(name, f"检查执行异常（{type(exc).__name__}）：{exc}")
    try:
        check_staleness(ctx, now or date.today(), stale_days)
    except Exception as exc:  # noqa: BLE001
        ctx.not_run("staleness", f"检查执行异常（{type(exc).__name__}）：{exc}")
    ctx.findings.sort(key=lambda f: (_SEV_ORDER.get(f.severity, 9), f.check, f.message))
    return ctx.findings


def _summary(findings: list[Finding], not_run_checks: list[str] | None = None) -> dict:
    counts = {FAIL: 0, NOT_RUN: 0, WARN: 0, INFO: 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    if counts[FAIL]:
        status = "fail"
    elif counts[NOT_RUN]:
        status = "not_run"
    else:
        status = "ok"
    return {
        "findings": len(findings),
        **counts,
        "status": status,
        "not_run": sorted(not_run_checks or []),
    }


def _emit(findings: list[Finding], as_json: bool, not_run_checks: list[str] | None = None) -> None:
    summary = _summary(findings, not_run_checks)
    if as_json:
        print(
            json.dumps(
                {
                    "schema": "prompt-drift/v1",
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                    "findings": [f.as_dict() for f in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for finding in findings:
        print(f"[{finding.severity}] {finding.check}: {finding.message}")
        if finding.evidence:
            print(f"        证据：{finding.evidence}")
    print(
        f"\n汇总：FAIL={summary[FAIL]} NOT_RUN={summary[NOT_RUN]} WARN={summary[WARN]} "
        f"INFO={summary[INFO]} 合计 {summary['findings']} 条"
    )
    if summary["status"] == "fail":
        print("结论：存在 FAIL，提示词已漂移，须修")
    elif summary["status"] == "not_run":
        print(
            "结论：有检查未能执行（NOT_RUN："
            + ", ".join(summary["not_run"])
            + "）—— 跳过 ≠ 通过，不得判绿"
        )
    else:
        print("结论：提示词与代码一致（无 FAIL，且全部检查已执行）")


# ══════════════════════════════════════════════════════════════════════
# 重签流程：--recheck-deps（只读清单）/ --resign（逐条确认 + 留痕）
# ══════════════════════════════════════════════════════════════════════
RECHECK_LOG_REL = "artifacts/agent/verify/todo/prompt-drift-recheck-log.jsonl"


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def collect_dep_changes(ctx: Ctx) -> list[dict]:
    """每个提示词文档的依赖指纹状态（记录值 vs 当前值）。"""
    rows: list[dict] = []
    for rel in prompt_doc_rels(ctx):
        text = ctx.read(rel) or ""
        head = "\n".join(text.splitlines()[:14])
        deps, _raw = ctx.deps_of(head)
        entries = []
        for dep_path, recorded in deps:
            target = ctx.repo / dep_path
            current = _sha12(target) if target.is_file() else None
            changed = current is None or not current.startswith(recorded or "~")
            entries.append(
                {"path": dep_path, "recorded": recorded, "current": current, "changed": changed}
            )
        rows.append({"file": rel, "deps": entries})
    return rows


def recheck_report(repo: Path) -> int:
    """只读：列出依赖变更 + git 证据 + 该提示词要复核的小节清单 + 精确重签命令。"""
    ctx = Ctx(repo=repo, kb_agent=load_kb_agent(repo))
    rows = collect_dep_changes(ctx)
    changed_total = sum(1 for row in rows for entry in row["deps"] if entry["changed"])
    print(f"提示词依赖指纹复核清单（{date.today().isoformat()}）")
    print(f"提示词文档 {len(rows)} 个；变更依赖 {changed_total} 条\n")
    if changed_total == 0:
        print("全部依赖指纹一致，无需重签。")
        return 0
    for row in rows:
        changed = [entry for entry in row["deps"] if entry["changed"]]
        if not changed:
            continue
        print(f"[CHANGED] {row['file']}")
        for entry in changed:
            print(
                f"  · {entry['path']}  记录 @{entry['recorded'] or '(缺失)'} → 当前 @{entry['current'] or '(文件缺失)'}"
            )
            log = _git(repo, "log", "-3", "--format=%h %cs %s", "--", entry["path"])
            if log:
                for line in log.splitlines():
                    print(f"      最近提交：{line}")
            diff = _git(repo, "diff", "--stat", "--", entry["path"])
            if diff:
                print(f"      未提交改动：{diff.splitlines()[-1].strip()}")
        text = ctx.read(row["file"]) or ""
        sections = re.findall(r"^#{1,3}\s+(.+)$", text, re.M)
        print("  ▸ 要逐条复核的断言所在小节（读这些小节，确认与代码新行为一致）：")
        for title in sections[:12]:
            print(f"      #{title.strip()}")
        print("  ▸ 重签（只签你**真的复核过**的依赖；漏签仍会红）：")
        dep_args = " ".join(f"--dep {entry['path']}" for entry in changed)
        print(
            f"      python scripts/agent/prompt_drift_check.py --resign {row['file']} "
            f"{dep_args} --note \"复核了哪些断言（≥10 字）\""
        )
        print()
    print("规则：不允许跳过复核直接改指纹；--resign 会把 from→to 与 note 追加到")
    print(f"      {RECHECK_LOG_REL}")
    return 0


def _rewrite_deps_header(text: str, new_digests: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        match = DEPS_MD.search(line)
        if match:
            entries: list[str] = []
            for raw in match.group(1).split(","):
                item = raw.strip()
                if not item:
                    continue
                path = item.rsplit("@", 1)[0].strip() if "@" in item else item
                digest = new_digests.get(path, item.rsplit("@", 1)[1] if "@" in item else "")
                entries.append(f"{path}@{digest}")
            out.append(f"<!-- spec-deps: {', '.join(entries)} -->\n")
            continue
        out.append(line)
    return "".join(out)


def resign(repo: Path, rel: str, dep_paths: list[str], note: str, reviewed_on: str | None) -> int:
    """逐条确认后重签指定依赖指纹；写追加审计日志；重签后立即重跑检查。"""
    ctx = Ctx(repo=repo, kb_agent=load_kb_agent(repo))
    rel = rel.replace("\\", "/").strip()
    valid = set(prompt_doc_rels(ctx))
    if rel not in valid:
        print(f"用法错误：{rel} 不是受管的提示词文档。可选：{', '.join(sorted(valid))}", file=sys.stderr)
        return EXIT_USAGE
    text = ctx.read(rel)
    if text is None:
        print(f"用法错误：读不到 {rel}", file=sys.stderr)
        return EXIT_USAGE
    head = "\n".join(text.splitlines()[:14])
    deps, _raw = ctx.deps_of(head)
    if not deps:
        print(f"用法错误：{rel} 没有 spec-deps 头，无法重签", file=sys.stderr)
        return EXIT_USAGE
    declared = {path for path, _digest in deps}
    current = {path: _sha12(ctx.repo / path) for path in declared if (ctx.repo / path).is_file()}
    changed = {
        path
        for path, digest in deps
        if path not in current or not current[path].startswith(digest or "~")
    }
    if not changed:
        print(f"{rel} 的依赖指纹已一致，无需重签。")
        return 0
    requested = {p.replace("\\", "/").strip() for p in dep_paths}
    unknown = requested - declared
    if unknown:
        print(f"用法错误：--dep 里的路径不在 {rel} 的 spec-deps 中：{sorted(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    missing = changed - requested
    if missing:
        print(
            "拒绝重签：以下变更依赖未被逐条确认（--dep 逐个列出你复核过的）："
            + ", ".join(sorted(missing)),
            file=sys.stderr,
        )
        return EXIT_USAGE
    if len((note or "").strip()) < 10:
        print("拒绝重签：--note 必须写 ≥10 字的复核说明（写清复核了哪些断言）", file=sys.stderr)
        return EXIT_USAGE
    new_digests = dict(current)
    updated = _rewrite_deps_header(text, new_digests)
    reviewed = reviewed_on or date.today().isoformat()
    try:
        date.fromisoformat(reviewed)
    except ValueError:
        print(f"用法错误：--reviewed-on 不是合法日期：{reviewed}", file=sys.stderr)
        return EXIT_USAGE
    updated = REVIEWED.sub(
        lambda m: m.group(0).replace(m.group(1) or m.group(2), reviewed), updated, count=1
    )
    if not REVIEWED.search("\n".join(updated.splitlines()[:14])):
        print(f"用法错误：{rel} 没有 reviewed-on 头，无法重签", file=sys.stderr)
        return EXIT_USAGE
    # newline="\n"：Windows 默认文本写会把 \n 翻成 \r\n ⇒ 重签一次会把整份提示词的换行全改掉
    (ctx.repo / rel).write_text(updated, encoding="utf-8", newline="\n")

    log_path = ctx.repo / RECHECK_LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "file": rel,
        "reviewed_on": reviewed,
        "deps": [
            {"path": path, "from": dict(deps).get(path, ""), "to": current.get(path, "")}
            for path in sorted(requested)
        ],
        "note": note.strip(),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"已重签 {len(requested)} 条依赖；复核记录追加到 {RECHECK_LOG_REL}")
    print("重跑检查：\n")
    findings = run_checks(ctx)
    _emit(findings, as_json=False, not_run_checks=ctx.not_run_checks)
    summary = _summary(findings, ctx.not_run_checks)
    if summary["status"] == "fail":
        return EXIT_FAIL
    if summary["status"] == "not_run":
        return EXIT_NOT_RUN
    return EXIT_OK


# ══════════════════════════════════════════════════════════════════════
# 自测（每条检查一份必红 fixture）
# ══════════════════════════════════════════════════════════════════════
GREEN_KB_AGENT = '''"""fixture"""
KIT_VERSION = "1.0.0"
SPEC_VERSION = "1.0.0"
KIT_FILE = ".kit.json"
REVIEW_DIRNAME = "review"
FILE_MAP = (
    ("kb-agent-readme.md", "README.md"),
    ("kb-agent.zh-CN.md", "prompt.zh-CN.md"),
    ("kb-spec.zh-CN.md", "kb-spec.zh-CN.md"),
    ("fsrs.py", "fsrs.py"),
)
REFERENCE_DOCS = (("preview-formats.md", "preview-formats.md"),)
'''

GREEN_README = """<!-- spec-version: 1.0.0 -->
<!-- spec-deps: src/memoria/graph/edge_types.py@%EDGE% -->
<!-- reviewed-on: 2026-10-01 -->
# fixture README

| 文件 | 用途 |
|---|---|
| `prompt.zh-CN.md` | 指令 |
| `kb-spec.zh-CN.md` | 规范 |
| `preview-formats.md` | 格式 |
| `fsrs.py` | 调度 |
| `review/cards.json` | 卡片 |
| `.kit.json` | 版本 |
"""

GREEN_PROMPT = """<!-- spec-version: 1.0.0 -->
<!-- spec-deps: src/memoria/graph/edge_types.py@%EDGE% -->
<!-- reviewed-on: 2026-10-01 -->
# prompt

先读 `.memoria/agent/kb-spec.zh-CN.md` 与 `.memoria/agent/preview-formats.md`。
复习用 `python .memoria/agent/fsrs.py due --date 2026-10-01`。
"""

GREEN_SPEC = """<!-- spec-version: 1.0.0 -->
<!-- spec-deps: src/memoria/graph/edge_types.py@%EDGE%, src/memoria/graph/kb_build.py@%BUILD% -->
<!-- reviewed-on: 2026-10-01 -->
# spec

边类型 `reference` / `extend` / `contain` 只存 sidecar `edges[]`；字段 `source_id`、`targets`、`edge_type`。
图片属性白名单 `width/height/align/name-size/name`。
遗留写法 `[[kp-id#extend]]` 会被构建剥离，不要用。
"""

GREEN_FSRS = '''"""fixture fsrs"""
import argparse
FSRS_VERSION = "5"
def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("due")
    sub.add_parser("init")
    sub.add_parser("grade")
    ap.add_argument("--kb", default=".")
    ap.add_argument("--date", default="")
    ap.add_argument("--card", default="")
    ap.add_argument("--grade", default="")
    return ap.parse_args(argv)
'''

GREEN_EDGE = '''EDGE_CONTAIN = "contain"
EDGE_REFERENCE = "reference"
EDGE_EXTEND = "extend"
EDGE_TYPES = frozenset({EDGE_CONTAIN, EDGE_REFERENCE, EDGE_EXTEND})
WIKILINK_HINT_ALIASES = {"prerequisite": "reference", "extend": "extend", "contain": "contain"}
'''

GREEN_BUILD = '''from memoria.services.link_md import strip_known_wikilink_edge_hints
def build(body):
    return strip_known_wikilink_edge_hints(body)
'''

GREEN_LINK_MD = '''def strip_known_wikilink_edge_hints(body):
    return body, 0
'''

GREEN_CONST = '''MEMORIA_DIR = ".memoria"
SIDECARS_DIR = ".memoria/sidecars"
IMAGES_DIR = ".memoria/images"
AGENT_DIR = ".memoria/agent"
MANIFEST = ".memoria/manifest.yaml"
REVIEW = "review"
'''

GREEN_RENDER = '''// 支持 width/height/align/name-size/name
console.warn("[img-attrs] 未知图片属性 key=");
'''

GREEN_MCP = '''TOOLS = [{"name": "outline"}, {"name": "section"}, {"name": "snippet"}, {"name": "propose_write"}]
'''

GREEN_TOOLS_KB = '''Tool(name="read_document", description="x")
Tool(name="search_kb", description="x")
'''


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _fixture_repo(tmp: Path, *, edge_hash: str | None = None, build_hash: str | None = None) -> Path:
    """构造一个绿 fixture 仓库（内容与真实仓库同构的最小版本）。"""
    repo = tmp / "repo"
    _write(repo / KB_AGENT_REL, GREEN_KB_AGENT)
    _write(repo / GREEN_EDGE_PATH, GREEN_EDGE)
    _write(repo / GREEN_BUILD_PATH, GREEN_BUILD)
    _write(repo / GREEN_LINK_MD_PATH, GREEN_LINK_MD)
    _write(repo / "src/memoria/storage/constants.py", GREEN_CONST)
    _write(repo / RENDER_CORE_REL, GREEN_RENDER)
    _write(repo / "src/memoria/services/agent/mcp_server.py", GREEN_MCP)
    _write(repo / "src/memoria/services/agent/tools/kb.py", GREEN_TOOLS_KB)
    # C1 需要 ui.py 作为"应用内部资源"的引用证据来源（缺失会触发 NOT_RUN，绿基线必须是"全执行"）
    _write(
        repo / "src/memoria/presentation/api/ui.py",
        'def get_agent_prompt(lang="zh-CN"):\n    return "organize.%s.md" % lang\n',
    )
    packaging = "\n".join(
        [
            '"agent-prompts/kb-agent-readme.md",',
            '"agent-prompts/kb-agent.zh-CN.md",',
            '"agent-prompts/kb-spec.zh-CN.md",',
            '"agent-prompts/fsrs.py",',
            '"docs/preview-formats.md",',
        ]
    )
    _write(repo / PACKAGING_REL, packaging)
    _write(repo / "docs/reference/preview-formats.md", "# preview\n")
    # 字段名/复习数据文件的字面量来源（真实仓库里有，fixture 也需要）
    _write(
        repo / "src/memoria/services/fixture_symbols.py",
        'FIELDS = ("source_id", "targets", "edge_type", "anchor_text", "instances")\n'
        'FILES = ("review/cards.json", "review/progress.json", "cards.json", "progress.json")\n',
    )
    edge_hash = edge_hash or _sha12(repo / GREEN_EDGE_PATH)
    build_hash = build_hash or _sha12(repo / GREEN_BUILD_PATH)
    _write(repo / "resources/agent-prompts/kb-agent-readme.md", GREEN_README.replace("%EDGE%", edge_hash))
    _write(repo / "resources/agent-prompts/kb-agent.zh-CN.md", GREEN_PROMPT.replace("%EDGE%", edge_hash))
    _write(
        repo / "resources/agent-prompts/kb-spec.zh-CN.md",
        GREEN_SPEC.replace("%EDGE%", edge_hash).replace("%BUILD%", build_hash),
    )
    _write(repo / FSRS_REL, GREEN_FSRS)
    return repo


GREEN_EDGE_PATH = EDGE_TYPES_REL
GREEN_BUILD_PATH = KB_BUILD_REL
GREEN_LINK_MD_PATH = LINK_MD_REL


def _context_for(repo: Path, now: date | None = None, stale_days: int = STALE_DAYS_DEFAULT) -> Ctx:
    ctx = Ctx(repo=repo, kb_agent=load_kb_agent(repo))
    run_checks(ctx, now=now, stale_days=stale_days)
    return ctx


def _findings_for(repo: Path, now: date | None = None, stale_days: int = STALE_DAYS_DEFAULT) -> list[Finding]:
    return _context_for(repo, now=now, stale_days=stale_days).findings


def selftest() -> int:
    failures: list[str] = []

    def expect(findings: list[Finding], check: str, severity: str, needle: str, label: str) -> None:
        for finding in findings:
            if finding.check == check and finding.severity == severity and needle in finding.message:
                return
        failures.append(f"{label}: 未报出预期 finding（{severity} {check} …{needle}）")
        print(f"  FAIL {label}")
        return
    _ = expect

    def assert_green(findings: list[Finding], label: str) -> None:
        bad = [f for f in findings if f.severity == FAIL]
        not_run = [f for f in findings if f.severity == NOT_RUN]
        if bad or not_run:
            reason = f"FAIL={[(f.check, f.message) for f in bad]}" if bad else ""
            reason += f" NOT_RUN={[(f.check, f.message) for f in not_run]}" if not_run else ""
            failures.append(f"{label}: 绿 fixture 出现 FAIL/NOT_RUN：{reason}")
            print(f"  FAIL {label}: 绿 fixture 有 FAIL/NOT_RUN")
        else:
            print(f"  PASS {label}")

    def expect_red(findings: list[Finding], check: str, label: str, needle: str = "") -> None:
        hit = [f for f in findings if f.severity == FAIL and f.check == check and needle in f.message]
        if hit:
            print(f"  PASS {label}")
        else:
            failures.append(f"{label}: {check} 未红（needle={needle!r}）")
            print(f"  FAIL {label}: {check} 未红")

    def expect_warn(findings: list[Finding], check: str, label: str, needle: str = "") -> None:
        hit = [f for f in findings if f.severity == WARN and f.check == check and needle in f.message]
        if hit:
            print(f"  PASS {label}")
        else:
            failures.append(f"{label}: {check} 未报 WARN（needle={needle!r}）")
            print(f"  FAIL {label}: {check} 未报 WARN")

    def expect_not_run(repo: Path, check: str, label: str, needle: str = "") -> None:
        ctx = _context_for(repo)
        hit = [f for f in ctx.findings if f.severity == NOT_RUN and f.check == check and needle in f.message]
        status = _summary(ctx.findings, ctx.not_run_checks)["status"]
        if hit and status == "not_run":
            print(f"  PASS {label}")
        else:
            failures.append(f"{label}: 未报 NOT_RUN（check={check}, status={status}）")
            print(f"  FAIL {label}: 未报 NOT_RUN")

    tmp = Path(tempfile.mkdtemp(prefix="prompt-drift-selftest-"))
    try:
        # ── 绿基线 ──
        base = _fixture_repo(tmp / "base")
        assert_green(_findings_for(base), "green:base")
        _ = expect

        # ── C1 红：删一个分发源文件 ──
        repo = _fixture_repo(tmp / "red1")
        os.remove(repo / "resources/agent-prompts/kb-spec.zh-CN.md")
        expect_red(_findings_for(repo), "distribution_integrity", "red:C1 分发源缺失", "分发源文件不存在")

        # ── C1 红：README 未声明新增分发项 ──
        repo = _fixture_repo(tmp / "red1b")
        kb = (repo / KB_AGENT_REL).read_text(encoding="utf-8").replace(
            '("fsrs.py", "fsrs.py"),', '("fsrs.py", "fsrs.py"),\n    ("extra.md", "extra.md"),'
        )
        _write(repo / KB_AGENT_REL, kb)
        _write(repo / "resources/agent-prompts/extra.md", "# extra\n")
        _write(repo / PACKAGING_REL, (repo / PACKAGING_REL).read_text(encoding="utf-8") + '"agent-prompts/extra.md",')
        expect_red(_findings_for(repo), "distribution_integrity", "red:C1 README 未声明", "未在 README 目录表中声明")

        # ── C2 红：提示词教了代码里不存在的符号（width/enlarge/align）──
        repo = _fixture_repo(tmp / "red2")
        spec = repo / "resources/agent-prompts/kb-spec.zh-CN.md"
        spec.write_text(spec.read_text(encoding="utf-8") + "\n图片属性 `width/enlarge/align`。\n", encoding="utf-8")
        expect_red(_findings_for(repo), "symbol_reference", "red:C2 不存在符号", "enlarge")

        # ── C2 红：fsrs 子命令编造 ──
        repo = _fixture_repo(tmp / "red2b")
        prompt = repo / "resources/agent-prompts/kb-agent.zh-CN.md"
        prompt.write_text(
            prompt.read_text(encoding="utf-8") + "\n运行 `python .memoria/agent/fsrs.py reset --date 2026-10-01`。\n",
            encoding="utf-8",
        )
        expect_red(_findings_for(repo), "symbol_reference", "red:C2 fsrs 子命令", "不存在的子命令")

        # ── C3 红：把会被剥离的语法当推荐写法 ──
        repo = _fixture_repo(tmp / "red3")
        spec = repo / "resources/agent-prompts/kb-spec.zh-CN.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + "\n| `[[kp-id#extend]]` | 声明 extend 边 |\n", encoding="utf-8"
        )
        expect_red(_findings_for(repo), "forbidden_syntax", "red:C3 教剥离语法", "会被构建剥离")

        # ── C4 红：版本戳不一致 ──
        repo = _fixture_repo(tmp / "red4")
        spec = repo / "resources/agent-prompts/kb-spec.zh-CN.md"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("spec-version: 1.0.0", "spec-version: 9.9.9"), encoding="utf-8"
        )
        expect_red(_findings_for(repo), "version_stamp", "red:C4 版本戳不一致", "与 kb_agent.SPEC_VERSION")

        # ── C4 红：依赖内容改了但指纹没重签 ──
        repo = _fixture_repo(tmp / "red4b")
        with (repo / GREEN_BUILD_PATH).open("a", encoding="utf-8") as handle:
            handle.write("\n# changed\n")
        expect_red(_findings_for(repo), "version_stamp", "red:C4 依赖指纹失配", "依赖已变更")

        # ── C5 黄：reviewed-on 超过阈值 ──
        repo = _fixture_repo(tmp / "red5")
        findings = _findings_for(repo, now=date(2026, 10, 1) + timedelta(days=STALE_DAYS_DEFAULT + 10))
        if any(f.severity == WARN and f.check == "staleness" for f in findings):
            print("  PASS red:C5 陈旧告警")
        else:
            failures.append("red:C5 陈旧告警未报 WARN")
            print("  FAIL red:C5 陈旧告警")

        # ── 重签流程：--recheck-deps 报告 / 拒绝无 note / 拒绝漏列依赖 / 正确重签后变绿 ──
        import contextlib
        import io as _io

        repo = _fixture_repo(tmp / "resign")
        with (repo / GREEN_BUILD_PATH).open("a", encoding="utf-8") as handle:
            handle.write("\n# changed-again\n")
        rel = "resources/agent-prompts/kb-spec.zh-CN.md"
        buffer = _io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = recheck_report(repo)
        report_text = buffer.getvalue()
        if code == 0 and "CHANGED" in report_text and GREEN_BUILD_PATH in report_text:
            print("  PASS resign:--recheck-deps 列出变更")
        else:
            failures.append("resign:--recheck-deps 未列出变更依赖")
            print("  FAIL resign:--recheck-deps 未列出变更依赖")

        code = main(["--repo", str(repo), "--resign", rel, "--note", "复核了边剥离断言，确认一致"])
        if code == EXIT_USAGE:
            print("  PASS resign:拒绝漏列依赖")
        else:
            failures.append(f"resign:漏列依赖未被拒（exit={code}）")
            print("  FAIL resign:漏列依赖未被拒")

        code = main(
            ["--repo", str(repo), "--resign", rel, "--dep", GREEN_BUILD_PATH, "--note", "短"]
        )
        if code == EXIT_USAGE:
            print("  PASS resign:拒绝过短 note")
        else:
            failures.append(f"resign:过短 note 未被拒（exit={code}）")
            print("  FAIL resign:过短 note 未被拒")

        code = main(
            [
                "--repo",
                str(repo),
                "--resign",
                rel,
                "--dep",
                GREEN_BUILD_PATH,
                "--note",
                "逐条复核 §4 剥离语义与 §8 常见坑，构建行为未变",
            ]
        )
        log_path = repo / RECHECK_LOG_REL
        resigned_bytes = (repo / rel).read_bytes()
        lf_preserved = b"\r\n" not in resigned_bytes
        if (
            code == 0
            and not any(f.severity == FAIL for f in _findings_for(repo))
            and log_path.is_file()
            and lf_preserved
        ):
            print("  PASS resign:正确重签后变绿且留痕（换行保持 LF）")
        else:
            failures.append("resign:正确重签后未变绿/未写日志/换行被改成 CRLF")
            print("  FAIL resign:正确重签后未变绿或未写日志或换行被改")

        # ── PD-1【高】检查无法执行 ⇒ NOT_RUN（跳过≠通过），且 exit=2 ──
        repo = _fixture_repo(tmp / "pd1")
        # 让 edge_types 仍存在（C4 指纹可匹配）但内容解析不出边类型 ⇒ 只有 C3 无法执行
        edge_file = repo / EDGE_TYPES_REL
        edge_file.write_text("EDGE_TYPES = frozenset()\n", encoding="utf-8")
        new_edge_hash = _sha12(edge_file)
        for fixture_name in ("kb-agent-readme.md", "kb-agent.zh-CN.md", "kb-spec.zh-CN.md"):
            fixture_path = repo / "resources" / "agent-prompts" / fixture_name
            fixture_text = fixture_path.read_text(encoding="utf-8")
            fixture_text = re.sub(
                r"src/memoria/graph/edge_types\.py@[0-9a-f]+",
                f"src/memoria/graph/edge_types.py@{new_edge_hash}",
                fixture_text,
            )
            fixture_path.write_text(fixture_text, encoding="utf-8", newline="\n")
        expect_not_run(repo, "forbidden_syntax", "PD-1 C3 依赖不可读 ⇒ NOT_RUN", "C3 无法执行")
        code = main(["--repo", str(repo)])
        if code == EXIT_NOT_RUN:
            print(f"  PASS PD-1 依赖不可读 ⇒ exit={EXIT_NOT_RUN}（not_run 不得判绿）")
        else:
            failures.append(f"PD-1 依赖不可读时 exit 应为 {EXIT_NOT_RUN}，实得 {code}")
            print("  FAIL PD-1 exit 码错误")

        # ── PD-1b 检查自身异常 ⇒ NOT_RUN（不崩溃、不静默）──
        repo = _fixture_repo(tmp / "pd1b")
        original_funcs = globals()["_CHECK_FUNCS"]

        def _probe_boom(_ctx) -> None:
            raise RuntimeError("probe boom")

        try:
            globals()["_CHECK_FUNCS"] = (("probe_crash", _probe_boom),)
            ctx_crash = _context_for(repo)
        finally:
            globals()["_CHECK_FUNCS"] = original_funcs
        crash_status = _summary(ctx_crash.findings, ctx_crash.not_run_checks)["status"]
        if crash_status == "not_run" and any(
            f.severity == NOT_RUN and "检查执行异常" in f.message for f in ctx_crash.findings
        ):
            print("  PASS PD-1b 检查自身异常 ⇒ NOT_RUN（不崩溃）")
        else:
            failures.append("PD-1b 检查自身异常未被登记为 NOT_RUN")
            print("  FAIL PD-1b 检查自身异常未被登记为 NOT_RUN")

        # ── PD-2 点分字段必须每一段都校验（camelCase 不得隐形）──
        repo = _fixture_repo(tmp / "pd2")
        spec = repo / "resources/agent-prompts/kb-spec.zh-CN.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + "\n字段 `range.fakeCamelField`。\n", encoding="utf-8"
        )
        expect_red(_findings_for(repo), "symbol_reference", "PD-2 点分 camelCase 隐形", "fakeCamelField")

        # ── PD-3 隐藏分发路径探测不再跳过 ui.py / kb_agent / build.py ──
        repo = _fixture_repo(tmp / "pd3")
        _write(
            repo / "src/memoria/presentation/api/ui.py",
            'AGENT_DIR = "agent-prompts"\nfor item in AGENT_DIR.iterdir():\n    pass\n',
        )
        expect_warn(
            _findings_for(repo), "distribution_integrity", "PD-3 ui.py 里的目录扫描不再被跳过", "疑似按目录扫描"
        )

        # ── PD-4 孤儿检测递归（嵌套文件也要报）──
        repo = _fixture_repo(tmp / "pd4")
        _write(repo / "resources/agent-prompts/nested/orphan.md", "# orphan\n")
        expect_warn(
            _findings_for(repo), "distribution_integrity", "PD-4 嵌套孤儿 WARN", "nested/orphan.md"
        )

        # ── PD-5 豁免必须紧邻：同行远处的「不要写错别字」不能整行豁免 ──
        repo = _fixture_repo(tmp / "pd5")
        spec = repo / "resources/agent-prompts/kb-spec.zh-CN.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + "\n| `[[kp-id#contain]]`，不要写错别字 |\n",
            encoding="utf-8",
        )
        expect_red(_findings_for(repo), "forbidden_syntax", "PD-5 远处限定词不豁免", "#contain")

        # ── 退出码：正常绿 fixture = 0 ──
        repo = _fixture_repo(tmp / "exit0")
        code = main(["--repo", str(repo)])
        if code == EXIT_OK:
            print(f"  PASS 退出码：绿 fixture ⇒ {EXIT_OK}")
        else:
            failures.append(f"绿 fixture exit 应为 {EXIT_OK}，实得 {code}")
            print("  FAIL 绿 fixture exit 码错误")

        # ── 绿：限定词豁免（遗留写法说明不算教）──
        assert_green(_findings_for(base), "green:legacy-note-allowed")
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        print(f"selftest: {len(failures)} 项未达预期")
        return 1
    print("selftest: PASS（每条检查都有必红 fixture，绿基线不误红）")
    return 0


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════
def _print_deps(repo: Path, paths: list[str]) -> int:
    missing = 0
    for rel in paths:
        target = repo / rel
        if not target.is_file():
            print(f"MISSING {rel}", file=sys.stderr)
            missing += 1
            continue
        print(f"{rel}@{_sha12(target)}")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, AttributeError):
            pass
    parser = argparse.ArgumentParser(
        description="Memoria 知识库 Agent 提示词漂移机检（task-151；task-158 增 NOT_RUN 语义）",
        epilog=(
            "退出码：0 全部执行且无 FAIL / 1 有 FAIL / 2 有检查未执行（NOT_RUN） / 3 用法错误。"
            " 依赖指纹变更后的标准动作：先 --recheck-deps 看清单，"
            "再 --resign <文件> --dep <依赖> --note <复核说明> 逐条重签。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", default=None, help="仓库根目录（默认脚本上两级）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--selftest", action="store_true", help="自证红/绿（临时 fixture，不碰真实仓库）")
    parser.add_argument("--now", default=None, help="覆盖“今天”（YYYY-MM-DD，供陈旧检查复现）")
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS_DEFAULT, help="陈旧阈值天数（默认 90）")
    parser.add_argument("--strict", action="store_true", help="WARN 也算失败（默认只 FAIL 退出 1）")
    parser.add_argument("--print-deps", nargs="+", default=None, help="打印依赖文件当前 sha12（维护头部指纹用）")
    parser.add_argument(
        "--recheck-deps",
        action="store_true",
        help="只读：列出所有提示词的依赖变更 + git 证据 + 要复核的小节 + 重签命令",
    )
    parser.add_argument("--resign", default=None, metavar="PROMPT_FILE", help="按逐条确认重签该提示词文件的依赖指纹")
    parser.add_argument("--dep", action="append", default=[], help="--resign 时逐条确认的依赖路径（可重复）")
    parser.add_argument("--note", default="", help="--resign 的复核说明（≥10 字，写入审计日志）")
    parser.add_argument("--reviewed-on", default=None, help="--resign 的复核日期（缺省今天，YYYY-MM-DD）")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve() if args.repo else ROOT
    if not repo.is_dir():
        print(f"用法错误：仓库目录不存在：{repo}", file=sys.stderr)
        return EXIT_USAGE
    if args.print_deps:
        return _print_deps(repo, args.print_deps)
    if args.recheck_deps:
        return recheck_report(repo)
    if args.resign:
        return resign(repo, args.resign, args.dep, args.note, args.reviewed_on)
    if args.selftest:
        return selftest()
    if not (repo / KB_AGENT_REL).is_file():
        print(f"用法错误：{KB_AGENT_REL} 不存在（--repo 指错了？）", file=sys.stderr)
        return EXIT_USAGE
    now = date.today()
    if args.now:
        try:
            now = date.fromisoformat(args.now)
        except ValueError:
            print(f"用法错误：--now 不是合法日期：{args.now}", file=sys.stderr)
            return EXIT_USAGE
    ctx = Ctx(repo=repo, kb_agent=load_kb_agent(repo))
    findings = run_checks(ctx, now=now, stale_days=args.stale_days)
    _emit(findings, args.json, ctx.not_run_checks)
    summary = _summary(findings, ctx.not_run_checks)
    if summary["status"] == "fail":
        return EXIT_FAIL
    if summary["status"] == "not_run":
        return EXIT_NOT_RUN
    if args.strict and summary[WARN]:
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
