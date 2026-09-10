#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Memoria 确定性间隔重复调度脚本（FSRS-5）。

随包分发给知识库内的 Trae 智能体调用：纯标准库、纯计算 + 读写 JSON、可复算、幂等。
数据文件位于 ``<KB>/.memoria/agent/review/``：
  - ``cards.json``    卡片定义，本脚本**只读**（由 agent 维护）。
  - ``progress.json`` 卡片状态与复习日志，本脚本**读写**；写盘采用「同目录临时文件 + os.replace」原子写。

用法::

    python fsrs.py due   [--kb <KB路径>] [--date YYYY-MM-DD]
    python fsrs.py init  --card <card_id> [--kb <KB路径>] [--date YYYY-MM-DD]
    python fsrs.py grade --card <card_id> --grade <1|2|3|4> [--kb <KB路径>] [--date YYYY-MM-DD]
    python fsrs.py --selftest

  - ``--kb``   缺省为当前工作目录。
  - ``--date`` 缺省为系统当天（本地日期）。
  - 各子命令最终 print 一行 JSON；exit code 0 表示成功、非 0 表示失败。

算法依据与版本
--------------
本实现为 **FSRS-5**（19 个参数），默认权重与公式来自 open-spaced-repetition 官方仓库
``awesome-fsrs`` 的 wiki 页面 `The Algorithm` 之「FSRS-5」章节
（https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm ，核对日期 2026-09-10）。

与任务书描述的唯一有意差异：任务书将难度更新写作 ``D' = D - w[6]*(G-3)``（即无阻尼的
FSRS-4.5 形式）；官方 FSRS-5 在难度更新中额外引入**线性阻尼**：

    ΔD(G) = -w[6] * (G - 3)
    D'    = D + ΔD * (10 - D) / 9

经核对以官方为准，故本实现采用带线性阻尼的版本；其余公式（遗忘曲线、间隔反解、初始稳定度 /
难度、成功与遗忘后的稳定度、同日稳定度、D0(4) 均值回归）与官方 FSRS-5 一致。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

SCHEMA_VERSION = 1
ALGORITHM = "fsrs"
FSRS_VERSION = "5"
REQUEST_RETENTION = 0.9

# 遗忘曲线参数：R(t,S) = (1 + FACTOR * t / S) ** DECAY
DECAY = -0.5
FACTOR = 19.0 / 81.0

# 稳定度下限与最大间隔（天）
S_MIN = 0.01
MAX_INTERVAL = 36500

# FSRS-5 官方默认权重（19 个），写入 progress.json 的 params 便于审计/复算
DEFAULT_PARAMS = [
    0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, 1.54575,
    0.1192, 1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315, 2.9898, 0.51655, 0.6621,
]

VALID_STATES = ("new", "learning", "review", "relearning")


class FsrsError(Exception):
    """可预期的输入/数据错误；CLI 会将其转为 JSON 错误输出与非零退出码。"""


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _utc_now() -> str:
    """当前 UTC 时间，ISO-8601（秒级，带 Z 后缀）。"""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _review_dir(kb) -> Path:
    return Path(kb) / ".memoria" / "agent" / "review"


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_date_string(text) -> bool:
    if not isinstance(text, str):
        return False
    try:
        _dt.date.fromisoformat(text)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
# 原子读写
# --------------------------------------------------------------------------- #

def atomic_write_json(path, data) -> None:
    """原子写入 JSON：同目录临时文件 → flush/fsync → os.replace。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # 失败时清理临时文件，避免污染知识库
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def default_progress() -> dict:
    """progress.json 的默认结构（文件不存在时使用）。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "fsrs_version": FSRS_VERSION,
        "params": list(DEFAULT_PARAMS),
        "request_retention": REQUEST_RETENTION,
        "updated_at": _utc_now(),
        "cards": {},
        "log": [],
    }


def load_progress(kb) -> dict:
    """读取 progress.json；不存在则返回默认结构，存在则做最小校验与补齐。"""
    path = _review_dir(kb) / "progress.json"
    if not path.is_file():
        return default_progress()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise FsrsError(f"progress.json 读取失败: {exc}") from exc
    if not isinstance(data, dict):
        raise FsrsError("progress.json 结构非法：顶层应为 JSON 对象")

    base = default_progress()
    base.update(data)  # 保留磁盘上的既有键（只允许新增键）
    if not isinstance(base.get("cards"), dict):
        base["cards"] = {}
    if not isinstance(base.get("log"), list):
        base["log"] = []
    params = base.get("params")
    if not isinstance(params, list) or len(params) != 19 or not all(_is_number(v) for v in params):
        base["params"] = list(DEFAULT_PARAMS)
    if not _is_number(base.get("request_retention")):
        base["request_retention"] = REQUEST_RETENTION
    if not isinstance(base.get("algorithm"), str):
        base["algorithm"] = ALGORITHM
    if not isinstance(base.get("fsrs_version"), str):
        base["fsrs_version"] = FSRS_VERSION
    if not isinstance(base.get("schema_version"), int):
        base["schema_version"] = SCHEMA_VERSION
    return base


