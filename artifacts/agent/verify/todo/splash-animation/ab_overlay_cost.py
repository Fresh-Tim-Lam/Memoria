"""task-186 T-splash-2 归因：交错 A/B 比较「完整蒙层」vs「只加载模块不建蒙层」（都带 script 标签）。

用途：定位 +134ms 的代价来自哪一层。若 nofx≈off(2112)，代价在蒙层；若 nofx≈full(2246)，
代价在"多一个同步脚本"本身（那就要换加载方式）。
"""
import io
import json
import os
import shutil
import statistics
import subprocess
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
HERE = os.path.join(ROOT, r"artifacts\agent\verify\todo\splash-animation")
SPLASH = os.path.join(ROOT, r"src\memoria\ui\static\app\js\splash.js")
BAK = SPLASH + ".ab.bak"
PS = os.path.join(HERE, "run_boot_measure.ps1")
NODE = r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
ROUNDS = int(os.environ.get("AB_ROUNDS", "5"))
ANCHOR = "  function start() {\n    try {\n"
OFF_LINE = "      return false;   // A/B：只加载模块，不建蒙层（临时）\n"


def set_mode(mode):
    if not os.path.isfile(BAK):
        shutil.copyfile(SPLASH, BAK)
    t = io.open(BAK, encoding="utf-8").read()
    if mode == "full":
        io.open(SPLASH, "w", encoding="utf-8", newline="\n").write(t)
    else:
        assert t.count(ANCHOR) == 1
        io.open(SPLASH, "w", encoding="utf-8", newline="\n").write(t.replace(ANCHOR, ANCHOR + OFF_LINE))


def run_trial(label, port):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS,
           "-Label", label, "-Trials", "1", "-NodeExe", NODE, "-BasePort", str(port)]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    summary = os.path.join(HERE, "measures-%s" % label, "summary.json")
    if not os.path.isfile(summary):
        return None
    return json.load(io.open(summary, encoding="utf-8-sig"))


def main():
    trials = []
    port = int(os.environ.get("AB_PORT", "9790"))
    for i in range(1, ROUNDS + 1):
        order = ["full", "nofx"] if i % 2 == 1 else ["nofx", "full"]
        for variant in order:
            set_mode(variant)
            d = run_trial("attr-%s-%d" % (variant, i), port)
            port += 1
            if not d:
                continue
            trials.append({"round": i, "variant": variant, "median_ms": d.get("median_ms")})
            print("  round %d %-4s -> %s ms" % (i, variant, d.get("median_ms")))
    set_mode("full")
    os.remove(BAK)

    def stats(v):
        vals = [x["median_ms"] for x in trials if x["variant"] == v and x["median_ms"]]
        return {"n": len(vals), "median": round(statistics.median(vals), 1), "all": vals} if vals else None

    out = {"rounds": ROUNDS, "full": stats("full"), "nofx": stats("nofx"),
           "delta_overlay_ms": (stats("full")["median"] - stats("nofx")["median"]) if stats("full") and stats("nofx") else None,
           "trials": trials}
    p = os.path.join(HERE, "ab-overlay-cost.json")
    io.open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())