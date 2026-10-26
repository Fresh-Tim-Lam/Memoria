"""KGViz 埋点 E1/E2（D-KGV-08）机检：T-tel-1..7。

设计冻结：`docs/design/kg-visualization-v0.md §5`。
实现：`memoria/storage/graph_telemetry.py`（用户态目录 append-only JSONL、失败静默）
      + `ui.py` 两条 RPC（record / summary）
      + `graph-settings.js` 前端采集（250ms 合并、失败静默）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoria.storage import graph_telemetry as tel


@pytest.fixture(autouse=True)
def _isolated_user_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "config"))
    tel.reset_for_tests()
    yield
    tel.reset_for_tests()


def _file() -> Path:
    return tel.telemetry_path()


def test_t_tel_1_node_radius_event_written_with_from_to():
    r = tel.record_events([{"event": "nodeRadius_change", "ts": 111, "from": 6, "to": 8}])
    assert r["status"] == "ok" and r["appended"] == 1
    lines = _file().read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["event"] == "nodeRadius_change" and rec["from"] == 6 and rec["to"] == 8
    assert rec["v"] == 1 and rec["ts"] == 111


def test_t_tel_2_graph_style_event_written_with_from_to():
    tel.record_events([{"event": "graphStyle_change", "ts": 222, "from": "force", "to": "galaxy"}])
    rec = json.loads(_file().read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["event"] == "graphStyle_change" and rec["from"] == "force" and rec["to"] == "galaxy"


def test_t_tel_3_append_only_and_corrupt_line_does_not_block():
    tel.record_events([{"event": "nodeRadius_change", "from": 6, "to": 7}])
    first = _file().read_bytes()
    # 人为插入一条损坏行（模拟半写/磁盘损坏）
    with _file().open("a", encoding="utf-8") as f:
        f.write("{ this is not json\n")
    # 后续追加必须仍然成功（append-only，不因坏行重写/失败）
    r = tel.record_events([{"event": "nodeRadius_change", "from": 7, "to": 9}])
    assert r["status"] == "ok" and r["appended"] == 1
    raw = _file().read_bytes()
    assert raw.startswith(first), "append-only 被破坏：旧字节被重写"
    data = tel.read_events()
    assert data["bad_lines"] == 1, "损坏行应被跳过并计数"
    assert [e["to"] for e in data["events"]] == [7, 9]


def test_t_tel_4_summary_answers_two_questions():
    # 10 条记录：E1 6→8 ×2、8→10 ×1；E2 force→galaxy ×3、galaxy→force ×2
    events = []
    events += [{"event": "nodeRadius_change", "from": 6, "to": 8}] * 2
    events += [{"event": "nodeRadius_change", "from": 8, "to": 10}] * 1
    events += [{"event": "graphStyle_change", "from": "force", "to": "galaxy"}] * 3
    events += [{"event": "graphStyle_change", "from": "galaxy", "to": "force"}] * 2
    r = tel.record_events(events)
    assert r["appended"] == 8
    s = tel.summary()
    assert s["events_total"] == 8
    assert s["E1_nodeRadius"]["count"] == 3
    assert s["E1_nodeRadius"]["transition_counts"] == {"6->8": 2, "8->10": 1}
    assert s["E1_nodeRadius"]["changed_count"] == 3
    assert s["E2_graphStyle"]["count"] == 5
    assert s["E2_graphStyle"]["distribution"] == {"galaxy": 3, "force": 2}
    assert s["E2_graphStyle"]["transition_counts"] == {"force->galaxy": 3, "galaxy->force": 2}


def test_t_tel_5_no_network_imports_or_calls():
    src = Path(tel.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import urllib", "import httpx", "socket.", "urlopen"):
        assert forbidden not in src, f"埋点模块出现网络调用痕迹：{forbidden}"


def test_t_tel_6_no_event_no_file_and_same_value_skipped():
    # 无变化（from == to）不应落盘，也不应创建文件
    r = tel.record_events([{"event": "nodeRadius_change", "from": 6, "to": 6}])
    assert r["appended"] == 0 and r["skipped"] == 1
    assert not _file().exists()
    # 禁采字段出现 ⇒ 丢弃（不是写入后再过滤）
    r = tel.record_events([{"event": "nodeRadius_change", "from": 6, "to": 7, "node_radius_px": 12}])
    assert r["appended"] == 0 and r["skipped"] == 1
    assert not _file().exists()


def test_t_tel_7_write_failure_is_silent_and_counted(tmp_path, monkeypatch):
    # 把落盘目录指到一个"父路径是文件"的非法位置 ⇒ mkdir 必失败
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(blocker / "cannot" / "mkdir"))
    r = tel.record_events([{"event": "nodeRadius_change", "from": 6, "to": 8}])
    assert r["status"] == "degraded" and r["appended"] == 0
    assert r["write_failures"] >= 1
    assert "error" in r
    # 再写一次仍不抛错、计数递增（可观测）
    tel.record_events([{"event": "graphStyle_change", "from": "force", "to": "galaxy"}])
    s = tel.summary()
    assert s["write_failures"] >= 2
    # 读取摘要也不能抛错
    assert s["status"] == "ok"


def test_rpc_wrappers_never_raise(monkeypatch):
    from memoria.presentation.api.ui import UIAPI

    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(Path("Z:/definitely-not-exists") / "x"))
    r = UIAPI.record_graph_telemetry(None, [{"event": "nodeRadius_change", "from": 6, "to": 9}])
    assert isinstance(r, dict) and r["status"] in ("ok", "degraded")
    s = UIAPI.get_graph_telemetry_summary(None)
    assert isinstance(s, dict) and s["status"] in ("ok", "degraded")


def test_front_end_collects_e1_e2_with_coalescing_and_silent_failure():
    js = (Path(tel.__file__).parents[1] / "ui/static/app/js/graph-settings.js").read_text(encoding="utf-8")
    assert "nodeRadius_change" in js and "graphStyle_change" in js
    assert "record_graph_telemetry" in js
    assert "TEL_COALESCE_MS" in js and "setTimeout" in js
    assert "TEL_COALESCE_MS = 250" in js
    # T-tel-7：RPC 调用必须 catch（静默降级）
    assert "Promise.resolve(api.record_graph_telemetry(events, ctx)).catch(() => {})" in js
    # 禁采字段不在前端事件里出现（注释里声明"不采"是允许的；只检查代码行）
    code = "\n".join(ln for ln in js.splitlines() if not ln.strip().startswith("//"))
    assert "node_radius_px" not in code
    assert "labelHover" not in code