def save_progress(kb, progress: dict) -> None:
    progress["updated_at"] = _utc_now()
    atomic_write_json(_review_dir(kb) / "progress.json", progress)


def load_card_ids(kb):
    """读取 cards.json 中的全部 card_id（保持文件内顺序）。"""
    path = _review_dir(kb) / "cards.json"
    if not path.is_file():
        raise FsrsError("cards.json 不存在")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise FsrsError(f"cards.json 读取失败: {exc}") from exc
    cards = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(cards, list):
        raise FsrsError("cards.json 结构非法：应为 {\"cards\": [...]}")
    ids = []
    for item in cards:
        if isinstance(item, dict) and isinstance(item.get("card_id"), str):
            ids.append(item["card_id"])
    return ids


# --------------------------------------------------------------------------- #
# FSRS-5 公式
# --------------------------------------------------------------------------- #

def initial_stability(grade: int, w) -> float:
    """初始稳定度 S0(G) = w[G-1]（G=1..4）。"""
    return float(w[grade - 1])


def initial_difficulty(grade: int, w) -> float:
    """初始难度 D0(G) = clamp(w[4] - exp(w[5]*(G-1)) + 1, 1, 10)。"""
    raw = w[4] - math.exp(w[5] * (grade - 1)) + 1.0
    return _clamp(float(raw), 1.0, 10.0)


def retrievability(elapsed_days: float, stability: float) -> float:
    """可提取性 R(t,S) = (1 + FACTOR * t / S) ** DECAY。"""
    return (1.0 + FACTOR * float(elapsed_days) / float(stability)) ** DECAY


def interval_from_stability(stability: float, retention: float) -> float:
    """由稳定度反解间隔 I(r,S) = (S / FACTOR) * (r ** (1/DECAY) - 1)。"""
    return (float(stability) / FACTOR) * (float(retention) ** (1.0 / DECAY) - 1.0)


def next_interval_days(stability: float, retention: float) -> int:
    """下次间隔（天）：round 后 clamp 到 [1, MAX_INTERVAL]。"""
    raw = interval_from_stability(stability, retention)
    return int(_clamp(round(raw), 1, MAX_INTERVAL))


def update_difficulty(difficulty: float, grade: int, w) -> float:
    """难度更新（官方 FSRS-5，含线性阻尼）→ 均值回归到 D0(4) → clamp 1..10。"""
    d0_easy = initial_difficulty(4, w)  # D0(4)：FSRS-5 的回归目标
    delta = -w[6] * (grade - 3)
    damped = difficulty + delta * (10.0 - difficulty) / 9.0
    reverted = w[7] * d0_easy + (1.0 - w[7]) * damped
    return _clamp(float(reverted), 1.0, 10.0)


def stability_after_recall(stability: float, difficulty: float, r: float, grade: int, w) -> float:
    """回忆成功（G>=2）后的稳定度。"""
    hard_penalty = w[15] if grade == 2 else 1.0
    easy_bonus = w[16] if grade == 4 else 1.0
    growth = (
        math.exp(w[8])
        * (11.0 - difficulty)
        * (stability ** (-w[9]))
        * (math.exp(w[10] * (1.0 - r)) - 1.0)
        * hard_penalty
        * easy_bonus
    )
    return stability * (1.0 + growth)


def stability_after_forget(stability: float, difficulty: float, r: float, w) -> float:
    """遗忘（G==1）后的稳定度，下限 S_MIN。"""
    raw = (
        w[11]
        * (difficulty ** (-w[12]))
        * ((stability + 1.0) ** w[13] - 1.0)
        * math.exp(w[14] * (1.0 - r))
    )
    return max(float(raw), S_MIN)


def stability_same_day(stability: float, grade: int, w) -> float:
    """同日（elapsed_days == 0，短时记忆）稳定度：S * exp(w[17]*(G-3+w[18]))。"""
    return stability * math.exp(w[17] * (grade - 3 + w[18]))


