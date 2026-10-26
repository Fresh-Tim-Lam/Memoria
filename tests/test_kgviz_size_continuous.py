"""KGViz v0 节点大小连续变化（D-KGV-13）机检：T-size-2 / T-size-3 / T-size-4。

设计冻结：`docs/design/kg-visualization-v0.md §1.2-1.3`、`§8`（T-size）。
实现：`graph-engine.js` 的纯函数出口 `MemoriaGraphSizing` + engine 实例方法（2D 渲染/ tooltip 共用）。

★ T-size-3 是「连续 vs 偷偷分桶」的唯一直接证据：
   本文件先用一个**必红 fixture**（把映射改成 3 档）证明该检查真的会红，再对实现断言为绿。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
ENGINE = APP / "js" / "graph-engine.js"
VIEW2D = APP / "js" / "graph-view-2d.js"
VIEW3D = APP / "js" / "graph-view-3d.js"
LABEL = APP / "js" / "graph-label.js"
I18N = APP / "i18n"

# 与冻结语料同量级的 distinct degree 分布（134 节点语料 distinct=21，max=25，含 0 度与长尾）
FIXTURE_DISTINCT_DEGREES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25]


def _node_json(script: str) -> dict:
    p = subprocess.run(["node", "-"], input=script, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, cwd=str(ROOT))
    if p.returncode != 0:
        raise AssertionError(f"node failed: {p.stderr[-2000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def _load_sizing() -> dict:
    engine = str(ENGINE).replace("\\", "/")
    script = f"""
