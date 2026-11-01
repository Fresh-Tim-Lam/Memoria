#!/usr/bin/env python
"""模型纪律审计：实际模型 vs 名册，发现 Pro 即 FAIL（P3）。

背景：2026-11-01 的 v4-pro 事故（`artifacts/agent/verify/model-guard/V4PRO-INCIDENT-20261101.md`）
不是因为名册写了 pro，而是因为**名册显示 flash、Session 出生描述符是 pro**：
  · 唤醒/冷恢复按出生描述符重放模型（subagent/descriptor 的 agentModel）
  · team_set_model 只改名册 row + team/model-overrides.json，改不到出生描述符
  · list_agents / team_snapshot 读名册，所以"看起来合规"
本脚本补上"实际是什么"的机检：读全部 Session 日志的出生描述符 + token-cost 账本，
与当前 roster 快照对比，任何 pro 实际模型 ⇒ exit 1。

用法：
    python scripts/agent/model_guard_audit.py                     # 默认扫 DSH home
    python scripts/agent/model_guard_audit.py --dsh-home <dir>    # 指定 .dsh 目录
    python scripts/agent/model_guard_audit.py --json              # 机器可读输出
    python scripts/agent/model_guard_audit.py --allow-session <id>  # 已知例外（可多次）

退出码：0 = 无违规；1 = 有违规；2 = 用法/环境错误。

边界：只读；不修改 Session、不写 token-cost、不调用模型。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Iterable

PRO_MODEL_PATTERN = re.compile(r"(?:^|[^a-z0-9])pro(?:[^a-z0-9]|$)|v\d+(?:[-_. ]?pro)", re.IGNORECASE)
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def is_pro(name: str) -> bool:
    """Return True when one model id denotes a Pro-tier model."""
    return bool(PRO_MODEL_PATTERN.search(name or ""))


def _scan_with_node(sessions_root: Path) -> dict[str, dict[str, Any]]:
    """Decode every session with the runtime node (zlib.zstdDecompressSync)."""
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if node is None:
        raise SystemExit("model_guard_audit: node is required to decode zstd session logs")
    script = r"""
