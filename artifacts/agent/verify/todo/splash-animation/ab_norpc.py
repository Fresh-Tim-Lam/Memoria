"""归因 3：蒙层保留，但启动期不读 ui_settings / 不装设置面板（交错 A/B）。"""
import io, json, os, shutil, statistics, subprocess, sys
ROOT = r"D:\AAA_Jupyter\Memoria"
HERE = os.path.join(ROOT, r"artifacts\agent\verify\todo\splash-animation")
SPLASH = os.path.join(ROOT, r"src\memoria\ui\static\app\js\splash.js")
BAK = SPLASH + ".ab3.bak"
PS = os.path.join(HERE, "run_boot_measure.ps1")
NODE = r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
ROUNDS = int(os.environ.get("AB_ROUNDS", "5"))
A1 = "      readPrefsFromDisk().then(function (prefs) {"
A2 = "  loadPrefsFast();\n  start();\n  ensureSettings();"

def set_mode(mode):
    if not os.path.isfile(BAK): shutil.copyfile(SPLASH, BAK)
    t = io.open(BAK, encoding="utf-8").read()
    if mode == "full":
        io.open(SPLASH, "w", encoding="utf-8", newline="\n").write(t)
    else:
        # 用 setInterval 包一层永不执行的假分支：等价于跳过 RPC + 设置面板安装
        assert t.count(A1) == 1 and t.count(A2) == 1
        t = t.replace(A1, "      if (false) readPrefsFromDisk().then(function (prefs) {")
        t = t.replace(A2, "  loadPrefsFast();\n  start();\n  // ensureSettings();  // A/B：启动期不装设置面板（临时）")
        io.open(SPLASH, "w", encoding="utf-8", newline="\n").write(t)

def run(label, port):
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",PS,
                    "-Label",label,"-Trials","1","-NodeExe",NODE,"-BasePort",str(port)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    p = os.path.join(HERE, "measures-%s" % label, "summary.json")
    return json.load(io.open(p, encoding="utf-8-sig")) if os.path.isfile(p) else None

def inpage(label):
    p = os.path.join(HERE, "measures-%s" % label, "trial-1.json")
    if not os.path.isfile(p): return None
    d = json.load(io.open(p, encoding="utf-8"))
    if not d.get("valid"): return None
    to = (d.get("perf") or {}).get("timeOrigin")
    return (d["removed_at"] - to) if to and d.get("removed_at") else None

trials=[]; port=int(os.environ.get("AB_PORT","9860"))
for i in range(1, ROUNDS+1):
    order = ["full","norpc"] if i%2==1 else ["norpc","full"]
    for v in order:
        set_mode(v); label="attr3-%s-%d"%(v,i); run(label, port); port+=1
        rows=[]
        for k in ("trial-1",):
            pass
        # 用 summary 的 median（wall）+ 单 trial 的 in-page
        ms = None
        p = os.path.join(HERE,"measures-%s"%label,"summary.json")
        if os.path.isfile(p):
            d=json.load(io.open(p,encoding="utf-8-sig")); ms=d.get("median_ms")
        ip = inpage(label)
        trials.append({"v":v,"wall":ms,"inpage":ip})
        print("  round %d %-6s wall=%s inpage=%s" % (i,v,ms,ip))
set_mode("full"); os.remove(BAK)
def st(key):
    xs=[x[key] for x in trials if x["v"]==key and x.get(key) is not None]
    return {"n":len(xs),"median":round(statistics.median(xs),1),"all":xs} if xs else None
out={"full":{"inpage":st("inpage"),"wall":st("wall")},"norpc":{"inpage":st("inpage"),"wall":st("wall")},"trials":trials}
io.open(os.path.join(HERE,"ab-norpc.json"),"w",encoding="utf-8",newline="\n").write(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print("in-page full:", out["full"]["inpage"], "norpc:", out["norpc"]["inpage"])