def compute_next_state(card: dict, grade: int, review_date: _dt.date, params, retention: float):
    """按 FSRS-5 计算评分后的卡片状态。

    返回 ``(new_card, elapsed_days)``；``new_card`` 为写回 progress.json 的完整卡片状态。
    纯函数、确定性：相同输入必得相同输出。
    """
    w = list(params)
    reps = int(card.get("reps", 0) or 0)
    lapses = int(card.get("lapses", 0) or 0)
    first_review = reps == 0

    if first_review:
        elapsed_days = 0
        stability = initial_stability(grade, w)
        difficulty = initial_difficulty(grade, w)
    else:
        prev_s = float(card.get("stability") or 0.0)
        prev_d = float(card.get("difficulty") or 0.0)
        last = card.get("last_review")
        if _valid_date_string(last):
            elapsed_days = (review_date - _dt.date.fromisoformat(last)).days
        else:
            elapsed_days = 0
        if elapsed_days < 0:
            elapsed_days = 0

        difficulty = update_difficulty(prev_d, grade, w)
        if elapsed_days == 0:
            stability = stability_same_day(prev_s, grade, w)
        else:
            r = retrievability(elapsed_days, prev_s)
            if grade == 1:
                stability = stability_after_forget(prev_s, prev_d, r, w)
            else:
                stability = stability_after_recall(prev_s, prev_d, r, grade, w)

    stability = max(float(stability), S_MIN)

    # 状态迁移（简化且确定性）
    if first_review:
        state = "learning" if grade == 1 else "review"
    else:
        state = "relearning" if grade == 1 else "review"

    if grade == 1:
        lapses += 1
    reps += 1

    scheduled_days = next_interval_days(stability, retention)
    next_due = review_date + _dt.timedelta(days=scheduled_days)

    new_card = {
        "state": state,
        "due": next_due.isoformat(),
        "stability": round(stability, 6),
        "difficulty": round(difficulty, 6),
        "elapsed_days": elapsed_days,
        "scheduled_days": scheduled_days,
        "reps": reps,
        "lapses": lapses,
        "last_review": review_date.isoformat(),
    }
    return new_card, elapsed_days


# --------------------------------------------------------------------------- #
# 子命令实现（纯 I/O + 计算，返回可 JSON 化的 dict）
# --------------------------------------------------------------------------- #

def op_due(kb, review_date: _dt.date) -> dict:
    """列出所有到期卡片：新卡优先，其后按 due 升序（再按 card_id 升序）。"""
    ids = load_card_ids(kb)
    progress = load_progress(kb)
    target = review_date.isoformat()

    new_ids = []
    due_pairs = []
    for card_id in ids:
        card = progress["cards"].get(card_id)
        if not isinstance(card, dict):
            new_ids.append(card_id)  # 新卡：progress 中不存在 → 视为到期
            continue
        due = card.get("due")
        if _valid_date_string(due):
            if due <= target:
                due_pairs.append((due, card_id))
        else:
            due_pairs.append(("", card_id))  # due 缺失/非法 → 视为到期，排在最前

    new_ids.sort()
    due_pairs.sort(key=lambda pair: (pair[0], pair[1]))
    ordered = new_ids + [card_id for _, card_id in due_pairs]

    return {
        "status": "ok",
        "date": target,
        "due": ordered,
        "count": len(ordered),
    }


def op_init(kb, card_id: str, review_date: _dt.date) -> dict:
    """为 card_id 建立初始状态（state=new，due=review_date）；已存在则不覆盖。"""
    progress = load_progress(kb)
    existing = progress["cards"].get(card_id)
    if isinstance(existing, dict):
        return {
            "status": "ok",
            "card_id": card_id,
            "created": False,
            "state": existing.get("state"),
            "due": existing.get("due"),
            "stability": existing.get("stability"),
            "difficulty": existing.get("difficulty"),
            "reps": int(existing.get("reps", 0) or 0),
            "lapses": int(existing.get("lapses", 0) or 0),
        }

    card = {
        "state": "new",
        "due": review_date.isoformat(),
        "stability": 0.0,
        "difficulty": 0.0,
        "elapsed_days": 0,
        "scheduled_days": 0,
        "reps": 0,
        "lapses": 0,
        "last_review": None,
    }
    progress["cards"][card_id] = card
    save_progress(kb, progress)
    return {
        "status": "ok",
        "card_id": card_id,
        "created": True,
        "state": "new",
        "due": card["due"],
        "stability": 0.0,
        "difficulty": 0.0,
        "reps": 0,
        "lapses": 0,
    }


