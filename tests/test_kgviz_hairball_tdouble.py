"""KGViz 收尾补齐机检：毛球态判定（D-KGV-09）+ T-double（D-KGV-15）。

设计冻结：
  · docs/design/kg-visualization-v0.md §6 —— 单条件（最大连通分量占比）+ 实测校准；
  · §8 T-double —— 同变量同方向 = 冗余强化（PASS）；不同变量或方向相反 = 冲突。

★ 先证红（双向）：
  · 旧三条件组合（labels>60 OR edges/nodes<4 OR avgdeg<8）在"良好语料"上也会命中 ⇒ 无判别力；
  · 新单条件：已知毛球态语料必须命中、已知良好语料必须不命中（不能永远命中/永远不命中）；
  · T-double 红 fixture：让颜色编码字母序（不同变量）/ 方向相反 ⇒ 必须报冲突。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
GROUPS = APP / "js" / "graph-groups.js"
ENGINE = APP / "js" / "graph-engine.js"
VIEW2D = APP / "js" / "graph-view-2d.js"
VIEW3D = APP / "js" / "graph-view-3d.js"


def _node_json(script: str) -> dict:
    p = subprocess.run(["node", "-"], input=script, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT))
    if p.returncode != 0:
        raise AssertionError(f"node failed: {p.stderr[-3000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def _harness(extra: str, files: tuple[Path, ...]) -> dict:
    loads = "\n".join(
        f'vm.runInContext(fs.readFileSync({json.dumps(str(f).replace(chr(92), "/"))}, "utf8"), sandbox);'
        for f in files
    )
    script = f"""
const fs = require("fs"), vm = require("vm");
const sandbox = {{}};
vm.createContext(sandbox);
{loads}
{extra}
"""
    return _node_json(script)


# ── 语料 fixture（纯前端合成图；真实语料数值来自报告 §2 的实测）──────────────

HAIRBALL_JS = r"""
function ringLinks(nodes, start = 0) {
  const links = [];
  for (let i = 0; i < nodes; i++) {
    links.push({ source: "n" + (start + i), target: "n" + (start + ((i + 1) % nodes)) });
  }
  return links;
}
function clusters(sizes) {
  const nodes = [];
  const links = [];
  let base = 0;
  for (const size of sizes) {
    for (let i = 0; i < size; i++) nodes.push({ id: "n" + (base + i) });
    links.push(...ringLinks(size, base));
    base += size;
  }
  return { nodes, links };
}
const G = sandbox.MemoriaGraphGroups;
const H = sandbox.MemoriaGraphHairball;

// 1) 已知毛球态：60 节点单一环 + 弦（单连通分量 100%）
const hb = (() => { const nodes = Array.from({length: 60}, (_, i) => ({id: "n" + i})); const links = ringLinks(60);
  links.push({source: "n0", target: "n30"}); links.push({source: "n5", target: "n40"});
  return { nodes, links, groups: G.computeGraphGroups(nodes, links) }; })();
const hbReport = H.computeHairball(hb.nodes, hb.links, hb.groups);

// 2) 已知良好语料：120 节点 / 12 个 10 节点小群（每群内部成环，群间无边）
const good = clusters(Array.from({length: 12}, () => 10));
const goodGroups = G.computeGraphGroups(good.nodes, good.links);
const goodReport = H.computeHairball(good.nodes, good.links, goodGroups);

// 旧三条件组合（设计 §6 记录的原组合）——用于证明它没有判别力
function legacyHairball(metrics) {
  return (metrics.labels > 60) || (metrics.edgesPerNode < 4) || (metrics.avgDegree < 8);
}
const goodLegacy = legacyHairball(goodReport.metrics);
const hbLegacy = legacyHairball(hbReport.metrics);

// 3) 真实语料实测值（报告 §2）：134/404 最大分量 120/134=0.8955；HEAD archive 61/154 最大 50/61=0.8197
const realLive = H.computeHairball(
  Array.from({length: 134}, (_, i) => ({id: "r" + i})),
  [],
  { groups: [{ size: 120 }, ...Array.from({length: 14}, () => ({ size: 1 }))] }
);
const realHead = H.computeHairball(
  Array.from({length: 61}, (_, i) => ({id: "h" + i})),
  [],
  { groups: [{ size: 50 }, ...Array.from({length: 10}, () => ({ size: 1 }))] }
);
// 4) 真实稀疏 KB：329 节点 / 36 边 / 最大分量 9（2.74%）
const realSparse = H.computeHairball(
  Array.from({length: 329}, (_, i) => ({id: "s" + i})),
  [],
  { groups: [{ size: 9 }, ...Array.from({length: 292}, () => ({ size: 1 }))] }
);

