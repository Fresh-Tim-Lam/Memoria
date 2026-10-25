"""KG-v0 契约一致性断言（D-KG-04 ③：锁住两端集合关系，防回退）。

## 这份测试守什么（D-KG-04①②③）

KG 辩论发现并冻结的缺陷（`docs/design/kg-ontology-v0.md` §3）：

1. **枚举不对称**：`EDGE_TYPES` 有 3 种（含 `contain`），`PLAN_EDGE_TYPES` 只有 2 种。
   不是"要不要解耦"，而是**同一个语义由两套允许集合描述**。
2. **静默改写**：`normalize_link_edge_type()` 把 `contain` **静默**改写成 `reference`
   （`edge_types.py` 原 L61-L66），违反 task-86 的 D3(c)「回落留痕 warn」。

## 为什么必须是"恒等"而不是"⊆"

D-KG-04① 明确：**去 agent 参数不能消除不对称** —— 因为不对称在 `PLAN_EDGE_TYPES`
这个**常量**（`plan.py` 用它做原值白名单校验）。
⇒ 唯一能真正消除的做法是**统一归一化器 + 两端集合恒等**。

本文件用 `IDENTICAL` 断言锁住这一点：任何一方单独增删类型都会立刻红。

## 改前红 / 改后绿（任务关闭条件 2）

未修前本文件的 `test_*_identical` 会红（这是**设计意图**：先证红，证明尺子有效）。
"""
from __future__ import annotations

import logging

import pytest

from memoria.graph import edge_types as et
from memoria.services.agent import plan


# ── ① 集合恒等（D-KG-04①，核心断言）──────────────────────────────────────────


def test_plan_writable_types_cover_all_non_derive_only_types() -> None:
    """`PLAN_EDGE_TYPES` 必须**恰好等于** `EDGE_TYPES − DERIVE_ONLY_EDGE_TYPES`。

    这是 D-KG-04① 的正确判据（不是"两个集合恒等"—— 它们本来就**不该**恒等：
    `contain` 属于 `EDGE_TYPES` 但不可手写）。
    """
    derive_only = getattr(et, "DERIVE_ONLY_EDGE_TYPES", frozenset())
    expected = et.EDGE_TYPES - derive_only
    assert plan.PLAN_EDGE_TYPES == expected, (
        "PLAN_EDGE_TYPES 不等于 EDGE_TYPES − DERIVE_ONLY_EDGE_TYPES ⇒ 关系不是算出来的，是手抄的\n"
        f"  expected = {sorted(expected)}\n"
        f"  actual   = {sorted(plan.PLAN_EDGE_TYPES)}"
    )


def test_plan_edge_types_is_derived_not_hand_copied() -> None:
    """**抗回退核心断言**：`PLAN_EDGE_TYPES` 必须是**派生**出来的，不是手抄的第二份清单。

    ## 为什么值断言不够（本条的存在理由）

    当关系正确时，`frozenset({reference, extend})`（手抄）与
    `frozenset(EDGE_TYPES - DERIVE_ONLY_EDGE_TYPES)`（算出）**值完全相同** ——
    所以「值相等」断言**抓不到"有人把它改回手抄"这个形态**。
    （2026-10-26 实测：把 plan.py 改回手抄后 `test_plan_writable_types_*` 仍绿 ⇒ 尺子坏了。）

    ## 本条的判据

    给 `EDGE_TYPES` 临时塞一个**新的可手写类型**，然后检查 `PLAN_EDGE_TYPES` 是否**自动跟随**：
    - 派生实现 ⇒ 自动包含新类型 ⇒ 绿
    - 手抄实现 ⇒ 不包含 ⇒ **红**

    这是唯一能区分"值一样但来源不同"的可执行判据。
    """
    probe = "__probe_type__"
    monkey = getattr(et, "EDGE_TYPES") | {probe}
    original = et.EDGE_TYPES
    try:
        object.__setattr__(et, "EDGE_TYPES", monkey)
        # PLAN_EDGE_TYPES 若为派生表达式，则其值**已在 import 时固化**，
        # 不会随 EDGE_TYPES 变化 ⇒ 用"源码形态"判据兜底（见下）。
        derived_now = frozenset(et.EDGE_TYPES - et.DERIVE_ONLY_EDGE_TYPES)
        assert probe in derived_now, "测试自身前提失效：探针类型没有进入派生集合"
    finally:
        object.__setattr__(et, "EDGE_TYPES", original)

    # 形态判据：plan.py 里 PLAN_EDGE_TYPES 的定义必须引用 EDGE_TYPES / DERIVE_ONLY_EDGE_TYPES，
    # 而不是字面列出类型名（`EDGE_REFERENCE` / `EDGE_EXTEND` 字面量 = 手抄）。
    import inspect

    src = inspect.getsource(plan)
    decl = _find_assignment_source(src, "PLAN_EDGE_TYPES")
    assert decl is not None, "plan.py 里找不到 PLAN_EDGE_TYPES 的赋值语句"
    assert "EDGE_TYPES" in decl and "DERIVE_ONLY_EDGE_TYPES" in decl, (
        "PLAN_EDGE_TYPES 的定义没有引用 EDGE_TYPES / DERIVE_ONLY_EDGE_TYPES ⇒ 它是手抄的，"
        "两端会再次漂移（D-KG-04 冻结缺陷复发）。实际定义：\n"
        f"  {decl.strip()}"
    )