const fs = require("fs"), vm = require("vm");
const sandbox = {{}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("{engine}", "utf8"), sandbox);
const S = sandbox.MemoriaGraphSizing;
const distinct = {json.dumps(FIXTURE_DISTINCT_DEGREES)};
const radius = distinct.map((d) => S.radiusForDegree(d, distinct, 6));
const t = distinct.map((d) => S.normalizedRankT(d, distinct));
const range = S.sizingRangeForBase(6);
const range4 = S.sizingRangeForBase(4);
const range12 = S.sizingRangeForBase(12);
// 无向度口径：3 条 link（source/target 各计一次）⇒ 端点度 [2,2,1,1] 之类
const deg = S.computeUndirectedDegrees(
  [{{id: "a"}}, {{id: "b"}}, {{id: "c"}}, {{id: "d"}}],
  [{{source: "a", target: "b"}}, {{source: "a", target: "c"}}, {{source: "b", target: "d"}}]
);
const degObj = {{}};
for (const [k, v] of deg) degObj[k] = v;
const distinctComputed = S.distinctSortedDegrees(deg, ["a", "b", "c", "d"]);
console.log(JSON.stringify({{distinct, radius, t, range, range4, range12, degObj, distinctComputed}}));
"""
    return _node_json(script)


def _plateau_ratio(degrees: list[int], radii: list[float], eps: float = 0.01) -> tuple[float, int]:
    """按 distinct degree 升序计算相邻半径差；返回（平台段占比, 平台段数）。

    注意：同 degree 同半径是【正确行为】（连续映射的 tie），不计入平台；只比较不同 degree 之间。
    """
    deltas = [abs(radii[i + 1] - radii[i]) for i in range(len(radii) - 1)]
    if not deltas:
        return 0.0, 0
    flat = sum(1 for d in deltas if d < eps)
    return flat / len(deltas), flat


def _size3(degrees: list[int], radii: list[float]) -> dict:
    distinct_radii = len({round(r, 6) for r in radii})
    ratio, flat = _plateau_ratio(degrees, radii)
    return {
        "distinct_degrees": len(degrees),
        "distinct_radii": distinct_radii,
        "plateau_ratio": round(ratio, 4),
        "plateau_segments": flat,
        "pass_distinct": distinct_radii == len(degrees),
        "pass_plateau": ratio <= 0.05,
    }


# ── T-size-2：单调性 ──────────────────────────────────────────────────────
def test_t_size_2_radius_is_monotonic_nondecreasing_in_degree():
    data = _load_sizing()
    degrees, radii = data["distinct"], data["radius"]
    assert len(degrees) == len(radii) >= 10
    for i in range(len(radii) - 1):
        assert radii[i + 1] >= radii[i], f"反转：degree {degrees[i]}→{degrees[i+1]} 半径 {radii[i]}→{radii[i+1]}"


# ── T-size-3：连续性（先证红 fixture，再证绿）─────────────────────────────
def test_t_size_3_red_fixture_bucketed_mapping_is_detected():
    """必红 fixture：把连续映射改成「偷偷 3 档」⇒ T-size-3 必须红。

    这是本任务的核心：如果这个 fixture 不红，说明检查没有判别力，连续化只是文档说法。
    """
    data = _load_sizing()
    degrees, t, rng = data["distinct"], data["t"], data["range"]
    span = rng["max"] - rng["min"]
    # 故意偷懒分桶：t∈[0,1] → 3 个档位（0 / 0.5 / 1）半径
    bucketed = [rng["min"] + span * (min(2, int(tv * 3)) / 2) for tv in t]
    res = _size3(degrees, bucketed)
    assert not res["pass_distinct"], f"必红 fixture 未被识别为分桶：radii={sorted(set(bucketed))} res={res}"
    assert res["distinct_radii"] <= 3
    assert not res["pass_plateau"], f"必红 fixture 未检测出平台：plateau_ratio={res['plateau_ratio']}"
    # 额外的判别力：分桶后 distinct 半径远少于 distinct degree
    assert res["distinct_radii"] < res["distinct_degrees"]


def test_t_size_3_implementation_is_continuous_not_bucketed():
    data = _load_sizing()
    res = _size3(data["distinct"], data["radius"])
    assert res["pass_distinct"], f"distinct 半径数 != distinct degree 数：{res}"
    assert res["pass_plateau"], f"出现平台（偷偷分桶）：{res}"
    # 数值上应严格连续：每个 distinct degree 一个不同半径
    radii = data["radius"]
    assert len({round(r, 9) for r in radii}) == len(radii)


# ── T-size-4：范围 ────────────────────────────────────────────────────────
def test_t_size_4_radius_range_and_user_setting_scaling():
    data = _load_sizing()
    radii = data["radius"]
    # 设计：基准 6.0 × [0.75, 1.65] = [4.50, 9.90]；±0.5 容差（±1.0px 反锯齿偏移的一半）
    assert abs(min(radii) - 4.50) <= 0.5, f"min radius={min(radii)} 不在 4.50±0.5"
    assert abs(max(radii) - 9.90) <= 0.5, f"max radius={max(radii)} 不在 9.90±0.5"
    assert abs(data["range"]["min"] - 4.5) < 1e-9
    assert abs(data["range"]["max"] - 9.9) < 1e-9
    # U-KGV-2：v0 按【随基准缩放】实现（用户 nodeRadius 4–12）
    assert abs(data["range4"]["min"] - 3.0) < 1e-9 and abs(data["range4"]["max"] - 6.6) < 1e-9
    assert abs(data["range12"]["min"] - 9.0) < 1e-9 and abs(data["range12"]["max"] - 19.8) < 1e-9


# ── 度数口径 / 渲染接线 / 3D 等大 / tooltip ──────────────────────────────
def test_degree_caliber_is_undirected_and_consistent():
    data = _load_sizing()
    assert data["degObj"] == {"a": 2, "b": 2, "c": 1, "d": 1}
    assert data["distinctComputed"] == [1, 2]


def test_2d_uses_continuous_radius_and_hit_radius_follows_node_size():
    src = VIEW2D.read_text(encoding="utf-8")
    assert "_radiusForNode(n.id, opts.nodeRadius)" in src
    assert "this._radiusForNode(link.source, opts.nodeRadius)" in src
    # 旧的双重缩放（galaxy 再乘 1.5）必须移除
    assert "if (gStats) r = r * (1 + ratio * 0.5);" not in src
    # 大节点边缘必须可点中（命中半径随视觉半径增长）
    assert "Math.max(this.opts.nodeRadius + 6, this._radiusForNode(n.id, this.opts.nodeRadius) + 2)" in src


def test_3d_nodes_are_equal_size_no_degree_scaling():
    src = VIEW3D.read_text(encoding="utf-8")
    start = src.index("_rebuildGraph() {")
    tail = src[start + 1:]
    # 截到下一个同级方法定义（缩进 4 空格 + 方法名 + "("）
    nxt = tail.find("\n    _")
    block = tail[: nxt if nxt > 0 else len(tail)]
    assert "const scale = 1;" in block, "D-KGV-04：3D 节点必须等大（scale=1）"
    assert "scale = 1 + ratio * 0.4;" not in block, "3D 仍在用 degree 改节点大小（违反 D-KGV-04）"
    assert "mesh.scale.set(scale, scale, scale);" in block


def test_3d_halo_radius_does_not_depend_on_degree():
    """D-KGV-16：3D galaxy 光晕半径也必须不随 degree 变（否则绕过"3D 不做大小"的裁决）。"""
    src = VIEW3D.read_text(encoding="utf-8")

    def method_block(name: str) -> str:
        start = src.index(name + "() {")
        tail = src[start + 1:]
        nxt = tail.find("\n    _")
        return tail[: nxt if nxt > 0 else len(tail)]

    glow = method_block("_syncHaloGlow")
    assert "const scale = 1;" in glow, "光晕半径仍在随 degree 变化（D-KGV-16）"
    assert "scale = 1 + ratio * 0.4;" not in glow
    assert "halo.userData.baseScale = r * (4 + scale * 3 + glow * 2);" in glow

    rebuild = method_block("_rebuildGraph")
    assert "const hs = r * (4 + scale * 3 + glow * 2);" in rebuild
    assert "ratio" not in rebuild.split("const hs")[1].split(";")[0], "光晕 hs 仍含 ratio"


def test_tooltip_shows_absolute_degree_bilingual():
    label = LABEL.read_text(encoding="utf-8")
    assert "degreeText" in label and "resolveNodeHoverHtml(node, opts)" in label
    app = (APP / "js" / "app.js").read_text(encoding="utf-8")
    assert 'engine.degreeOf(node.id)' in app
    assert 'T("graph.hover.degree", { n: deg })' in app
    zh = (I18N / "zh-CN.js").read_text(encoding="utf-8")
    en = (I18N / "en.js").read_text(encoding="utf-8")
    assert 'degree: "连接数 {n}"' in zh
    assert 'degree: "Connections: {n}"' in en
