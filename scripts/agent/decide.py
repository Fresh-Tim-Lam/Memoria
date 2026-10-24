#!/usr/bin/env python3
"""决策索引（L10 / lead-dispatch-rules §6）的写入端：D2 通道 + D1 trailer 解析。

**索引不是文库**：本工具只落盘「选了什么 / 放弃什么 / 一句话为什么 / 证据指针」，
长论证留在 evidence 指向的文档与提交里。它**永不创作 why/alternatives**——
这两个字段只能来自人/决策者的输入原文（A6：机器不创作）。

写权限与事实源
--------------
- `team/decisions.jsonl`：**append-only**（进 git）。唯一写入者 = 决策者本人（经本工具）。
  任何提交对它 `removed > 0` ⇒ 视为伪造（A3，由 team_audit::decision_trail 检查）。
- D1（有提交的决策）**不写本文件**：它写在 commit message 的 trailer 里；
  `parse-commit` 只负责**解析成索引行**（只读，不写盘），供 team_audit 抽取。

用法
----
    # D2：无提交的决策（纯对话决策/选型/角色去留）
    python scripts/agent/decide.py append --decided-by lead --scope team-memory \
        --question "新成员如何继承前任经验：复制会话 vs 记忆卡" \
        --choice "记忆卡（≤8KB，append，带免责）" \
        --alternative "复制整段会话|42.6MB×5=210MB 且会传播已推翻结论" \
        --why "载体可 git diff、可审计；错误项已剔除" \
        --evidence doc:team/memory/README.md \
        --rule-ref "docs/guides/agent-team-lessons.md#1" \
        --reversibility R2 --task-id task-87 --at-the-time

    python scripts/agent/decide.py parse-commit <sha> [--json]   # D1：解析 trailer（只读）
    python scripts/agent/decide.py check [--json]                # 校验整个索引（坏行/倒流/重复/证据失效）
    python scripts/agent/decide.py --selftest                    # 自测：每条校验红路径必红

键名（与 lead-dispatch-rules §6.2 逐字一致，改名会破坏机检）
------------------------------------------------------------
Decision / Alternatives / Why / Rule-Ref / Reversibility / Human-Directive / Decision-Id
（commit message 里写作 `Decision: ...`；解析按 `^Key:` 匹配）

写前 fail-closed 六条（设计稿 §2.3.3）
--------------------------------------
① id 形状 `dec-YYYYMMDD-<sha8>` 且不与历史重复；② ts ≥ 文件最后一行 ts（单调）；
③ decided_by ∈ agents.json 的 id（含 retired）/ "human" / "lead"；
④ alternatives 非空 或 no_alternative_reason 非空；⑤ 每条 evidence.ref 可解析
（doc/report=文件存在，commit=git 对象存在，task=任务板/派发日志里存在）；
⑥ reconstructed 必填布尔（A2：事后补录必须显式标记，不得伪装成当时写的）。

退出码：0 成功；1 check 失败；2 写入被拒绝/用法错误；3 parse-commit 无决策记录（显式，不静默空）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DECISIONS = REPO_ROOT / "team" / "decisions.jsonl"
DEFAULT_AGENTS = REPO_ROOT / "team" / "agents.json"
DEFAULT_SNAPSHOT = REPO_ROOT / "team" / "team-board-snapshot.json"
DEFAULT_DISPATCH = REPO_ROOT / "team" / "dispatch-log.jsonl"

ID_RE = re.compile(r"^dec-\d{8}-[0-9a-f]{8}$")
REVERSIBILITY = ("R0", "R1", "R2")
EVIDENCE_KINDS = ("doc", "commit", "task", "report")
TRAILER_KEYS = (
    "Decision", "Alternatives", "Why", "Rule-Ref", "Reversibility", "Human-Directive", "Decision-Id",
)
MAX_DECISION_CHARS = 200
MAX_WHY_CHARS = 200
MAX_HUMAN_DIRECTIVE_CHARS = 120
# A1/A2 时效窗口（设计稿 §2.3.5）
EVIDENCE_EARLY_TOLERANCE_SECONDS = 120      # 决策时间不得早于证据存在时间超过 2 分钟
RECONSTRUCTED_THRESHOLD_SECONDS = 600       # 决策时间晚于证据 mtime 10 分钟 ⇒ 必须 reconstructed:true


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def git(repo: Path, *args: str) -> tuple[bool, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        return False, "", str(exc)
    return proc.returncode == 0, proc.stdout, proc.stderr


def read_jsonl(path: Path) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    bad: list[dict] = []
    if not path.is_file():
        return rows, bad
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            bad.append({"line": lineno, "error": str(exc)})
            continue
        if not isinstance(obj, dict):
            bad.append({"line": lineno, "error": "not-a-json-object"})
            continue
        rows.append(obj)
    return rows, bad


def load_known_deciders(repo: Path) -> set[str]:
    """decided_by 合法集合：agents.json 的 id（含 retired_agents）+ lead + human。"""
    known = {"lead", "human"}
    path = repo / "team" / "agents.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            payload = {}
        for key in ("agents", "retired_agents"):
            for agent in payload.get(key) or []:
                if isinstance(agent, dict) and agent.get("id"):
                    known.add(str(agent["id"]))
    return known


def resolve_evidence(repo: Path, item: dict) -> tuple[bool, str]:
    """返回 (ok, detail)。kind ∈ doc|report ⇒ 文件存在；commit ⇒ git 对象存在；task ⇒ 任务存在。"""
    kind = str(item.get("kind") or "")
    ref = str(item.get("ref") or "")
    if kind not in EVIDENCE_KINDS:
        return False, f"kind={kind!r} 不在 {EVIDENCE_KINDS}"
    if not ref:
        return False, "evidence.ref 为空"
    if kind in ("doc", "report"):
        path = repo / ref
        if not path.is_file():
            return False, f"文件不存在：{ref}"
        declared_sha = item.get("sha256")
        if declared_sha:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != declared_sha:
                return False, f"sha256 不匹配：{ref}（磁盘 {actual[:12]}…）"
        return True, f"{ref} 存在"
    if kind == "commit":
        ok, _out, _err = git(repo, "cat-file", "-e", f"{ref}^{{commit}}")
        return (ok, f"commit {ref} 存在") if ok else (False, f"commit 不存在：{ref}")
    # task：任务板快照 tasks[] 或 dispatch-log 的 task 字段命中即视为存在
    snapshot = repo / "team" / "team-board-snapshot.json"
    if snapshot.is_file():
        try:
            data = json.loads(snapshot.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            data = {}
        if any(str(t.get("id")) == ref for t in (data.get("tasks") or []) if isinstance(t, dict)):
            return True, f"任务 {ref} 在快照 tasks[] 中"
        if any(str(t.get("id")) == ref for t in (data.get("completedRecent") or []) if isinstance(t, dict)):
            return True, f"任务 {ref} 在快照 completedRecent 中"
    dispatch = repo / "team" / "dispatch-log.jsonl"
    if dispatch.is_file():
        for raw in dispatch.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and str(row.get("task")) == ref:
                return True, f"任务 {ref} 在 dispatch-log 中"
    return False, f"任务不存在（快照/dispatch-log 均未命中）：{ref}"


def _evidence_mtime(repo: Path, item: dict) -> datetime | None:
    kind = str(item.get("kind") or "")
    ref = str(item.get("ref") or "")
    if kind not in ("doc", "report"):
        return None
    path = repo / ref
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _tokens_in_text(section: str, text: str) -> bool:
    """规则引用章节的宽松解析：§0.5 L8 / #6.2 / 6.3 等，要求至少一个 token 出现在目标文件。"""
    cleaned = re.sub(r"^#+", "", section).strip()
    tokens = [t for t in re.split(r"[§#\s、,，/·]+", cleaned) if len(t) >= 2]
    if not tokens:
        tokens = [cleaned] if cleaned else []
    return any(token in text for token in tokens)


