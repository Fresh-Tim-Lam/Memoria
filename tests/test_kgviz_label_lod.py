"""KGViz v0 标签 LOD/避让（D-KGV-06）机检：T-label-1 / T-label-2 / T-label-3 / T-label-5。

设计冻结：`docs/design/kg-visualization-v0.md §3`（可读性前置；性能前置已撤回）。
实现：`graph-label.js#layoutNodeLabels`（纯函数，屏幕坐标包围盒碰撞 + 度数优先级）；
      2D 渲染层 `graph-view-2d.js#_drawVisibleLabels` 在 ctx.restore() 后按屏幕坐标绘制。

★ 必红 fixture：`lod:false`（全部显示）⇒ 两两包围盒重叠数必须 >0。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
LABEL = APP / "js" / "graph-label.js"
VIEW2D = APP / "js" / "graph-view-2d.js"


def _label_module() -> dict:
    script = f"""
const fs = require("fs"), vm = require("vm");
const sandbox = {{}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("{str(LABEL).replace(chr(92), "/")}", "utf8"), sandbox);
const L = sandbox.MemoriaGraphLabels;
function mkGrid(n, dx, dy) {{
  const items = [];
  for (let i = 0; i < n; i++) {{
    items.push({{ id: "n" + i, text: "label" + i, x: (i % 20) * dx, y: Math.floor(i / 20) * dy, r: 6, degree: (i * 7) % 13 }});
  }}
  return items;
}}
function summarize(layout) {{
  const boxes = [...layout.boxes.values()];
  let overlaps = 0;
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {{
    if (L.boxesOverlap(boxes[i], boxes[j], 1)) overlaps += 1;
  }}
  return {{ visible: layout.visibleCount, all: layout.allCount, hidden: layout.hiddenIds.length,
           topVisible: layout.topIds.every((id) => layout.visibleIds.has(id)),
           overlaps, overlapCount: layout.overlapCount }};
}}
const dense = mkGrid(134, 18, 16);
const lod = L.layoutNodeLabels(dense, {{ lod: true, topN: 10 }});
const red = L.layoutNodeLabels(dense, {{ lod: false, topN: 10 }});
const hiddenId = lod.hiddenIds[0];
const hover = hiddenId ? L.layoutNodeLabels(dense, {{ lod: true, topN: 10, hoverIds: [hiddenId] }}) : null;
// 缩放变稀疏（屏幕坐标 ×1.8）⇒ 密度下降，可见标签应增加
const zoomed = dense.map((it) => ({{ ...it, x: it.x * 1.8, y: it.y * 1.8, r: it.r * 1.8 }}));
const lodZoom = L.layoutNodeLabels(zoomed, {{ lod: true, topN: 10 }});
console.log(JSON.stringify({{
  dense: summarize(lod),
  red: summarize(red),
  hiddenId,
  hoverVisible: hover ? hover.visibleIds.has(hiddenId) : false,
  zoomVisible: lodZoom.visibleCount,
  visible: lod.visibleCount,
  topIds: lod.topIds,
  estimateWidth: L.estimateLabelWidth("hello", 10),
}}));
"""
    p = subprocess.run(["node", "-"], input=script, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, cwd=str(ROOT))
    if p.returncode != 0:
        raise AssertionError(f"node failed: {p.stderr[-3000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_t_label_1_no_pairwise_bbox_overlap_at_100pct():
    d = _label_module()
    assert d["dense"]["overlaps"] == 0, f"LOD 后仍有标签包围盒重叠：{d['dense']}"
    assert d["dense"]["overlapCount"] == 0
    assert d["dense"]["visible"] > 0


def test_t_label_1_red_fixture_all_labels_overlap():
    """必红 fixture（先证红）：关闭避让 ⇒ 全部标签画出来 ⇒ 两两包围盒重叠必须 >0。"""
    d = _label_module()
    assert d["red"]["visible"] == d["red"]["all"], "关闭 LOD 时应全部可见（回退行为）"
    assert d["red"]["overlaps"] > 0, f"必红 fixture 未变红：{d['red']}"


def test_t_label_2_highest_degree_topn_always_visible():
    d = _label_module()
    assert d["dense"]["topVisible"], f"topN 未全部可见：{d['dense']}"
    assert len(d["topIds"]) == 10


def test_t_label_3_zoom_in_reveals_more_labels():
    d = _label_module()
    assert d["zoomVisible"] > d["visible"], (
        f"缩放变稀疏后可见标签未增加（{d['visible']} → {d['zoomVisible']}）"
    )


def test_hovered_hidden_label_can_appear():
    d = _label_module()
    assert d["hiddenId"], "密度不足，未产生隐藏标签（拒绝弱测试）"
    assert d["hoverVisible"], "hover 被隐藏的标签没有出现（信息丢失）"


def test_t_label_5_toggle_off_reverts_to_all_labels():
    d = _label_module()
    assert d["red"]["visible"] == d["red"]["all"]


def test_2d_view_uses_label_lod_and_exposes_machine_state():
    src = VIEW2D.read_text(encoding="utf-8")
    assert "layoutNodeLabels" in src
    assert "labelLod" in src
    assert "_visibleLabelIds" in src and "_labelBoxes" in src and "_labelLodStats" in src
    # 标签必须在屏幕空间绘制：绘制调用在 ctx.restore() 之后
    assert "this._drawVisibleLabels(ctx, labelItems, opts, C);" in src
    assert src.index("ctx.restore();") < src.index("this._drawVisibleLabels(ctx, labelItems, opts, C);")
