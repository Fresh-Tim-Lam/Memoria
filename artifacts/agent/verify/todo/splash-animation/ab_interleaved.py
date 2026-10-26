"""task-186 T-splash-2 公平 A/B：**交错**测"有蒙层/无蒙层"冷启动耗时（抵消环境漂移）。

为什么需要交错：顺序测（先全是 before、再全是 after）会被系统状态漂移污染 ——
实测同一天两次 before 相差 1897 vs 2081ms（+184ms，与本功能无关）。交错 A/B 把
"时间漂移"变成两臂共同承受的噪声。

每次 trial：
  · 用 python 切换 index.html 里的 splash.js <script>（on/off），跑 run_boot_measure.ps1 -Trials 1
  · 口径与之前完全一致：进程启动 t0 → html.-booting 消失（既有"跑马灯"结束）
  · 结束恢复 index.html 为 on（并断言恢复成功）
输出：ab-interleaved.json（逐 trial + 两臂中位数/极小值/极大值/差值）
"""
import io
import json
import os
import statistics
import subprocess
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
HERE = os.path.join(ROOT, r"artifacts\agent\verify\todo\splash-animation")
INDEX = os.path.join(ROOT, r"src\memoria\ui\static\app\index.html")
PS = os.path.join(HERE, "run_boot_measure.ps1")
NODE = r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
SCRIPT_LINE = '  <script src="/app/js/splash.js"></script>\n'
OFF_LINE = '  <!-- task-186 A/B：本轮关闭 splash.js -->\n'
ROUNDS = int(os.environ.get("AB_ROUNDS", "5"))


def set_mode(mode):
    t = io.open(INDEX, encoding="utf-8").read()
    if mode == "on":
        if SCRIPT_LINE in t:
            return
        assert t.count(OFF_LINE) == 1
        t = t.replace(OFF_LINE, SCRIPT_LINE)
    else:
        if OFF_LINE in t:
            return
        assert t.count(SCRIPT_LINE) == 1
        t = t.replace(SCRIPT_LINE, OFF_LINE)
    io.open(INDEX, "w", encoding="utf-8", newline="\n").write(t)


def run_trial(label, port):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS,
           "-Label", label, "-Trials", "1", "-NodeExe", NODE, "-BasePort", str(port)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    summary = os.path.join(HERE, "measures-%s" % label, "summary.json")
    if not os.path.isfile(summary):
        print("  !! trial failed:", label, proc.stdout[-500:], proc.stderr[-500:])
        return None
    d = json.load(io.open(summary, encoding="utf-8-sig"))
    return d


def main():
    trials = []
    port = int(os.environ.get("AB_PORT", "9750"))
    for i in range(1, ROUNDS + 1):
        # 交错：奇数轮 on→off，偶数轮 off→on（抵消顺序效应）
        order = ["on", "off"] if i % 2 == 1 else ["off", "on"]
        for variant in order:
            set_mode(variant)
            label = "ab-%s-%d" % (variant, i)
            d = run_trial(label, port)
            port += 1
            if not d:
                continue
            trials.append({"round": i, "variant": variant, "label": label,
                           "median_ms": d.get("median_ms"), "all_ms": d.get("all_ms")})
            print("  round %d %-3s -> %s ms" % (i, variant, d.get("median_ms")))
    set_mode("on")
    t = io.open(INDEX, encoding="utf-8").read()
    assert SCRIPT_LINE in t and OFF_LINE not in t, "index.html 未恢复到 on 状态！"

    def stats(variant):
        vals = [x["median_ms"] for x in trials if x["variant"] == variant and x["median_ms"]]
        if not vals:
            return None
        return {"n": len(vals), "median": round(statistics.median(vals), 1),
                "min": min(vals), "max": max(vals), "all": vals}

    on, off = stats("on"), stats("off")
    result = {"rounds": ROUNDS, "method": "interleaved A/B (same window; alternates order each round)",
              "metric": "process start t0 -> html.-booting removed (existing marquee end)",
              "on": on, "off": off,
              "delta_ms": (on["median"] - off["median"]) if on and off else None,
              "trials": trials}
    out = os.path.join(HERE, "ab-interleaved.json")
    io.open(out, "w", encoding="utf-8", newline="\n").write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("written", out)
    return 0 if (on and off) else 1


if __name__ == "__main__":
    sys.exit(main())