def validate_rule_ref(repo: Path, rule_ref: str) -> tuple[bool, str]:
    if "#" not in rule_ref:
        return False, f"Rule-Ref 必须是 path#section 形式：{rule_ref!r}"
    path_part, section = rule_ref.split("#", 1)
    path = repo / path_part
    if not path.is_file():
        return False, f"Rule-Ref 指向的文件不存在：{path_part}"
    if not section.strip():
        return False, f"Rule-Ref 缺章节：{rule_ref!r}"
    if not _tokens_in_text(section, path.read_text(encoding="utf-8", errors="replace")):
        return False, f"Rule-Ref 章节无法在文件中解析：{rule_ref!r}"
    return True, ""


def validate_row(repo: Path, row: dict, *, prior_ts: datetime | None, seen_ids: set[str],
                 known_deciders: set[str], lineno: int | None = None) -> list[str]:
    """实现设计稿 §2.3.3 六条 + A1/A2 时效 + Rule-Ref 可解析。返回问题列表（空=合法）。"""
    problems: list[str] = []

    def add(message: str) -> None:
        prefix = f"line {lineno}: " if lineno else ""
        problems.append(prefix + message)

    rid = row.get("id")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        add(f"id={rid!r} 不匹配 dec-YYYYMMDD-<sha8>")
    elif rid in seen_ids:
        add(f"id 重复：{rid}")
    else:
        seen_ids.add(rid)

    stamp = parse_ts(row.get("ts"))
    if stamp is None:
        add(f"ts={row.get('ts')!r} 不可解析")
    elif prior_ts is not None and stamp < prior_ts:
        add("ts 早于上一条记录（append-only 时间倒流 ⇒ 疑似改写历史）")

    decided_by = str(row.get("decided_by") or "")
    if decided_by not in known_deciders:
        add(f"decided_by={decided_by!r} 不是 agents.json 里的 id，也不是 human/lead")

    alternatives = row.get("alternatives")
    if not alternatives and not row.get("no_alternative_reason"):
        add("alternatives 为空且无 no_alternative_reason（决策缺少被放弃项）")
    if alternatives is not None:
        if not isinstance(alternatives, list) or not alternatives:
            add("alternatives 必须是非空数组（或省略并给 no_alternative_reason）")
        else:
            for index, alt in enumerate(alternatives):
                if not isinstance(alt, dict) or not alt.get("option") or not alt.get("why_rejected"):
                    add(f"alternatives[{index}] 必须含 option 与 why_rejected")

    for key, limit in (("question", 500), ("choice", 500), ("why", MAX_WHY_CHARS)):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            add(f"缺 {key}（决策索引必须有 {key}）")
        elif len(value) > limit:
            add(f"{key} 超过 {limit} 字符（索引不是文库，长论证放 evidence）")

    reconstructed = row.get("reconstructed")
    if not isinstance(reconstructed, bool):
        add("reconstructed 必须是布尔（A2：事后补录必须显式标记）")

    reversibility = row.get("reversibility")
    if reversibility is not None and reversibility not in REVERSIBILITY:
        add(f"reversibility={reversibility!r} 不在 {REVERSIBILITY}")

    rule_refs = row.get("rule_refs") or []
    if not isinstance(rule_refs, list):
        add("rule_refs 必须是数组")
    else:
        for rule_ref in rule_refs:
            ok, detail = validate_rule_ref(repo, str(rule_ref))
            if not ok:
                add(detail)

    evidence = row.get("evidence") or []
    if not isinstance(evidence, list):
        add("evidence 必须是数组")
        evidence = []
    max_evidence_mtime: datetime | None = None
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            add(f"evidence[{index}] 必须是对象 {{kind, ref}}")
            continue
        ok, detail = resolve_evidence(repo, item)
        if not ok:
            add(f"evidence[{index}] 不可解析：{detail}")
        mtime = _evidence_mtime(repo, item)
        if mtime is not None and (max_evidence_mtime is None or mtime > max_evidence_mtime):
            max_evidence_mtime = mtime

    if stamp is not None and max_evidence_mtime is not None:
        if stamp < max_evidence_mtime - timedelta_seconds(EVIDENCE_EARLY_TOLERANCE_SECONDS):
            add("A1：决策时间早于证据存在时间（不可能当场引用尚未存在的证据）")
        if (not reconstructed
                and stamp > max_evidence_mtime + timedelta_seconds(RECONSTRUCTED_THRESHOLD_SECONDS)):
            add("A2：决策时间晚于证据 10 分钟以上 ⇒ 必须 reconstructed:true（事后补录不得伪装当场）")

    return problems


