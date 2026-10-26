"""归因 2：蒙层 DOM 建好但 display:none（不参与绘制/合成）vs 完整蒙层（交错 A/B）。"""
import io, json, os, shutil, statistics, subprocess, sys
ROOT = r"D:\AAA_Jupyter\Memoria"
HERE = os.path.join(ROOT, r"artifacts\agent\verify\todo\splash-animation")
SPLASH = os.path.join(ROOT, r"src\memoria\ui\static\app\js\splash.js")
BAK = SPLASH + ".ab2.bak"
PS = os.path.join(HERE, "run_boot_measure.ps1")
NODE = r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
ROUNDS = int(os.environ.get("AB_ROUNDS", "5"))
ANCHOR = "    DOC.body.appendChild(root);\n    return { root: root, canvas: canvas, hint: hint };"
HIDDEN = "    root.style.display = \"none\";  // A/B：不参与绘制/合成（临时）\n"

def set_mode(mode):
    if not os.path.isfile(BAK): shutil.copyfile(SPLASH, BAK)
    t = io.open(BAK, encoding="utf-8").read()
    if mode == "full":
        io.open(SPLASH, "w", encoding="utf-8", newline="\n").write(t)
    else:
        assert t.count(ANCHOR) == 1, "anchor"
        io.open(SPLASH, "w", encoding="utf-8", newline="\n").write(t.replace(ANCHOR, HIDDEN + ANCHOR))

def run(label, port):
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",PS,
                    "-Label",label,"-Trials","1","-NodeExe",NODE,"-BasePort",str(port)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    p = os.path.join(HERE, "measures-%s" % label, "summary.json")
    return json.load(io.open(p, encoding="utf-8-sig")) if os.path.isfile(p) else None

trials=[]; port=int(os.environ.get("AB_PORT","9830"))
for i in range(1, ROUNDS+1):
    order = ["full","hidden"] if i%2==1 else ["hidden","full"]
    for v in order:
        set_mode(v); d = run("attr2-%s-%d"%(v,i), port); port+=1
        if d: trials.append({"v":v,"ms":d.get("median_ms")}); print("  round %d %-6s -> %s" % (i,v,d.get("median_ms")))
set_mode("full"); os.remove(BAK)
def st(v):
    xs=[x["ms"] for x in trials if x["v"]==v and x["ms"]]
    return {"n":len(xs),"median":round(statistics.median(xs),1),"all":xs} if xs else None
out={"full":st("full"),"hidden":st("hidden"),"delta_paint_ms":(st("full")["median"]-st("hidden")["median"]) if st("full") and st("hidden") else None,"trials":trials}
io.open(os.path.join(HERE,"ab-paint-cost.json"),"w",encoding="utf-8",newline="\n").write(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(out,ensure_ascii=False,indent=2))