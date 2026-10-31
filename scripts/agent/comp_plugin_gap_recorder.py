#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插件能力缺失登记器（comp.plugin-gap-recorder，task-274 从 artifacts 草案提升为 tracked 工具）：
校验一次插件能力缺失观察并渲染机器可读的 TODO-INBOX 草稿块（validate a plugin capability-gap observation
and render a machine-readable TODO-INBOX draft block.

本文件由 artifacts/agent/plugin-design/comp_plugin_gap_recorder.py 迁移（task-274）；只做校验与草稿渲染，不
edit TODO-INBOX.md, does not create tickets, and does not call the Team API.

Input: one JSON object (file or stdin) with
  gapId, observedAt, sessionId|pluginVersion, expected, actual, reproCommand,
  evidencePaths[], capabilityRef (componentId or null), severity (P0|P1|P2)
Optional: rawObservation / notes (verbatim; never rewritten).

Output: stdout JSON {ok, missing, record?, draft?}; --out writes the TODO-INBOX
draft markdown; --registry also verifies capabilityRef against the component
registry.
Exit: 0 complete; 1 schema/gap invalid; 2 empty input or usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "docs/design/component-registry.v2.json"
GAP_ID_RE = re.compile(r"^GAP-[A-Za-z0-9][A-Za-z0-9-]{2,63}$")
REQUIRED = (
    "gapId", "observedAt", "expected", "actual", "reproCommand",
    "evidencePaths", "capabilityRef", "severity",
)


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_iso_datetime(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _registry_ids(registry_path: Path | None) -> set[str] | None:
    if registry_path is None or not registry_path.exists():
        return None
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    components = data.get("components") if isinstance(data, dict) else None
    if not isinstance(components, list):
        return None
    return {item.get("id") for item in components if isinstance(item, dict) and isinstance(item.get("id"), str)}


def validate(observation: object, registry_path: Path | None = None) -> dict:
    """Return {ok, missing[], record?, draft?} without editing any file."""
    if not isinstance(observation, dict) or not observation:
        return {"ok": False, "missing": list(REQUIRED), "error": "EMPTY_INPUT：输入为空或不是 JSON object，空输入不得放行"}
    missing: list[str] = []
    for field in REQUIRED:
        if field not in observation:
            missing.append(field)
    if "sessionId" not in observation and "pluginVersion" not in observation:
        missing.append("sessionId|pluginVersion")
    if _text(observation.get("gapId")) and not GAP_ID_RE.match(_text(observation.get("gapId"))):
        return {"ok": False, "missing": missing, "error": "INVALID_GAP_ID：gapId 必须匹配 GAP-<id>"}
    if "gapId" in observation and _text(observation.get("gapId")) == "":
        missing.append("gapId")
    if "observedAt" in observation and not _is_iso_datetime(observation.get("observedAt")):
        missing.append("observedAt")
    for field in ("expected", "actual", "reproCommand"):
        if field in observation and _text(observation.get(field)) == "":
            missing.append(field)
    if "sessionId" in observation and _text(observation.get("sessionId")) == "":
        missing.append("sessionId")
    if "pluginVersion" in observation and _text(observation.get("pluginVersion")) == "":
        missing.append("pluginVersion")
    evidence = observation.get("evidencePaths")
    if "evidencePaths" in observation:
        if not isinstance(evidence, list) or len(evidence) == 0 or not all(
                isinstance(item, str) and item.strip() for item in evidence):
            missing.append("evidencePaths")
    severity = observation.get("severity")
    if "severity" in observation and severity not in ("P0", "P1", "P2"):
        missing.append("severity")
    capability = observation.get("capabilityRef", None)
    if "capabilityRef" in observation:
        if capability is not None and (not isinstance(capability, str) or not capability.strip()):
            missing.append("capabilityRef")
        elif isinstance(capability, str) and capability.strip():
            ids = _registry_ids(registry_path)
            if ids is not None and capability.strip() not in ids:
                missing.append("capabilityRef")
    missing = list(dict.fromkeys(missing))
    if missing:
        return {"ok": False, "missing": missing, "error": "MISSING_OR_INVALID_FIELDS"}
    record = {
        "schema": "plugin-gap-record/v1",
        "gapId": _text(observation.get("gapId")),
        "observedAt": _text(observation.get("observedAt")),
        "sessionId": _text(observation.get("sessionId")) or None,
        "pluginVersion": _text(observation.get("pluginVersion")) or None,
        "expected": _text(observation.get("expected")),
        "actual": _text(observation.get("actual")),
        "reproCommand": _text(observation.get("reproCommand")),
        "evidencePaths": [item.strip() for item in observation["evidencePaths"]],
        "capabilityRef": (capability.strip() if isinstance(capability, str) and capability.strip() else None),
        "severity": severity,
        "rawObservation": observation.get("rawObservation"),
        "notes": observation.get("notes"),
    }
    draft = render_draft(record)
    return {"ok": True, "missing": [], "record": record, "draft": draft}


def render_draft(record: dict) -> str:
    """Render a TODO-INBOX draft: human block + fenced machine JSON."""
    title = f"{record['gapId']}：插件能力缺失（{record['severity']}）"
    lines = [
        f"### {title}",
        "",
        f"- gapId: `{record['gapId']}`",
        f"- observedAt: `{record['observedAt']}`",
        f"- sessionId: `{record['sessionId']}`" if record["sessionId"] else "- sessionId: —",
        f"- pluginVersion: `{record['pluginVersion']}`" if record["pluginVersion"] else "- pluginVersion: —",
        f"- expected: {record['expected']}",
        f"- actual: {record['actual']}",
        f"- reproCommand: `{record['reproCommand']}`",
        f"- evidencePaths: {', '.join(f'`{path}`' for path in record['evidencePaths'])}",
        f"- capabilityRef: `{record['capabilityRef']}`" if record["capabilityRef"] else "- capabilityRef: null",
        f"- severity: `{record['severity']}`",
        "",
    ]
    if record.get("rawObservation") is not None:
        lines += ["原始观察（不改写）：", "", "```text", str(record["rawObservation"]), "```", ""]
    lines += ["```json", json.dumps(record, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def selftest() -> int:
    failures: list[str] = []
    good = {
        "gapId": "GAP-SELFTEST-01",
        "observedAt": "2026-10-31T01:00:00Z",
        "sessionId": "session-selftest",
        "expected": "snapshot tasks have description",
        "actual": "snapshot tasks lack description",
        "reproCommand": "python scripts/agent/comp_task_classifier.py --board snapshot.json",
        "evidencePaths": ["artifacts/agent/plugin-design/evidence/example.json"],
        "capabilityRef": "comp.inbox-digester",
        "severity": "P1",
    }
    result = validate(good)
    if not result["ok"] or result["missing"]:
        failures.append("完整样例应 ok=true/missing=[]")
    if "```json" not in result.get("draft", ""):
        failures.append("草稿应含 fenced JSON")
    bad = dict(good)
    bad.pop("reproCommand")
    bad_result = validate(bad)
    if bad_result["ok"] or bad_result["missing"] != ["reproCommand"]:
        failures.append(f"缺 reproCommand 应 ok=false/missing=['reproCommand']，实际 {bad_result}")
    empty = validate({})
    if empty["ok"] or "EMPTY_INPUT" not in (empty.get("error") or ""):
        failures.append("空输入应 ok=false + EMPTY_INPUT")
    bad_severity = dict(good, severity="P9")
    if validate(bad_severity)["ok"]:
        failures.append("非法 severity 应失败")
    bad_registry = dict(good, capabilityRef="comp.does-not-exist")
    if validate(bad_registry, DEFAULT_REGISTRY)["ok"]:
        failures.append("registry 中不存在的 capabilityRef 应失败")
    if failures:
        print("SELFTEST FAIL")
        for failure in failures:
            print(" -", failure)
        return 1
    print("SELFTEST PASS：完整样例通过；缺 reproCommand 精确报错；空输入拒绝；severity/registry 校验生效。")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8()
    parser = argparse.ArgumentParser(description="插件能力缺失登记（comp.plugin-gap-recorder，草案）")
    parser.add_argument("--input", default="-", help="JSON 文件路径，- 表示 stdin")
    parser.add_argument("--out", help="写入 TODO-INBOX 草稿 markdown")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="组件库 JSON（默认 v2）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(args.input).read_text(encoding="utf-8")
    except OSError as error:
        print(json.dumps({"ok": False, "missing": list(REQUIRED), "error": f"READ_ERROR：{error}"}, ensure_ascii=False))
        return 2
    if not raw.strip():
        print(json.dumps({"ok": False, "missing": list(REQUIRED), "error": "EMPTY_INPUT：空输入不得放行"}, ensure_ascii=False))
        return 2
    try:
        observation = json.loads(raw)
    except json.JSONDecodeError as error:
        print(json.dumps({"ok": False, "missing": list(REQUIRED), "error": f"INVALID_JSON：{error}"}, ensure_ascii=False))
        return 2
    result = validate(observation, Path(args.registry))
    if result["ok"] and args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result["draft"], encoding="utf-8")
        result["out"] = str(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