def op_grade(kb, card_id: str, grade: int, review_date: _dt.date) -> dict:
    """施加一次评分。

    幂等键 = (card_id, review_date)：若 log 中已存在同 card_id 且同 review_date 的记录，
    则不重复施加，直接返回该记录对应的结果（``idempotent`` = true）。
    """
    progress = load_progress(kb)
    params = progress["params"]
    retention = float(progress["request_retention"])
    today = review_date.isoformat()

    # 幂等：命中同日同卡的历史记录
    for entry in reversed(progress["log"]):
        if entry.get("card_id") == card_id and entry.get("review_date") == today:
            card = progress["cards"].get(card_id)
            if not isinstance(card, dict):
                raise FsrsError(f"日志含 card_id={card_id} 但 progress.cards 中无对应状态")
            return {
                "status": "ok",
                "card_id": card_id,
                "grade": int(entry.get("grade", grade)),
                "state": card.get("state"),
                "due": entry.get("next_due"),
                "scheduled_days": int(entry.get("scheduled_days", card.get("scheduled_days", 0) or 0)),
                "stability": card.get("stability"),
                "difficulty": card.get("difficulty"),
                "reps": int(card.get("reps", 0) or 0),
                "lapses": int(card.get("lapses", 0) or 0),
                "idempotent": True,
            }

    card = progress["cards"].get(card_id)
    if not isinstance(card, dict):
        # 未 init 的卡片按新卡处理
        card = {
            "state": "new",
            "due": today,
            "stability": 0.0,
            "difficulty": 0.0,
            "elapsed_days": 0,
            "scheduled_days": 0,
            "reps": 0,
            "lapses": 0,
            "last_review": None,
        }

    new_card, elapsed_days = compute_next_state(card, grade, review_date, params, retention)
    progress["cards"][card_id] = new_card
    progress["log"].append({
        "ts": _utc_now(),
        "card_id": card_id,
        "grade": grade,
        "review_date": today,
        "elapsed_days": elapsed_days,
        "scheduled_days": new_card["scheduled_days"],
        "next_due": new_card["due"],
    })
    save_progress(kb, progress)

    return {
        "status": "ok",
        "card_id": card_id,
        "grade": grade,
        "state": new_card["state"],
        "due": new_card["due"],
        "scheduled_days": new_card["scheduled_days"],
        "stability": new_card["stability"],
        "difficulty": new_card["difficulty"],
        "reps": new_card["reps"],
        "lapses": new_card["lapses"],
        "idempotent": False,
    }


# --------------------------------------------------------------------------- #
# 内置自检（--selftest）
# --------------------------------------------------------------------------- #

