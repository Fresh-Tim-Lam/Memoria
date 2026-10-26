#!/usr/bin/env python3
"""校验 SF-035 的 rule_ref 是否能被 team_audit._validate_rule_ref 解析（防止 r6 假红）。"""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("team_audit", "scripts/agent/team_audit.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["team_audit"] = mod
spec.loader.exec_module(mod)
repo = Path(".").resolve()
rows = [json.loads(line) for line in Path("team/steward/findings.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
for row in rows:
    if row["finding_id"] == "SF-20261026-035":
        print("rule_ref:", row["rule_ref"])
        print("resolves:", mod._validate_rule_ref(repo, row["rule_ref"]))
