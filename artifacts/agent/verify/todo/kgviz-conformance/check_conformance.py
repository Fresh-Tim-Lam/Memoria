"""KG 可视化 v0 设计文档 vs 实现：逐条条款核对矩阵（可复跑）。

用途：为"文档每一条都有对应实现或明确标注需人参与"提供机器可复核的证据。
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
JS = os.path.join(ROOT, "src", "memoria", "ui", "static", "app", "js")
CSS = os.path.join(ROOT, "src", "memoria", "ui", "static", "app", "css", "app.css")
STORAGE = os.path.join(ROOT, "src", "memoria", "storage")
TESTS = os.path.join(ROOT, "tests")
DOC = os.path.join(ROOT, "docs", "design", "kg-visualization-v0.md")


def read(p):
    try:
        return io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def js(name):
    return read(os.path.join(JS, name))


def has(pattern, *texts):
    rx = re.compile(pattern)
    return any(rx.search(t) for t in texts if t)


def count(rx, text):
    return len(re.findall(rx, text))


engine = js("graph-engine.js")
v2 = js("graph-view-2d.js")
v3 = js("graph-view-3d.js")
label = js("graph-label.js")
lay2 = js("graph-layout-2d.js")
lay3 = js("graph-layout-3d.js")
tele = read(os.path.join(STORAGE, "graph_telemetry.py"))
css = read(CSS)

rows = []


def row(clause, verdict, evidence):
    rows.append({"clause": clause, "verdict": verdict, "evidence": evidence})


# §1 节点大小连续变化
sz = has(r"MemoriaGraphSizing", engine) and has(r"radiusForNode", engine)
row("§1 连续尺寸映射（radiusForNode / MemoriaGraphSizing）",
    "IMPLEMENTED" if sz else "MISSING",
    "graph-engine.js: MemoriaGraphSizing=%s radiusForNode=%s; 范围 4.50/9.90=%s/%s"
    % (has(r"MemoriaGraphSizing", engine), has(r"radiusForNode", engine),
       has(r"4\.50|4\.5\b", engine), has(r"9\.90|9\.9\b", engine)))
row("§1 t(d)=distinct-degree 归一化 rank",
    "IMPLEMENTED" if has(r"normalizedRankT", engine) else "MISSING",
    "graph-engine.js normalizedRankT=%s（旧名 percentileRankT 残留=%d）"
    % (has(r"normalizedRankT", engine), count(r"percentileRankT", engine)))
_lbl_and_app = label + read(os.path.join(ROOT, "src/memoria/ui/static/app/js/app.js"))
_deg_ui = has(r"-graph-hint-degree", _lbl_and_app) or has(r"hint-degree", _lbl_and_app)
row("§1.5 tooltip 显示 degree 绝对原值",
    "IMPLEMENTED" if _deg_ui and has(r"degreeText", label) else "MISSING",
    "-graph-hint-degree 类名出现=%s；graph-label.js degreeText=%s；css 定义=%s"
    % (_deg_ui, has(r"degreeText", label), has(r"-graph-hint-degree", css)))

# §2 3D 等大 + 光晕等大
row("§2 3D 节点等大（mesh scale=1）",
    "IMPLEMENTED" if count(r"const scale = 1;", v3) >= 2 else "MISSING",
    "graph-view-3d.js 'const scale = 1;' 出现 %d 次（期望 ≥2：初始重建 + halo re-sync）"
    % count(r"const scale = 1;", v3))
row("§2/D-KGV-16 3D 光晕不随 degree",
    "IMPLEMENTED" if has(r"D-KGV-16", v3) and not has(r"scale = 1 \+ ratio", v3) else "MISSING",
    "graph-view-3d.js 有 D-KGV-16 注释=%s；残留 '1 + ratio' 公式=%s"
    % (has(r"D-KGV-16", v3), has(r"scale = 1 \+ ratio", v3)))

# §3 标签 LOD
row("§3 标签 LOD/避让（layoutNodeLabels）",
    "IMPLEMENTED" if has(r"layoutNodeLabels", label) else "MISSING",
    "graph-label.js layoutNodeLabels=%s；labelLod 开关=%s"
    % (has(r"layoutNodeLabels", label), has(r"labelLod", v2)))

# §4 布局确定性种子
seed = has(r"MemoriaGraphSeed|createSeededRandom", engine)
no_rnd = count(r"Math\.random\s*\(", lay2) == 0 and count(r"Math\.random\s*\(", lay3) == 0
row("§4 确定性种子（2D 与 3D）",
    "IMPLEMENTED" if seed and no_rnd else "MISSING",
    "graph-engine.js MemoriaGraphSeed=%s；layout 内 Math.random() 调用 2d=%d 3d=%d（期望 0）"
    % (seed, count(r"Math\.random\s*\(", lay2), count(r"Math\.random\s*\(", lay3)))

# §5 埋点
row("§5 埋点 E1/E2",
    "IMPLEMENTED" if tele and has(r"nodeRadius_change", tele) and has(r"graphStyle_change", tele) else "MISSING",
    "graph_telemetry.py 存在=%s；nodeRadius_change=%s graphStyle_change=%s 禁采 node_radius_px=%s"
    % (bool(tele), has(r"nodeRadius_change", tele), has(r"graphStyle_change", tele),
       not has(r"node_radius_px", tele)))

# §6 毛球态判定
hair = has(r"hairball|毛球|largestGroup|maxGroupRatio|Hairball", v2 + v3 + js("graph-groups.js") + engine)
row("§6 毛球态判定（D-KGV-09）",
    "IMPLEMENTED" if hair else "MISSING",
    "graph-*.js 中 hairball/毛球/最大分组占比 判定逻辑=%s" % hair)

# §7 语料身份三元组
row("§7 语料身份三元组（manifest_sha256 + head + measured_at）",
    "IMPLEMENTED" if has(r"manifest_sha256", tele) else "MISSING",
    "graph_telemetry.py manifest_sha256=%s head=%s measured_at=%s"
    % (has(r"manifest_sha256", tele), has(r"\"head\"", tele), has(r"measured_at", tele)))

# §8 机检
t_size = has(r"T-size|t_size", read(os.path.join(TESTS, "test_kgviz_size_continuous.py")))
t_double = any(has(r"t_double|T-double", read(os.path.join(TESTS, f)))
               for f in os.listdir(TESTS) if f.endswith(".py"))
row("§8 T-size-2/3/4 机检",
    "IMPLEMENTED" if t_size else "MISSING",
    "tests/test_kgviz_size_continuous.py T-size 命中=%s" % t_size)
row("§8 T-double 机检（D-KGV-15）",
    "IMPLEMENTED" if t_double else "MISSING",
    "全 tests/ 中 t_double/T-double 命中=%s" % t_double)
row("§8 T-size-1 / T-label / T-depth（真人判读）",
    "HUMAN_GATED",
    "设计文档 U-KGV-5 已登记需人参与；无自动化实现属预期")

# 汇总
impl = [r for r in rows if r["verdict"] == "IMPLEMENTED"]
miss = [r for r in rows if r["verdict"] == "MISSING"]
human = [r for r in rows if r["verdict"] == "HUMAN_GATED"]

out = {
    "schema": "kgviz-design-conformance/v1",
    "doc": "docs/design/kg-visualization-v0.md",
    "head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip(),
    "summary": {"total": len(rows), "implemented": len(impl),
                "missing": len(miss), "human_gated": len(human)},
    "rows": rows,
}
dst = os.path.join(ROOT, "artifacts", "agent", "verify", "todo", "kgviz-conformance")
os.makedirs(dst, exist_ok=True)
io.open(os.path.join(dst, "conformance.json"), "w", encoding="utf-8", newline="").write(
    json.dumps(out, ensure_ascii=False, indent=2))

print("=" * 72)
print("KG 可视化 v0 设计文档 → 实现 逐条核对（HEAD %s）" % out["head"])
print("=" * 72)
for r in rows:
    mark = {"IMPLEMENTED": "[OK  ]", "MISSING": "[MISS]", "HUMAN_GATED": "[HUMAN]"}[r["verdict"]]
    print("%s %s" % (mark, r["clause"]))
    print("         %s" % r["evidence"])
print()
print("汇总：共 %d 条 = 已实现 %d / 未实现 %d / 需人参与 %d"
      % (len(rows), len(impl), len(miss), len(human)))
if miss:
    print("未实现条款：")
    for r in miss:
        print("  - %s" % r["clause"])
sys.exit(0 if not miss else 1)