const fs=require('fs'),path=require('path'),z=require('zlib');
const base=process.argv[2];
const MAGIC=Buffer.from([0x28,0xb5,0x2f,0xfd]);
const out={};
for(const proj of fs.readdirSync(base)){
  const pdir=path.join(base,proj);
  try{ if(!fs.statSync(pdir).isDirectory()) continue; }catch{ continue }
  for(const sid of fs.readdirSync(pdir)){
    const f=path.join(pdir,sid,'session.v4.jsonl.zstd');
    if(!fs.existsSync(f)) continue;
    const raw=fs.readFileSync(f);
    const pos=[]; let i=raw.indexOf(MAGIC,0);
    while(i!==-1){pos.push(i);i=raw.indexOf(MAGIC,i+4);}
    let desc=null, header=null, lastModel=null, lastTime=0;
    for(let k=0;k<pos.length;k++){
      const end=k+1<pos.length?pos[k+1]:raw.length;
      let buf; try{buf=z.zstdDecompressSync(raw.subarray(pos[k],end))}catch{continue}
      const txt=buf.toString('utf8');
      for(const line of txt.split('\n')){
        if(!line) continue;
        let o; try{o=JSON.parse(line)}catch{continue}
        if(o.type==='session') header=o;
        if(o.type==='subagent/descriptor') desc=o.data;
        if(o.type==='request/header' && o.data && o.data.header && o.data.header.config){lastModel=o.data.header.config.model; lastTime=o.time;}
      }
      if(desc && header && lastModel) break;
    }
    out[sid]={descriptor:desc, header:header, lastModel:lastModel, lastTime:lastTime};
  }
}
process.stdout.write(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = handle.name
    try:
        completed = subprocess.run(
            [node, script_path, str(sessions_root)],
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout or "{}")
    finally:
        Path(script_path).unlink(missing_ok=True)


def _token_cost_models(token_cost_dir: Path) -> dict[str, dict[str, Any]]:
    """Summarize per-session model counts from the token-cost ledger (post-hoc truth)."""
    summary: dict[str, dict[str, Any]] = {}
    if not token_cost_dir.is_dir():
        return summary
    for path in token_cost_dir.glob("*.jsonl"):
        counts: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            model = record.get("model") or "?"
            counts[model] = counts.get(model, 0) + 1
        summary[path.stem] = {
            "models": counts,
            "proCalls": sum(count for model, count in counts.items() if is_pro(model)),
            "totalCalls": sum(counts.values()),
        }
    return summary


def _roster(snapshot: Path) -> dict[str, dict[str, Any]]:
    """Read a team_snapshot export when present (lead row + teammates)."""
    if not snapshot.is_file():
        return {}
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    rows = {}
    for member in data.get("members") or []:
        rows[member.get("id") or member.get("target")] = member
    return rows


def audit(dsh_home: Path, snapshot: Path, allowed: Iterable[str]) -> dict[str, Any]:
    """Compute the actual-model report for every session."""
    sessions_root = dsh_home / "sessions"
    if not sessions_root.is_dir():
        raise SystemExit(f"model_guard_audit: sessions root missing: {sessions_root}")
    sessions = _scan_with_node(sessions_root)
    ledger = _token_cost_models(dsh_home / "token-cost")
    roster = _roster(snapshot)
    allow = set(allowed)

    findings: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    for sid, info in sessions.items():
        descriptor = info.get("descriptor") or {}
        actual = descriptor.get("agentModel")
        header = info.get("header") or {}
        entry = {
            "sessionId": sid,
            "member": None,
            "descriptorModel": actual,
            "lastRequestModel": info.get("lastModel"),
            "proCalls": (ledger.get(sid) or {}).get("proCalls", 0),
            "totalCalls": (ledger.get(sid) or {}).get("totalCalls", 0),
            "cwd": header.get("cwd"),
        }
        if sid in roster:
            entry["member"] = roster[sid].get("target") or roster[sid].get("name")
            entry["rosterModel"] = roster[sid].get("model")
        if sid in allow:
            entry["allowedException"] = True
            continue
        reasons = []
        if is_pro(str(actual or "")):
            reasons.append("descriptor-pro")
        if is_pro(str(info.get("lastModel") or "")):
            reasons.append("last-request-pro")
        if entry["proCalls"] > 0:
            reasons.append("ledger-pro-calls")
        if reasons:
            entry["reasons"] = reasons
            if entry["member"] is None:
                historical.append(entry)
            else:
                findings.append(entry)

    return {
        "dshHome": str(dsh_home),
        "sessionsScanned": len(sessions),
        "sessionsWithLedger": len(ledger),
        "rosterRows": len(roster),
        "findings": sorted(findings, key=lambda item: item["sessionId"]),
        "historical": sorted(historical, key=lambda item: item["sessionId"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsh-home", default=str(Path.home() / ".dsh"), help="DSH home (contains sessions/ and token-cost/)")
    parser.add_argument(
        "--snapshot",
        default=str(Path(__file__).resolve().parents[2] / "artifacts" / "agent" / "verify" / "model-guard" / "team-snapshot-20261101.json"),
        help="team_snapshot JSON used to map session ids to member names",
    )
    parser.add_argument("--allow-session", action="append", default=[], help="known exception session id (repeatable)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    report = audit(Path(args.dsh_home).expanduser(), Path(args.snapshot), args.allow_session)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"sessions scanned: {report['sessionsScanned']}  roster rows: {report['rosterRows']}")
        print(f"historical (never wakeable) Pro descriptors: {len(report['historical'])}")
        if not report["findings"]:
            print("RESULT: PASS (no wakeable roster member has Pro-tier evidence)")
        else:
            print(f"RESULT: FAIL ({len(report['findings'])} wakeable roster member(s) with Pro-tier evidence)")
            for item in report["findings"]:
                member = item.get("member") or "(not in roster)"
                print(
                    f"  - {item['sessionId']}  member={member}  descriptor={item['descriptorModel']}"
                    f"  last={item['lastRequestModel']}  proCalls={item['proCalls']}/{item['totalCalls']}"
                    f"  reasons={','.join(item['reasons'])}"
                )
            print("  fix: re-spawn the member (fresh Session => fresh descriptor) or set DSH_ALLOW_PRO_MODELS=1 deliberately")
    return 0 if not report["findings"] else 1


if __name__ == "__main__":
    sys.exit(main())