def timedelta_seconds(seconds: int):
    from datetime import timedelta
    return timedelta(seconds=seconds)


def choose_id(repo: Path, question: str, choice: str, why: str, ts: str) -> str:
    digest = hashlib.sha256(f"{question}|{choice}|{why}|{ts}".encode("utf-8")).hexdigest()[:8]
    return f"dec-{parse_ts(ts).strftime('%Y%m%d') if parse_ts(ts) else datetime.now().strftime('%Y%m%d')}-{digest}"


def build_alternative(raw: str) -> dict:
    """`option|why_rejected`（也接受 `option@why_rejected`）。缺 why_rejected ⇒ 报错，不猜。"""
    text = raw.strip()
    separator = "|" if "|" in text else ("@" if "@" in text else None)
    if separator is None:
        raise ValueError(f"--alternative 必须是 '选项|why_rejected' 形式：{raw!r}")
    option, why_rejected = text.split(separator, 1)
    if not option.strip() or not why_rejected.strip():
        raise ValueError(f"--alternative 的 option/why_rejected 都不能为空：{raw!r}")
    return {"option": option.strip(), "why_rejected": why_rejected.strip()}


def parse_evidence_arg(raw: str) -> dict:
    """`kind:ref` 或 `kind:ref#sha256=<hex>`。"""
    text = raw.strip()
    if ":" not in text:
        raise ValueError(f"--evidence 必须是 kind:ref 形式：{raw!r}")
    kind, rest = text.split(":", 1)
    sha = None
    if "#sha256=" in rest:
        rest, sha = rest.split("#sha256=", 1)
        sha = sha.strip().lower()
    item = {"kind": kind.strip(), "ref": rest.strip()}
    if sha:
        item["sha256"] = sha
    return item