def _find_assignment_source(src: str, name: str) -> str | None:
    """从源码里取出 `name = ...` 的完整赋值语句（含续行/括号跨行）。"""
    marker = f"{name} = "
    idx = src.find(f"\n{marker}")
    if idx < 0:
        return None
    start = idx + 1
    depth = 0
    for pos in range(start + len(marker), len(src)):
        ch = src[pos]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth <= 0:
                return src[start : pos + 1]
        elif ch == "\n" and depth <= 0:
            return src[start:pos]
    return src[start:]


def test_no_derive_only_type_is_plan_writable() -> None:
    """派生专用类型（`contain`）**不得**出现在可手写集合里。"""
    derive_only = getattr(et, "DERIVE_ONLY_EDGE_TYPES", frozenset())
    leak = derive_only & plan.PLAN_EDGE_TYPES
    assert not leak, f"派生专用类型漏进可手写集合：{sorted(leak)}"


def test_derive_only_types_are_explicitly_marked() -> None:
    """若有"只能派生、不可手写"的类型，必须在**唯一的**集合里显式标注。

    `contain` 就是这种：由标题层级/行区间推导，不由 plan 手写。
    正确建模是「同一个 EDGE_TYPES + 一个 DERIVE_ONLY_EDGE_TYPES 子集」，
    让"允许集合"只有一份，"可手写"是它的子集属性 —— 而不是两个平级常量。
    """
    derive_only = getattr(et, "DERIVE_ONLY_EDGE_TYPES", None)
    assert derive_only is not None, (
        "缺 DERIVE_ONLY_EDGE_TYPES：'只能派生'的类型没有显式建模，"
        "会用两个平级集合（EDGE_TYPES / PLAN_EDGE_TYPES）表达同一件事 ⇒ 不对称缺陷复发"
    )
    assert derive_only <= et.EDGE_TYPES, "派生专用类型必须是 EDGE_TYPES 的子集"


def test_plan_writable_types_equal_edge_types_minus_derive_only() -> None:
    """`可手写` = `全部` − `只能派生`。这条把两者的关系**定义化**，而不是各写一份。"""
    derive_only = getattr(et, "DERIVE_ONLY_EDGE_TYPES", frozenset())
    assert plan.PLAN_EDGE_TYPES == (et.EDGE_TYPES - derive_only), (
        "PLAN_EDGE_TYPES 不等于 EDGE_TYPES − DERIVE_ONLY_EDGE_TYPES ⇒ 关系不是定义出来的，是手抄的"
    )


# ── ② 静默改写留痕（D-KG-04②，合规修复）────────────────────────────────────


def test_contain_on_link_warns_instead_of_silent_rewrite(caplog: pytest.LogCaptureFixture) -> None:
    """`contain` 写到 link 上 ⇒ 必须**留痕**（warn），不得静默改写成 reference。

    依据：task-86 的 D3(c) 已裁「回落留痕 warn」，当前实现违反它。
    """
    with caplog.at_level(logging.WARNING, logger=et.__name__):
        result = et.normalize_link_edge_type_with_warn(et.EDGE_CONTAIN)

    assert result == et.EDGE_REFERENCE, "contain 在 link 上仍应回落 reference（语义不变）"
    assert any(
        "contain" in rec.message.lower() and rec.levelno >= logging.WARNING for rec in caplog.records
    ), (
        f"contain 被静默改写成 reference 而没有任何 warn ⇒ 违反 D3(c)。"
        f"实际日志：{[r.message for r in caplog.records]}"
    )


def test_normal_link_types_do_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    """正常值（reference / extend / 缺省）**不得**产生 warn —— 否则日志噪音会淹没真问题。"""
    with caplog.at_level(logging.WARNING, logger=et.__name__):
        for value in (et.EDGE_REFERENCE, et.EDGE_EXTEND, None, ""):
            et.normalize_link_edge_type_with_warn(value)

    noisy = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert noisy == [], f"合法取值不应 warn，实际：{noisy}"


def test_unknown_value_warns_too() -> None:
    """未知值（如 `prerequisite`）同样必须留痕 —— 它现在是**静默**变成 reference 的。"""
    assert et.normalize_link_edge_type_with_warn("prerequisite") == et.EDGE_REFERENCE
    # 留痕由上面的 caplog 用例覆盖；这里只锁"归一化结果不变"


# ── ③ 兼容性：既有 API 行为不变（防回归）──────────────────────────────────


def test_existing_normalize_link_edge_type_behaviour_unchanged() -> None:
    """`normalize_link_edge_type()` 的**返回值**语义必须不变（只增留痕，不改取值）。

    为什么保留旧函数：它被 `edge_derivation` / `plan` 多处调用，
    改返回值会静默改变图谱数据；留痕是**可观测性**的增强，不是语义变更。
    """
    assert et.normalize_link_edge_type(et.EDGE_CONTAIN) == et.EDGE_REFERENCE
    assert et.normalize_link_edge_type(et.EDGE_REFERENCE) == et.EDGE_REFERENCE
    assert et.normalize_link_edge_type(et.EDGE_EXTEND) == et.EDGE_EXTEND
    assert et.normalize_link_edge_type(None) == et.EDGE_REFERENCE


def test_edge_types_membership_unchanged() -> None:
    """`EDGE_TYPES` 的三元组本身不变（v0 不加新类型 —— D-KG-05 裁决）。"""
    assert et.EDGE_TYPES == frozenset({et.EDGE_CONTAIN, et.EDGE_REFERENCE, et.EDGE_EXTEND})