def _prepare_kb(kb, card_ids) -> None:
    """在给定 KB 下写出示例 cards.json（自检专用）。"""
    directory = _review_dir(kb)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": _utc_now(),
        "cards": [
            {
                "card_id": card_id,
                "kp_id": card_id,
                "file": "a.md",
                "type": "basic",
                "front": "front",
                "back": "back",
                "source": "agent",
                "created_at": _utc_now(),
            }
            for card_id in card_ids
        ],
    }
    with open(directory / "cards.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def run_selftest() -> int:
    """内置断言自检；全部通过返回 0，否则返回 1。"""
    failures = []
    total = 0

    def check(name: str, condition: bool) -> None:
        nonlocal total
        total += 1
        if not condition:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="fsrs_selftest_") as root:
        # 5) 全程在系统临时目录内，绝不污染仓库/真实知识库
        check(
            "selftest 全程运行于系统临时目录",
            os.path.abspath(root).startswith(os.path.abspath(tempfile.gettempdir())),
        )

        # 1) 确定性：同输入两次运行结果一致
        kb_a = os.path.join(root, "kb_a")
        kb_b = os.path.join(root, "kb_b")
        _prepare_kb(kb_a, ["c1", "c2"])
        _prepare_kb(kb_b, ["c1", "c2"])
        op_init(kb_a, "c1", _dt.date(2026, 1, 1))
        op_init(kb_b, "c1", _dt.date(2026, 1, 1))
        result_a = op_grade(kb_a, "c1", 3, _dt.date(2026, 1, 3))
        result_b = op_grade(kb_b, "c1", 3, _dt.date(2026, 1, 3))
        check("确定性：两次同输入 grade 输出一致", result_a == result_b)
        check(
            "确定性：两次同输入写出的卡片状态一致",
            load_progress(kb_a)["cards"]["c1"] == load_progress(kb_b)["cards"]["c1"],
        )

        # 3) 幂等：同 (card_id, date) 二次 grade 不改变状态
        before = load_progress(kb_a)["cards"]["c1"]
        repeat = op_grade(kb_a, "c1", 3, _dt.date(2026, 1, 3))
        after = load_progress(kb_a)["cards"]["c1"]
        check("幂等：重复评分标记 idempotent=true", repeat.get("idempotent") is True)
        check("幂等：重复评分不改变卡片状态", before == after)
        check("幂等：重复评分返回原 scheduled_days", repeat["scheduled_days"] == result_a["scheduled_days"])

        # 2) 单调性：同一张卡 Good >= Hard、Easy >= Good、Again < Good
        base_card = {
            "state": "review",
            "due": "2026-01-01",
            "stability": 10.0,
            "difficulty": 5.0,
            "elapsed_days": 10,
            "scheduled_days": 10,
            "reps": 3,
            "lapses": 0,
            "last_review": "2026-01-01",
        }
        review_day = _dt.date(2026, 1, 11)
        intervals = {}
        for grade in (1, 2, 3, 4):
            new_card, _ = compute_next_state(
                base_card, grade, review_day, DEFAULT_PARAMS, REQUEST_RETENTION
            )
            intervals[grade] = new_card["scheduled_days"]
        check("单调性：Hard 间隔 <= Good 间隔", intervals[2] <= intervals[3])
        check("单调性：Good 间隔 <= Easy 间隔", intervals[3] <= intervals[4])
        check("单调性：Again 间隔 < Good 间隔", intervals[1] < intervals[3])

        # 4) 原子写与结构合法
        progress = load_progress(kb_a)
        check("结构：schema_version == 1", progress.get("schema_version") == 1)
        check("结构：algorithm == 'fsrs'", progress.get("algorithm") == "fsrs")
        check(
            "结构：params 长度 == 19",
            isinstance(progress.get("params"), list) and len(progress["params"]) == 19,
        )
        check("结构：fsrs_version == '5'", str(progress.get("fsrs_version")) == "5")
        leftovers = [name for name in os.listdir(_review_dir(kb_a)) if name.endswith(".tmp")]
        check("原子写：无遗留 .tmp 临时文件", not leftovers)

        # 附加：due 语义（新卡优先 + due <= date 过滤）
        kb_c = os.path.join(root, "kb_c")
        _prepare_kb(kb_c, ["n1", "r1"])
        op_init(kb_c, "r1", _dt.date(2026, 1, 1))
        op_grade(kb_c, "r1", 3, _dt.date(2026, 1, 1))  # 首次 Good → 3 天后到期
        due_today = op_due(kb_c, _dt.date(2026, 1, 1))
        check("due：未到期卡片被过滤，新卡优先", due_today["due"] == ["n1"])
        due_later = op_due(kb_c, _dt.date(2026, 1, 4))
        check("due：到期后按新卡优先返回", due_later["due"] == ["n1", "r1"])

    if failures:
        for name in failures:
            print(f"[FAIL] {name}")
        print(f"FSRS selftest: FAIL ({total - len(failures)}/{total})")
        return 1
    print(f"FSRS selftest: PASS ({total}/{total})")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fsrs.py",
        description="Memoria FSRS-5 确定性间隔重复调度（标准库实现，无第三方依赖、不联网）",
    )
    parser.add_argument("--selftest", action="store_true", help="运行内置断言自检")
    sub = parser.add_subparsers(dest="command")

    def add_common(sub_parser):
        sub_parser.add_argument("--kb", default=None, help="知识库根目录（缺省为当前工作目录）")
        sub_parser.add_argument("--date", default=None, help="评审日期 YYYY-MM-DD（缺省为本地当天）")

    p_due = sub.add_parser("due", help="列出到期卡片")
    add_common(p_due)

    p_init = sub.add_parser("init", help="为新卡建立初始状态")
    add_common(p_init)
    p_init.add_argument("--card", required=True, help="card_id")

    p_grade = sub.add_parser("grade", help="施加一次评分")
    add_common(p_grade)
    p_grade.add_argument("--card", required=True, help="card_id")
    p_grade.add_argument("--grade", required=True, type=int, choices=[1, 2, 3, 4],
                         help="评分：1=Again 2=Hard 3=Good 4=Easy")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    if args.command is None:
        print(json.dumps(
            {"status": "error", "error": "缺少子命令：请使用 due / init / grade，或 --selftest"},
            ensure_ascii=False,
        ))
        return 2

    try:
        kb = Path(args.kb).expanduser() if args.kb else Path.cwd()
        review_date = _dt.date.fromisoformat(args.date) if args.date else _dt.date.today()
        if args.command == "due":
            result = op_due(kb, review_date)
        elif args.command == "init":
            result = op_init(kb, args.card, review_date)
        elif args.command == "grade":
            result = op_grade(kb, args.card, args.grade, review_date)
        else:  # pragma: no cover - argparse 已限制取值范围
            raise FsrsError(f"未知子命令: {args.command}")
    except (FsrsError, ValueError, OSError, ArithmeticError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