def append_decision(repo: Path, decisions_path: Path, args) -> int:
    rows, bad = read_jsonl(decisions_path)
    if bad:
        print("FAIL: 决策索引已有坏行，拒绝在其后追加（先修坏行/恢复；A3 append-only）", file=sys.stderr)
        for item in bad[:5]:
            print(f"  - line {item['line']}: {item['error']}", file=sys.stderr)
        return 2
    prior_ts = parse_ts(rows[-1].get("ts")) if rows else None
    seen_ids = {str(row.get("id")) for row in rows}
    known_deciders = load_known_deciders(repo)

    ts = args.ts or now_iso()
    if parse_ts(ts) is None:
        print(f"FAIL: --ts {ts!r} 不可解析", file=sys.stderr)
        return 2
    decision_id = args.id or choose_id(repo, args.question, args.choice, args.why, ts)

    try:
        alternatives = [build_alternative(raw) for raw in (args.alternative or [])]
        evidence = [parse_evidence_arg(raw) for raw in (args.evidence or [])]
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    row = {
        "id": decision_id,
        "ts": ts,
        "decided_by": args.decided_by,
        "scope": args.scope,
        "question": args.question,
        "choice": args.choice,
        "alternatives": alternatives,
        "why": args.why,
        "evidence": evidence,
        "rule_refs": args.rule_ref or [],
        "reversibility": args.reversibility,
        "task_id": args.task_id,
        "reconstructed": bool(args.reconstructed),
        "supersedes": args.supersedes,
        "review": {"by": None, "at": None, "verdict": None},
    }
    if args.no_alternative_reason:
        row["no_alternative_reason"] = args.no_alternative_reason
    if args.human_directive:
        if len(args.human_directive) > MAX_HUMAN_DIRECTIVE_CHARS:
            print(f"FAIL: --human-directive 超过 {MAX_HUMAN_DIRECTIVE_CHARS} 字符（须为原文摘录）", file=sys.stderr)
            return 2
        row["human_directive"] = args.human_directive
    row = {key: value for key, value in row.items() if value is not None}

    # 必填布尔：--reconstructed / --at-the-time 二选一（缺省不允许，A2 要显式）
    if not args.reconstructed and not args.at_the_time:
        print("FAIL: 必须显式声明 --reconstructed（事后补录）或 --at-the-time（当时记录）——"
              "不允许缺省（A2 防伪装）", file=sys.stderr)
        return 2

    problems = validate_row(repo, row, prior_ts=prior_ts, seen_ids=seen_ids,
                            known_deciders=known_deciders)
    # 发版/回退触发的决策必须有 Alternatives（§6.2）
    if row.get("reversibility") == "R1" and not row.get("alternatives") and not row.get("no_alternative_reason"):
        problems.append("reversibility=R1（单向门）必须给 alternatives 或 no_alternative_reason")
    if problems:
        print("FAIL: 拒绝写入非法决策记录（fail-closed）：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    with decisions_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))
    return 0


def parse_commit_trailers(message: str) -> tuple[dict, list[str]]:
    """从 commit message 尾部解析 trailer 块；返回 ({key: value}, 出现过的未知键)。"""
    lines = [line.rstrip() for line in message.splitlines()]
    trailers: dict[str, str] = {}
    unknown: list[str] = []
    index = len(lines) - 1
    while index >= 0:
        line = lines[index]
        if not line.strip():
            if trailers:  # 空行结束 trailer 块
                break
            index -= 1
            continue
        match = re.match(r"^([A-Za-z][A-Za-z-]*):\s*(.*)$", line)
        if not match:
            break
        key, value = match.group(1), match.group(2).strip()
        if key in TRAILER_KEYS:
            trailers.setdefault(key, value)
        else:
            unknown.append(key)
        index -= 1
    return trailers, unknown


def parse_commit(repo: Path, sha: str, decided_by: str) -> int:
    ok, out, err = git(repo, "show", "-s", "--format=%H%x1f%aI%x1f%an%x1f%B", sha)
    if not ok:
        print(f"FAIL: 无法读取提交 {sha}：{err.strip()}", file=sys.stderr)
        return 2
    parts = out.split("\x1f", 3)
    if len(parts) < 4:
        print(f"FAIL: 提交 {sha} 输出格式异常", file=sys.stderr)
        return 2
    full_sha, author_iso, _author, message = parts
    trailers, unknown = parse_commit_trailers(message)
    if "Decision" not in trailers and "Why" not in trailers:
        payload = {
            "status": "no-trailer",
            "commit": full_sha.strip(),
            "author_date": author_iso.strip(),
            "detail": "该提交没有 Decision/Why trailer ⇒ 无决策记录（不是空成功）",
            "trailers_found": sorted(trailers),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 3

    problems: list[str] = []
    for key in ("Decision", "Why"):
        if not trailers.get(key):
            problems.append(f"缺 {key}:（≤200 字符、非空）")
        elif len(trailers[key]) > MAX_DECISION_CHARS:
            problems.append(f"{key}: 超过 {MAX_DECISION_CHARS} 字符（正文放 body，不放 trailer）")
    reversibility = trailers.get("Reversibility")
    if reversibility is not None and reversibility not in REVERSIBILITY:
        problems.append(f"Reversibility={reversibility!r} 不在 {REVERSIBILITY}")
    alternatives_raw = trailers.get("Alternatives") or ""
    is_release_or_revert = bool(re.search(r"^chore\(release\)|^Revert\b", message.splitlines()[0] if message.splitlines() else ""))
    if (is_release_or_revert or reversibility == "R1") and not alternatives_raw:
        problems.append("发版/回退（或 Reversibility=R1）必须写 Alternatives:")
    if alternatives_raw and "rejected" not in alternatives_raw:
        problems.append("Alternatives: 每项必须含 rejected: 说明")
    rule_ref = trailers.get("Rule-Ref")
    if rule_ref:
        ok_ref, detail = validate_rule_ref(repo, rule_ref)
        if not ok_ref:
            problems.append(f"Rule-Ref 不可解析：{detail}")
    human = trailers.get("Human-Directive")
    if human and len(human) > MAX_HUMAN_DIRECTIVE_CHARS:
        problems.append(f"Human-Directive 超过 {MAX_HUMAN_DIRECTIVE_CHARS} 字符（须为原文摘录）")
    decision_id = trailers.get("Decision-Id")
    if decision_id and not ID_RE.match(decision_id):
        problems.append(f"Decision-Id={decision_id!r} 不匹配 dec-YYYYMMDD-<sha8>")

    stamp = parse_ts(author_iso.strip())
    index_row = {
        "source": "commit",
        "commit": full_sha.strip(),
        "ts": stamp.isoformat(timespec="seconds") if stamp else None,
        "decided_by": decided_by,
        "decision_id": decision_id or (f"dec-{stamp.strftime('%Y%m%d')}-{full_sha.strip()[:8]}" if stamp else None),
        "decision": trailers.get("Decision"),
        "why": trailers.get("Why"),
        "alternatives": alternatives_raw,
        "rule_ref": rule_ref,
        "reversibility": reversibility or "R2",
        "human_directive": human,
        "problems": problems,
        "status": "ok" if not problems else "invalid-trailer",
    }
    print(json.dumps(index_row, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def check_index(repo: Path, decisions_path: Path, as_json: bool) -> int:
    rows, bad = read_jsonl(decisions_path)
    problems: list[dict] = [{"line": item["line"], "rule": "json", "detail": item["error"]} for item in bad]
    if not decisions_path.is_file():
        problems.append({"line": 0, "rule": "missing", "detail": f"{decisions_path.name} 不存在（输入为 0 不得判绿）"})
    if not rows and not bad and decisions_path.is_file():
        problems.append({"line": 0, "rule": "empty", "detail": "决策索引为空（输入为 0 不得判绿）"})
    seen_ids: set[str] = set()
    known_deciders = load_known_deciders(repo)
    prior_ts: datetime | None = None
    for index, row in enumerate(rows, 1):
        for message in validate_row(repo, row, prior_ts=prior_ts, seen_ids=seen_ids,
                                    known_deciders=known_deciders, lineno=index):
            problems.append({"line": index, "rule": "schema", "detail": message})
        stamp = parse_ts(row.get("ts"))
        if stamp is not None:
            prior_ts = stamp
    report = {
        "path": str(decisions_path),
        "count": len(rows),
        "bad_lines": len(bad),
        "checked_count": len(rows),
        "problems": problems,
        "ok": not problems,
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if report['ok'] else 'FAIL'}: {decisions_path} — {len(rows)} 条决策，"
              f"checked_count={report['checked_count']}，problems={len(problems)}")
        for item in problems[:20]:
            print(f"  - line {item['line']} [{item['rule']}] {item['detail']}")
    return 0 if report["ok"] else 1


# ---------------------------------------------------------------------------
# 自测：每条校验红路径必红
# ---------------------------------------------------------------------------
def _selftest_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _selftest_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def _capture_main(argv: list[str]) -> tuple[int, str, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def selftest() -> int:
    failures: list[str] = []

    def expect(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    _force_utf8_stdio()
    with tempfile.TemporaryDirectory(prefix="decide-selftest-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        _selftest_write(repo / "docs" / "note.md", "# note\n")
        _selftest_write(repo / "docs" / "guides" / "agent-team-lessons.md",
                        "# lessons\n\n## 1. 假绿与假红\n说明\n\n## 6. 报告与记账\n说明\n")
        _selftest_write(repo / "team" / "agents.json", json.dumps({
            "agents": [{"id": "lead", "status": "active"}],
            "retired_agents": [{"id": "old-member", "status": "retired-in-dsh"}],
        }, ensure_ascii=False))
        _selftest_write(repo / "team" / "dispatch-log.jsonl",
                        json.dumps({"ts": now_iso(), "actor": "lead", "phase": "spawn",
                                    "target": "x", "task": "task-999"}, ensure_ascii=False) + "\n")
        _selftest_git(repo, "init", "-q")
        _selftest_git(repo, "config", "user.email", "selftest@example.com")
        _selftest_git(repo, "config", "user.name", "selftest")
        _selftest_git(repo, "config", "commit.gpgsign", "false")
        _selftest_git(repo, "add", "-A")
        _selftest_git(repo, "commit", "-q", "-m", "chore: fixture")
        _ok, commit_out, _ = git(repo, "rev-parse", "HEAD")
        head = commit_out.strip()
        decisions = repo / "team" / "decisions.jsonl"

        base = ["append", "--repo", str(repo), "--file", str(decisions),
                "--decided-by", "lead", "--question", "选 A 还是 B", "--choice", "选 A",
                "--why", "A 可回滚", "--at-the-time"]

        # 绿：合法追加
        code, out, err = _capture_main(base + ["--alternative", "B|B 不可回滚",
                                               "--evidence", f"commit:{head}",
                                               "--rule-ref", "docs/guides/agent-team-lessons.md#1"])
        expect("green-append-exit0", code == 0)
        expect("green-append-written", decisions.is_file() and len(decisions.read_text(encoding="utf-8").splitlines()) == 1)
        expect("green-append-id-shape", ID_RE.match(json.loads(decisions.read_text(encoding="utf-8").splitlines()[0])["id"]) is not None)
        first_id = json.loads(decisions.read_text(encoding="utf-8").splitlines()[0])["id"]

        # 红 1：缺 alternatives 且无 no_alternative_reason
        code, _out, err = _capture_main(base + ["--choice", "选 C", "--why", "C 更简单"])
        expect("red-missing-alternatives", code == 2 and "alternatives" in err)

        # 红 2：非法 id 形状
        code, _out, err = _capture_main(base + ["--id", "bad-id", "--alternative", "B|x",
                                                "--evidence", f"commit:{head}"])
        expect("red-bad-id-shape", code == 2 and "id=" in err)

        # 红 3：id 重复
        code, _out, err = _capture_main(base + ["--id", first_id, "--alternative", "B|x",
                                                "--evidence", f"commit:{head}"])
        expect("red-duplicate-id", code == 2 and "id 重复" in err)

        # 红 4：ts 倒流
        code, _out, err = _capture_main(base + ["--ts", "2020-01-01T00:00:00+08:00",
                                                "--alternative", "B|x", "--evidence", f"commit:{head}"])
        expect("red-ts-backwards", code == 2 and "时间倒流" in err)

        # 红 5：decided_by 非法
        code, _out, err = _capture_main(base + ["--decided-by", "nobody", "--alternative", "B|x",
                                                "--evidence", f"commit:{head}"])
        expect("red-decided-by", code == 2 and "decided_by" in err)

        # 红 6：evidence 不可解析
        code, _out, err = _capture_main(base + ["--alternative", "B|x", "--evidence", "doc:docs/not-exist.md"])
        expect("red-bad-evidence", code == 2 and "不可解析" in err)

        # 红 7：既非 reconstructed 也非 at-the-time
        code, _out, err = _capture_main(["append", "--repo", str(repo), "--file", str(decisions),
                                         "--decided-by", "lead", "--question", "Q", "--choice", "A",
                                         "--why", "w", "--alternative", "B|x", "--evidence", f"commit:{head}"])
        expect("red-reconstructed-required", code == 2 and "reconstructed" in err)

        # 红 8：不存在的 Rule-Ref
        code, _out, err = _capture_main(base + ["--alternative", "B|x", "--evidence", f"commit:{head}",
                                                "--rule-ref", "docs/guides/agent-team-lessons.md#NoSuchSection99"])
        expect("red-bad-rule-ref", code == 2 and "Rule-Ref" in err)

        # 绿 2：check 合法索引
        code, out, _err = _capture_main(["check", "--repo", str(repo), "--file", str(decisions), "--json"])
        report = json.loads(out)
        expect("green-check-pass", code == 0 and report["ok"] is True and report["checked_count"] == 1)

        # 红 9：坏 JSON 行 ⇒ check FAIL
        with decisions.open("a", encoding="utf-8") as fh:
            fh.write("not-json\n")
        code, out, _err = _capture_main(["check", "--repo", str(repo), "--file", str(decisions), "--json"])
        expect("red-check-bad-json", code == 1 and json.loads(out)["bad_lines"] == 1)
        # 还原
        decisions.write_text("\n".join(decisions.read_text(encoding="utf-8").splitlines()[:-1]) + "\n",
                             encoding="utf-8")

        # 红 10：ts 倒流（手写第二行早于第一行）⇒ check FAIL
        row1 = json.loads(decisions.read_text(encoding="utf-8").splitlines()[0])
        row2 = dict(row1, id="dec-20200101-deadbeef", ts="2020-01-01T00:00:00+08:00")
        decisions.write_text(json.dumps(row1, ensure_ascii=False) + "\n" +
                             json.dumps(row2, ensure_ascii=False) + "\n", encoding="utf-8")
        code, out, _err = _capture_main(["check", "--repo", str(repo), "--file", str(decisions), "--json"])
        expect("red-check-ts-backwards", code == 1 and any(
            "时间倒流" in item["detail"] for item in json.loads(out)["problems"]))
        # 还原为单行
        decisions.write_text(json.dumps(row1, ensure_ascii=False) + "\n", encoding="utf-8")

        # parse-commit：无 trailer ⇒ 必须显式 no-trailer（exit 3，不是 0）
        code, out, _err = _capture_main(["parse-commit", head, "--repo", str(repo)])
        payload = json.loads(out)
        expect("no-trailer-explicit", code == 3 and payload["status"] == "no-trailer")

        # parse-commit：带 trailer ⇒ 解析出索引行
        _selftest_write(repo / "docs" / "note.md", "# note v2\n")
        _selftest_git(repo, "add", "-A")
        _selftest_git(repo, "commit", "-q", "-m",
                      "feat: 测试决策 trailer\n\n"
                      "Decision: 采用 A 方案\n"
                      "Alternatives: B 方案 (rejected: 不可回滚)\n"
                      "Why: A 可回滚且可审计\n"
                      "Rule-Ref: docs/guides/agent-team-lessons.md#1\n"
                      "Reversibility: R2\n")
        _ok, out_trailer, _ = git(repo, "rev-parse", "HEAD")
        code, out, _err = _capture_main(["parse-commit", out_trailer.strip(), "--repo", str(repo)])
        payload = json.loads(out)
        expect("parse-trailer-ok", code == 0 and payload["status"] == "ok"
               and payload["decision"] == "采用 A 方案" and "不可回滚" in payload["alternatives"])
        expect("parse-trailer-why", payload["why"] == "A 可回滚且可审计")

        # 红 11：发版提交缺 Alternatives ⇒ parse-commit 必须报 invalid
        _selftest_write(repo / "docs" / "note.md", "# note v3\n")
        _selftest_git(repo, "add", "-A")
        _selftest_git(repo, "commit", "-q", "-m",
                      "chore(release): v9.9.9\n\nDecision: 发布 v9.9.9\nWhy: 测试\n")
        _ok, out_release, _ = git(repo, "rev-parse", "HEAD")
        code, out, _err = _capture_main(["parse-commit", out_release.strip(), "--repo", str(repo)])
        payload = json.loads(out)
        expect("parse-release-missing-alternatives", code == 1 and payload["status"] == "invalid-trailer"
               and any("Alternatives" in problem for problem in payload["problems"]))

    if failures:
        print(f"FAIL: {', '.join(failures)}")
        return 1
    print("PASS: decide.py selftest（绿：合法 append/check/parse；红 ≥10 类：缺 alternatives / 坏 id / "
          "重复 id / ts 倒流 / 非法 decided_by / evidence 不可解析 / reconstructed 缺省 / Rule-Ref 不可解析 / "
          "坏 JSON 行 / 发版缺 Alternatives / parse-commit 无 trailer 显式 no-trailer）")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="决策索引（D2 写入端 + D1 trailer 解析；append-only）")
    parser.add_argument("--selftest", action="store_true", help="运行自测并退出")
    parser.add_argument("--repo", default=None, help="仓库根（默认脚本所在仓库）")
    sub = parser.add_subparsers(dest="command")

    append_parser = sub.add_parser("append", help="追加一条决策（fail-closed 六条校验）")
    append_parser.add_argument("--file", default=None, help="决策索引路径（默认 team/decisions.jsonl）")
    append_parser.add_argument("--repo", default=None, help="仓库根（也可放在子命令后）")
    append_parser.add_argument("--id", help="显式 decision id（默认按内容派生 dec-YYYYMMDD-<sha8>）")
    append_parser.add_argument("--ts", help="显式时间戳（默认当前；仅回填时用，须单调）")
    append_parser.add_argument("--decided-by", default="lead", help="决策者 id（agents.json / human / lead）")
    append_parser.add_argument("--scope", help="自由标签（检索用）")
    append_parser.add_argument("--question", required=True, help="决策要回答的问题")
    append_parser.add_argument("--choice", required=True, help="选了什么（一句话）")
    append_parser.add_argument("--alternative", action="append", metavar="OPTION|WHY_REJECTED",
                               help="被放弃项（可多次；每项必须写 why_rejected）")
    append_parser.add_argument("--no-alternative-reason", help="确实没有备选时的显式理由")
    append_parser.add_argument("--why", required=True, help="一句话为什么（≤200 字符）")
    append_parser.add_argument("--evidence", action="append", metavar="KIND:REF",
                               help="证据指针：doc:/report:/commit:/task:（可多次）")
    append_parser.add_argument("--rule-ref", action="append", help="path#section（可多次，必须可解析）")
    append_parser.add_argument("--reversibility", choices=REVERSIBILITY, default="R2")
    append_parser.add_argument("--task-id", help="关联任务 id")
    append_parser.add_argument("--human-directive", help="人指令原文摘录（≤120 字符）")
    append_parser.add_argument("--supersedes", help="被本决策取代的历史 decision id")
    group = append_parser.add_mutually_exclusive_group()
    group.add_argument("--reconstructed", action="store_true", help="事后补录（A2 会要求显式）")
    group.add_argument("--at-the-time", action="store_true", help="当时记录（与 --reconstructed 二选一）")

    parse_parser = sub.add_parser("parse-commit", help="解析提交 trailer 成决策索引行（只读）")
    parse_parser.add_argument("sha", help="提交 sha")
    parse_parser.add_argument("--repo", default=None, help="仓库根")
    parse_parser.add_argument("--decided-by", default="lead", help="决策者（缺省 lead，可按 commit 归属改）")

    check_parser = sub.add_parser("check", help="校验决策索引（坏行/倒流/重复/证据失效）")
    check_parser.add_argument("--file", default=None, help="决策索引路径（默认 team/decisions.jsonl）")
    check_parser.add_argument("--repo", default=None, help="仓库根")
    check_parser.add_argument("--json", action="store_true", help="机器可读")
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    repo = Path(args.repo).resolve() if getattr(args, "repo", None) else REPO_ROOT
    if args.command == "append":
        decisions_path = Path(args.file).resolve() if args.file else (repo / "team" / "decisions.jsonl")
        return append_decision(repo, decisions_path, args)
    if args.command == "parse-commit":
        return parse_commit(repo, args.sha, args.decided_by)
    if args.command == "check":
        decisions_path = Path(args.file).resolve() if args.file else (repo / "team" / "decisions.jsonl")
        return check_index(repo, decisions_path, args.json)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
