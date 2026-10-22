# -*- coding: utf-8 -*-
"""task-79 äº¤é”™ A/B campaignã€‚

é¡ºåºç»è¿‡è®¾è®¡ï¼ˆA/B/B/A + å°¾éƒ¨å›žè¡¥ï¼‰ï¼Œä»¥ä¾¿æŠŠæœºå™¨æ¼‚ç§»å¹³å‡æŽ‰ï¼š
  V4-r1, Voff-r1, Voff-r2, V4-r2, V3-r1, V6-r1, Vpre-r1, V3-r2, V6-r2, V4-r3, Voff-r3
æ¯æ¬¡ run ç‹¬ç«‹å¯åŠ¨ appï¼ˆå¹²å‡€é¡µé¢ï¼‰ï¼Œrunner è‡ªå·±å–é—¨ç¦ä¸²è¡Œé”ã€‚

ç”¨æ³•ï¼š
  python scripts/benchmark/surface/_t79_campaign.py
  python scripts/benchmark/surface/_t79_campaign.py --only v4-r1,voff-r1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS = HERE / "results"
RUN = HERE / "_t79_run.py"
LOG = RESULTS / "t79-campaign.log"

SEQ = [
    ("V4", "head", None, "v4-r1"),
    ("Voff", "head", 1000000, "voff-r1"),
    ("Voff", "head", 1000000, "voff-r2"),
    ("V4", "head", None, "v4-r2"),
    ("V3", "head", 3, "v3-r1"),
    ("V6", "head", 6, "v6-r1"),
    ("Vpre", "git:9c940796", None, "vpre-r1"),
    ("V3", "head", 3, "v3-r2"),
    ("V6", "head", 6, "v6-r2"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="åªè·‘æŒ‡å®š labelï¼ˆé€—å·åˆ†éš”ï¼‰")
    ap.add_argument("--work-root", default="")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    RESULTS.mkdir(parents=True, exist_ok=True)

    seq = [s for s in SEQ if (not only or s[3] in only)]
    logf = open(LOG, "a", encoding="utf-8")
    ok, fail = [], []
    for variant, src, threshold, label in seq:
        cmd = [sys.executable, str(RUN), "--variant", variant, "--label", label,
               "--appjs-from", src, "--label", label]
        if threshold is not None:
            cmd += ["--threshold", str(threshold)]
        if args.work_root:
            cmd += ["--work-root", args.work_root]
        # åŽ»æŽ‰é‡å¤ --label
        seen, cmd2 = set(), []
        i = 0
        while i < len(cmd):
            if cmd[i] == "--label":
                if "label" in seen:
                    i += 2
                    continue
                seen.add("label")
            cmd2.append(cmd[i]); i += 1
        t0 = time.time()
        line = f"\n===== {time.strftime('%H:%M:%S')} {label} ({variant}, thr={threshold}) =====\n"
        print(line, end="")
        logf.write(line); logf.flush()
        cp = subprocess.run(cmd2, cwd=str(REPO_ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=2400)
        out = (cp.stdout or "") + (("\n[stderr]\n" + cp.stderr) if cp.stderr else "")
        logf.write(out); logf.flush()
        tail = "\n".join(out.strip().splitlines()[-12:])
        print(tail)
        run_json = RESULTS / f"t79-{label}.json"
        dt = time.time() - t0
        if cp.returncode == 0 and run_json.is_file():
            try:
                d = json.loads(run_json.read_text("utf-8"))
                w2 = d.get("w2", [])
                w1d = [x.get("frames", {}) for x in (d.get("w1") or {}).get("down", [])]
                summary = (f"OK {dt:.0f}s blocks={(d.get('open') or {}).get('stats', {}).get('totalBlocks')} "
                           f"W1down max med={sorted([x.get('max') for x in w1d if x.get('max') is not None])[len(w1d)//2] if w1d else None} "
                           f"W2 maxMat={[(x.get('drag') or {}).get('maxMat') for x in w2]} "
                           f"W2 back={[x.get('events', {}).get('back') for x in w2]}")
                ok.append(label)
                print("[campaign] " + summary)
                logf.write("[campaign] " + summary + "\n"); logf.flush()
            except Exception as e:
                fail.append((label, f"json parse: {e}"))
        else:
            fail.append((label, f"exit={cp.returncode}"))
        time.sleep(1.0)
    logf.write(f"\n[campaign done] ok={ok} fail={fail}\n")
    logf.close()
    print(f"\n[campaign done] ok={ok} fail={fail}")
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())