console.log(JSON.stringify({
  threshold: H.THRESHOLD,
  hairball: { is: hbReport.isHairball, maxShare: hbReport.metrics.maxGroupShare, metrics: hbReport.metrics, rule: hbReport.rule },
  good: { is: goodReport.isHairball, maxShare: goodReport.metrics.maxGroupShare, metrics: goodReport.metrics },
  legacy: { onGood: goodLegacy, onHairball: hbLegacy },
  realLive: { is: realLive.isHairball, maxShare: realLive.metrics.maxGroupShare, threshold: realLive.threshold },
  realHead: { is: realHead.isHairball, maxShare: realHead.metrics.maxGroupShare },
  realSparse: { is: realSparse.isHairball, maxShare: realSparse.metrics.maxGroupShare },
}));
"""


def test_t_hairball_1_real_corpus_measurement():
    r = _harness(HAIRBALL_JS, (GROUPS,))
    assert r["threshold"] == 0.8
    # 真实语料实测：134/404 ⇒ 最大分组 120/134 = 89.55%（与报告 §2 一致）
    assert r["realLive"]["maxShare"] == 0.8955
    assert r["realLive"]["is"] is True
    # HEAD archive（同 KB 提交态）：61/154 ⇒ 50/61 = 81.97%，仍应命中（阈值 0.80）
    assert r["realHead"]["maxShare"] == 0.8197
    assert r["realHead"]["is"] is True
    # 真实稀疏 KB：329/36 ⇒ 2.74%，不应命中
    assert r["realSparse"]["maxShare"] == 0.0274
    assert r["realSparse"]["is"] is False


def test_t_hairball_2_threshold_is_calibrated_between_measured_groups():
    r = _harness(HAIRBALL_JS, (GROUPS,))
    # 阈值必须落在「已实测良好语料上界」与「已实测毛球语料下界」之间
    good_upper = r["good"]["maxShare"]          # 0.0833
    hairball_lower = min(r["realHead"]["maxShare"], r["realLive"]["maxShare"])  # 0.8197
    assert good_upper < r["threshold"] < hairball_lower
    # 阈值不是拍脑袋：报告里给出推导（min(hairball)-margin）；这里校验数值边界
    assert abs(r["threshold"] - 0.8) < 1e-9


def test_t_hairball_3_red_and_green_bidirectional():
    r = _harness(HAIRBALL_JS, (GROUPS,))
    # 红：已知毛球态（单连通分量 100%）必须命中
    assert r["hairball"]["maxShare"] == 1.0
    assert r["hairball"]["is"] is True
    # 绿：已知良好语料（12×10 群，最大占比 8.33%）必须不命中
    assert r["good"]["maxShare"] == 0.0833
    assert r["good"]["is"] is False
    # 反向证红：旧三条件组合对「良好语料」也命中（labels 120>60 / edgesPerNode 1<4）
    # ⇒ 原组合没有判别力；新单条件才有
    assert r["legacy"]["onGood"] is True, "旧组合在良好语料上竟不命中，红样例失效"
    assert r["legacy"]["onHairball"] is True


# ── T-double ────────────────────────────────────────────────────────────────

CHANNELS_JS = r"""
const V = sandbox.MemoriaGraphVisualChannels;
const current = V.check(V.CHANNELS);
// 红 fixture ①：颜色编码字母序（不同变量）而半径编码 degree
const diffVar = V.CHANNELS.map((c) =>
  c.id === "2d.galaxyColor" ? { ...c, variable: "alphabetical" } : c);
const diffVarResult = V.check(diffVar);
// 红 fixture ②：半径 degree 增大，但颜色对 degree 反向（大节点更暗）
const opposite = V.CHANNELS.map((c) =>
  c.id === "2d.galaxyColor" ? { ...c, direction: -1 } : c);
const oppositeResult = V.check(opposite);
console.log(JSON.stringify({
  currentPass: current.pass,
  conflicts: current.conflicts,
  encodedVariables: current.encodedVariables,
  channels: current.channels,
  diffVar: { pass: diffVarResult.pass, conflicts: diffVarResult.conflicts },
  opposite: { pass: oppositeResult.pass, conflicts: oppositeResult.conflicts },
}));
"""


def test_t_double_1_galaxy_channels_same_variable_same_direction_pass():
    r = _harness(CHANNELS_JS, (ENGINE,))
    assert r["currentPass"] is True, f"当前 galaxy 三通道被误判冲突：{r['conflicts']}"
    assert set(r["encodedVariables"]) == {"degree"}
    # 2D 半径/颜色/halo 亮度 + 3D 颜色/亮度都编码 degree 且同向
    by_id = {c["id"]: c for c in r["channels"]}
    for cid in ("2d.nodeRadius", "2d.galaxyColor", "2d.galaxyHalo", "3d.galaxyColor", "3d.galaxyEmissive", "3d.galaxyHalo"):
        assert by_id[cid]["variable"] == "degree" and by_id[cid]["direction"] == 1
    # 3D 半径不编码变量（等大，D-KGV-04）
    assert by_id["3d.nodeRadius"]["variable"] is None


def test_t_double_2_red_fixture_conflicts_are_detected():
    r = _harness(CHANNELS_JS, (ENGINE,))
    # ① 不同变量 ⇒ 必须报冲突
    assert r["diffVar"]["pass"] is False
    assert any(c["reason"] == "different_variables" for c in r["diffVar"]["conflicts"])
    # ② 同变量方向相反 ⇒ 必须报冲突
    assert r["opposite"]["pass"] is False
    assert any(c["reason"] == "opposite_direction" for c in r["opposite"]["conflicts"])


def test_declared_channels_match_production_render_code():
    """防"声明说谎"：T-double 的通道声明必须能在生产渲染代码里找到对应公式。"""
    v2 = VIEW2D.read_text(encoding="utf-8")
    v3 = VIEW3D.read_text(encoding="utf-8")
    assert "_radiusForNode(n.id, opts.nodeRadius)" in v2
    assert "galaxyNodeColor2D(ratio)" in v2
    assert "halo = 0.14 + ratio * 0.3" in v2
    assert "const scale = 1;" in v3              # 3D 等大
    assert "galaxyColor3D(ratio)" in v3
    assert "0.25 + ratio * 0.45" in v3           # 3D emissive 亮度
    # 3D 光晕半径不随 degree（D-KGV-16），opacity 仍可编码 degree（亮度通道）
    assert "const scale = 1;" in v3.split("_syncHaloGlow() {")[1][:800]
