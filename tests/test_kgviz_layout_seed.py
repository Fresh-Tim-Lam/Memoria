"""KGViz v0 布局确定性种子（D-KGV-07）机检：T-stable-1/2/5。

设计冻结：`docs/design/kg-visualization-v0.md §4`、§8（T-stable）。
实现：`graph-engine.js` 的 `MemoriaGraphSeed`（mulberry32 + 默认种子）+ 两个 layout 模块的 `setSeed/getSeed`，
      所有初始化随机源与近重合守卫都走注入 RNG（不再用 Math.random）。

★ T-stable-2 是「确定性不是把随机删掉」的唯一证据：换种子后坐标必须改变。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
JS = APP / "js"

DEFAULT_SEED = 0x9E3779B9


def _node_json(script: str) -> dict:
    p = subprocess.run(["node", "-"], input=script, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT))
    if p.returncode != 0:
        raise AssertionError(f"node failed: {p.stderr[-3000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def _vm_harness(extra: str) -> dict:
    files = [
        "graph-engine.js",
        "graph-bh-tree.js",
        "graph-layout-sim-core.js",
        "graph-layout-2d.js",
        "graph-layout-3d.js",
    ]
    file_js = "\n".join(
        f'vm.runInContext(fs.readFileSync({json.dumps(str(JS / f).replace(chr(92), "/"))}, "utf8"), sandbox);'
        for f in files
    )
    script = f"""
const fs = require("fs"), vm = require("vm");
const sandbox = {{}};
vm.createContext(sandbox);
{file_js}
{extra}
"""
    return _node_json(script)


def _synthetic_graph(n=60):
    """确定性合成图：n 个节点、链 + 少量跨边（只用于布局机检，不代表真实语料）。"""
    nodes = [{"id": f"n{i}"} for i in range(n)]
    links = [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(n - 1)]
    links += [{"source": f"n{i}", "target": f"n{(i * 7 + 3) % n}"} for i in range(0, n, 5)]
    return nodes, links


def _snapshot_roundtrip(dim: str) -> dict:
    nodes, links = _synthetic_graph()
    extra = f"""
const nodes = {json.dumps(nodes)};
const links = {json.dumps(links)};
const Layout = sandbox.{'MemoriaGraphLayout2D' if dim == '2d' else 'MemoriaGraphLayout3D'};
const engine = {{ nodes, links }};
function snap(layout) {{
  return layout.nodes.map((n) => [n.id, n.x, n.y, n.z].map((v) => (typeof v === 'number' ? v.toPrecision(17) : v)).join('|')).join('\\n');
}}
const layout = new Layout({{}});
layout.loadFromEngine(engine, {{}});
const first = snap(layout);
layout.loadFromEngine(engine, {{}});
const second = snap(layout);
const seedBefore = layout.getSeed();
layout.setSeed(0x12345678, {{ relayout: true }});
const third = snap(layout);
const seedAfter = layout.getSeed();
layout.setSeed({DEFAULT_SEED}, {{ relayout: true }});
const fourth = snap(layout);
console.log(JSON.stringify({{
  dim: {json.dumps(dim)},
  firstEqualsSecond: first === second,
  firstEqualsFourth: first === fourth,
  differentSeedChanged: first !== third,
  changedNodes: first.split('\\n').filter((row, i) => row !== third.split('\\n')[i]).length,
  seedBefore, seedAfter,
  hasSetSeed: typeof layout.setSeed === 'function',
  sample: first.split('\\n').slice(0, 3),
}}));
"""
    return _vm_harness(extra)


def test_t_stable_1_same_seed_twice_is_byte_identical_2d_and_3d():
    """T-stable-1：同一语料 + 同种子连续初始化 2 次 ⇒ 坐标逐节点字节级一致（2D/3D 都要）。"""
    for dim in ("2d", "3d"):
        r = _snapshot_roundtrip(dim)
        assert r["hasSetSeed"], f"{dim}: 缺少 setSeed（T-stable-5）"
        assert r["firstEqualsSecond"], f"{dim}: 同种子两次初始化坐标不一致（T-stable-1 失败）"
        # 换回默认种子后仍与首次一致（证明种子是唯一变量）
        assert r["firstEqualsFourth"], f"{dim}: 恢复默认种子后坐标与首次不一致"


def test_t_stable_2_different_seed_changes_layout():
    """T-stable-2：换种子 ⇒ 坐标必须不同（否则只是把随机删成固定值/规则圆环）。"""
    for dim in ("2d", "3d"):
        r = _snapshot_roundtrip(dim)
        assert r["differentSeedChanged"], f"{dim}: 换种子后坐标完全相同 ⇒ 种子未生效（T-stable-2 失败）"
        assert r["changedNodes"] >= int(0.9 * 60), (
            f"{dim}: 换种子只改了 {r['changedNodes']}/60 个节点，随机性太弱"
        )


def test_t_stable_1_red_fixture_nondeterministic_rng_is_detected():
    """必红 fixture（先证红）：把 RNG 换回非确定性 ⇒ 同一次测试里连续初始化 2 次坐标必须不同。

    如果这个 fixture 不红，说明 T-stable-1 根本分不出"种子生效"和"什么都没做"。
    """
    nodes, links = _synthetic_graph()
    extra = f"""
const nodes = {json.dumps(nodes)};
const links = {json.dumps(links)};
// 必红 fixture：用非确定性 RNG 覆盖 engine 提供的确定性 RNG（模拟改前 Math.random）
sandbox.MemoriaGraphSeed.createSeededRandom = () => () => Math.random(); // host Math = 非确定性
const Layout = sandbox.MemoriaGraphLayout2D;
const layout = new Layout({{}});
const engine = {{ nodes, links }};
const snap = () => layout.nodes.map((n) => n.x.toPrecision(17) + '|' + n.y.toPrecision(17)).join('\\n');
layout.loadFromEngine(engine, {{}});
const first = snap();
layout.loadFromEngine(engine, {{}});
const second = snap();
console.log(JSON.stringify({{ different: first !== second }}));
"""
    r = _vm_harness(extra)
    assert r["different"], "必红 fixture 仍未变红：T-stable-1 无法区分非确定性随机（检查没有判别力）"


def test_t_stable_5_both_layout_modules_have_injected_seed():
    for fname in ("graph-layout-2d.js", "graph-layout-3d.js"):
        src = (JS / fname).read_text(encoding="utf-8")
        assert "DEFAULT_LAYOUT_SEED" in src and "makeLayoutRng" in src
        assert "setSeed(seed" in src and "getSeed()" in src
        # 不允许在函数体里直接调用 Math.random（注释除外）——只允许 default 回退已删除
        code_lines = [ln.strip() for ln in src.splitlines() if "Math.random" in ln and not ln.strip().startswith("//") and "不再用" not in ln]
        assert code_lines == [], f"{fname} 仍有 Math.random 调用：{code_lines[:3]}"


def test_engine_exposes_seeded_rng_and_default_seed():
    r = _vm_harness(
        """
const Seed = sandbox.MemoriaGraphSeed;
const a = Seed.createSeededRandom(123);
const b = Seed.createSeededRandom(123);
const c = Seed.createSeededRandom(124);
const seqA = [a(), a(), a()], seqB = [b(), b(), b()], seqC = [c(), c(), c()];
const eng = new sandbox.MemoriaGraphEngine();
eng.setLayoutSeed(777);
console.log(JSON.stringify({
  defaultSeed: Seed.DEFAULT_LAYOUT_SEED,
  sameSeedSequenceEqual: JSON.stringify(seqA) === JSON.stringify(seqB),
  diffSeedSequenceDiffers: JSON.stringify(seqA) !== JSON.stringify(seqC),
  engineSeed: eng.layoutSeed(),
}));
"""
    )
    assert r["defaultSeed"] == DEFAULT_SEED
    assert r["sameSeedSequenceEqual"] and r["diffSeedSequenceDiffers"]
    assert r["engineSeed"] == 777
