"""I-12 `ErrorMap`：S6 + ADDENDUM-1/2 的 ``GRAPH_*`` 错误码唯一映射表（只读契约）。

## 单一真源（冻结输入，不得在此改写语义）

| 来源 | sha256 | 贡献 |
|---|---|---|
| ``S6-contract-v1.md`` | ``40f12e5f…`` | §S6-6 四个 + §S6-3 一个 |
| ``S6-ADDENDUM-1.md`` | ``f9918dfd…`` | S7 工具 6 个 |
| ``S6-ADDENDUM-2.md`` | ``45b99ab2…`` | S10 KP/边/curation 14 个 |

## 契约（S6 §S6-9）

- **canonical 一律 ``GRAPH_*``**；S2–S5 旧码只以 ``legacy_code`` 形式保留映射，**不得**作为 canonical 返回。
- **未知错误 ⇒ ``GRAPH_INTERNAL``**（绝不抛出未命名码、绝不静默成功）。
- 所有错误**必须带 ``audit_id``**（ADDENDUM-1 §1、ADDENDUM-2 §1）。
- i18n key 归 UI；本模块只声明 key 身份，不做翻译。
- **新增码只增不删**：改语义/删码须重开 S6（§6 变更控制）⇒ 本表由测试对冻结文档逐码反查，
  文档里出现而表里没有的码会让测试红。

## 为什么 S6 有 5 个而不是 4 个

任务书按 ``S6 4 + ADDENDUM-1 6 + ADDENDUM-2 14`` 计；``S6-6`` 确为 4 个，
但 ``S6-3`` 另冻结了 ``GRAPH_HISTORY_SIGNATURE_INVALID``。**覆盖是下限不是上限**，
漏掉它会得到一个真实缺失的码 ⇒ 本表收 5 个（并在 ``S6_ONLY_CODES`` 注明来源）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: 未知错误 / 契约内部故障的兜底码。**任何无法映射的错误都必须落到这里。**
GRAPH_INTERNAL = "GRAPH_INTERNAL"

#: 常用码的具名常量（供其它模块 import；值与 ``ERROR_SPECS`` 的键一致）。
GRAPH_WRITE_FORBIDDEN = "GRAPH_WRITE_FORBIDDEN"      #: agent 尝试写图/curation（v1 只读）
GRAPH_EDGE_INVALID = "GRAPH_EDGE_INVALID"            #: 边 type/字段非法
GRAPH_KP_INVALID = "GRAPH_KP_INVALID"                #: KP 字段/范围/锚非法

#: 只有 legacy 身份、**不是** canonical 的码（S2–S5 历史命名）。
#: 出现在外部输入里时会被 ``canonicalize()`` 折回 canonical。
LEGACY_ONLY_CODES: frozenset[str] = frozenset({"GRAPH_EDITION_STALE"})

#: 允许的 severity 取值（冻结：仅两档；不引入 info/debug 以免"降级即静默"）。
SEVERITIES: frozenset[str] = frozenset({"error", "warn"})


@dataclass(frozen=True)
class ErrorSpec:
    """一个 canonical ``GRAPH_*`` 码的完整身份。"""

    code: str
    legacy_code: str          #: 旧码映射；空串表示"旧无对应"
    severity: str             #: ``error`` / ``warn``
    i18n_key: str             #: UI 翻译键身份（不做翻译）
    source: str               #: 冻结来源文档（可追溯到 S6 / ADD-1 / ADD-2）
    note: str = ""            #: 触发条件摘要（可读，不参与机检判定）


def _s6() -> list[ErrorSpec]:
    """``S6-contract-v1.md`` 冻结的码。

    ``S6-6`` 只给码不给 severity/i18n（S6-9：i18n 归 UI）⇒ 本模块按语义补全，
    属 B1 实现赋值，**不改 S6 语义**；ADDENDUM 侧的 severity/i18n 则逐字照抄冻结表。
    """
    return [
        ErrorSpec("GRAPH_FRAME_ID_INVALID", "", "error", "graph.frame.id_invalid",
                  "S6-contract-v1.md", "frame_id 非法/不可复算（S6-6、S6-7、R-S6-1）"),
        ErrorSpec("GRAPH_PRESENCE_INVALID", "", "error", "graph.presence.invalid",
                  "S6-contract-v1.md", "presence 三值或 rule_id 非法（S6-6）"),
        ErrorSpec("GRAPH_SUBSET_VIOLATION", "", "error", "graph.subset.violation",
                  "S6-contract-v1.md", "subset 不守恒（S6-6）"),
        ErrorSpec("GRAPH_BUDGET_INVALID", "", "warn", "graph.budget.invalid",
                  "S6-contract-v1.md", "预算非法（S6-6）"),
        ErrorSpec("GRAPH_HISTORY_SIGNATURE_INVALID", "", "error", "graph.history.signature_invalid",
                  "S6-contract-v1.md", "history 签名验证失败（S6-3）"),
    ]


def _add1() -> list[ErrorSpec]:
    """``S6-ADDENDUM-1.md`` §1 表格**逐字**照抄。"""
    return [
        ErrorSpec("GRAPH_TOOL_INPUT_INVALID", GRAPH_INTERNAL, "error",
                  "graph.tool.input_invalid", "S6-ADDENDUM-1.md", "工具参数缺失/非法/越界"),
        ErrorSpec("GRAPH_TOOL_BUDGET_EXCEEDED", "GRAPH_BUDGET_INVALID", "warn",
                  "graph.tool.budget_exceeded", "S6-ADDENDUM-1.md",
                  "max_tokens/max_nodes 连 summary 都无法满足"),
        ErrorSpec("GRAPH_ANCHOR_STALE", "GRAPH_EDITION_STALE", "warn",
                  "graph.tool.anchor_stale", "S6-ADDENDUM-1.md", "引用 anchor 对应版本已失效"),
        ErrorSpec("GRAPH_RETRIEVAL_UNAVAILABLE", GRAPH_INTERNAL, "error",
                  "graph.tool.retrieval_unavailable", "S6-ADDENDUM-1.md", "S9 检索不可用/超时"),
        ErrorSpec("GRAPH_WRITE_FORBIDDEN", GRAPH_INTERNAL, "error",
                  "graph.tool.write_forbidden", "S6-ADDENDUM-1.md",
                  "agent 尝试写图/curation（v1 只读）"),
        ErrorSpec("GRAPH_TOOL_AUDIT_FAILED", GRAPH_INTERNAL, "error",
                  "graph.tool.audit_failed", "S6-ADDENDUM-1.md", "工具调用审计落盘失败"),
    ]


def _add2() -> list[ErrorSpec]:
    """``S6-ADDENDUM-2.md`` §1 表格**逐字**照抄（14 个）。"""
    return [
        ErrorSpec("GRAPH_KP_INVALID", GRAPH_INTERNAL, "error", "graph.kp.invalid",
                  "S6-ADDENDUM-2.md", "KP 字段/范围/锚非法"),
        ErrorSpec("GRAPH_KP_DUPLICATE", GRAPH_INTERNAL, "warn", "graph.kp.duplicate",
                  "S6-ADDENDUM-2.md", "同 id/同 name 重复 KP 未合并"),
        ErrorSpec("GRAPH_KP_EVIDENCE_MISSING", GRAPH_INTERNAL, "error", "graph.kp.evidence_missing",
                  "S6-ADDENDUM-2.md", "KP 提案无 file/line/anchor"),
        ErrorSpec("GRAPH_KP_AMBIGUOUS", GRAPH_INTERNAL, "warn", "graph.kp.ambiguous",
                  "S6-ADDENDUM-2.md", "锚点歧义/多候选无法唯一"),
        ErrorSpec("GRAPH_KP_LOW_CONFIDENCE", GRAPH_INTERNAL, "warn", "graph.kp.low_confidence",
                  "S6-ADDENDUM-2.md", "低于阈值，不 apply"),
        ErrorSpec("GRAPH_EDGE_INVALID", GRAPH_INTERNAL, "error", "graph.edge.invalid",
                  "S6-ADDENDUM-2.md", "边 type/direction/字段非法"),
        ErrorSpec("GRAPH_EDGE_DUPLICATE", GRAPH_INTERNAL, "warn", "graph.edge.duplicate",
                  "S6-ADDENDUM-2.md", "同 pair/同 type 重复"),
        ErrorSpec("GRAPH_EDGE_EVIDENCE_MISSING", GRAPH_INTERNAL, "error",
                  "graph.edge.evidence_missing", "S6-ADDENDUM-2.md",
                  "边无 evidence/assertion_source"),
        ErrorSpec("GRAPH_EDGE_SEMANTIC_MISMATCH", GRAPH_INTERNAL, "error",
                  "graph.edge.semantic_mismatch", "S6-ADDENDUM-2.md", "结构/引用边标 semantic"),
        ErrorSpec("GRAPH_CURATION_CONFLICT", GRAPH_INTERNAL, "warn", "graph.curation.conflict",
                  "S6-ADDENDUM-2.md", "冲突未裁决"),
        ErrorSpec("GRAPH_CURATION_APPROVAL_REQUIRED", GRAPH_INTERNAL, "error",
                  "graph.curation.approval_required", "S6-ADDENDUM-2.md", "无人确认即 apply"),
        ErrorSpec("GRAPH_CURATION_PRIVACY_REJECTED", GRAPH_INTERNAL, "error",
                  "graph.curation.privacy_rejected", "S6-ADDENDUM-2.md", "PII/正文边界违规"),
        ErrorSpec("GRAPH_CURATION_BUDGET_EXCEEDED", GRAPH_INTERNAL, "warn",
                  "graph.curation.budget_exceeded", "S6-ADDENDUM-2.md", "提案超预算"),
        ErrorSpec("GRAPH_CURATION_ROLLBACK_FAILED", GRAPH_INTERNAL, "error",
                  "graph.curation.rollback_failed", "S6-ADDENDUM-2.md",
                  "回滚失败，零写入校验失败"),
    ]


def _fallback() -> ErrorSpec:
    return ErrorSpec(GRAPH_INTERNAL, "", "error", "graph.internal", "S6-contract-v1.md",
                     "未知错误 / 契约内部故障的兜底（S6-9：未知 ⇒ GRAPH_INTERNAL）")


#: 全部 canonical 码（含兜底），键 = code。
ERROR_SPECS: dict[str, ErrorSpec] = {
    s.code: s for s in (_s6() + _add1() + _add2() + [_fallback()])
}

#: S6 本体贡献的码（含 S6-3，共 5 个）。
S6_ONLY_CODES: frozenset[str] = frozenset(s.code for s in _s6())

#: ADDENDUM-1 贡献的码（6 个）。
ADDENDUM1_CODES: frozenset[str] = frozenset(s.code for s in _add1())

#: ADDENDUM-2 贡献的码（14 个）。
ADDENDUM2_CODES: frozenset[str] = frozenset(s.code for s in _add2())

#: 全部 legacy 身份（canonical 互作 legacy 目标 + 只作 legacy 的历史码）。
LEGACY_CODES: frozenset[str] = frozenset(
    {s.legacy_code for s in ERROR_SPECS.values() if s.legacy_code}
) | LEGACY_ONLY_CODES


def canonicalize(code: object) -> str:
    """把任意输入折成 **canonical** 码（未知/非字符串 ⇒ ``GRAPH_INTERNAL``）。

    只作 legacy 的历史码（如 ``GRAPH_EDITION_STALE``）**不会**被原样返回 ——
    它们没有 canonical 身份，必须由调用方提供 canonical 码。
    """
    if not isinstance(code, str):
        return GRAPH_INTERNAL
    if code in ERROR_SPECS:
        return code
    return GRAPH_INTERNAL


def spec_for(code: object) -> ErrorSpec:
    """取码的 ``ErrorSpec``；未知 ⇒ 兜底 ``GRAPH_INTERNAL`` 的 spec（绝不抛）。"""
    return ERROR_SPECS.get(canonicalize(code), ERROR_SPECS[GRAPH_INTERNAL])


class GraphError(Exception):
    """携带 ``GRAPH_*`` 身份的异常（B1 起只读模块统一用它 fail-closed）。

    ``audit_id`` 由调用方（B5 的 AuditLog）补齐；B1 阶段允许为空串，
    但 ``to_envelope()`` 会如实反映"是否已有审计身份"，不伪造。
    """

    def __init__(
        self,
        code: object,
        message: str,
        *,
        audit_id: str = "",
        detail: dict | None = None,
    ) -> None:
        self.spec = spec_for(code)
        self.code = self.spec.code
        self.message = str(message)
        self.audit_id = audit_id or ""
        self.detail = dict(detail or {})
        super().__init__(f"{self.code}: {self.message}")

    def to_envelope(self) -> dict:
        """稳定的错误信封（供 UI/agent/审计共用；字段集见 ``schemas/error.json``）。"""
        return {
            "code": self.code,
            "legacy_code": self.spec.legacy_code,
            "severity": self.spec.severity,
            "i18n_key": self.spec.i18n_key,
            "message": self.message,
            "audit_id": self.audit_id,
            "detail": self.detail,
        }


def validate_table() -> list[str]:
    """自检错误表一致性；返回问题列表（空 = 通过）。

    这是**机检**入口：``tests/graph/test_contracts.py`` 既调用它，也独立对冻结文档反查，
    以免"表自己说自己没问题"。
    """
    problems: list[str] = []

    if len(ERROR_SPECS) != len({s.code for s in ERROR_SPECS.values()}):
        problems.append("canonical 码重复")

    for code, spec in ERROR_SPECS.items():
        if code != spec.code:
            problems.append(f"键与 spec.code 不一致：{code} vs {spec.code}")
        if not code.startswith("GRAPH_"):
            problems.append(f"canonical 码必须以 GRAPH_ 开头：{code}")
        if spec.severity not in SEVERITIES:
            problems.append(f"{code} severity 非法：{spec.severity!r}")
        if not spec.i18n_key.startswith("graph."):
            problems.append(f"{code} i18n key 必须以 graph. 开头：{spec.i18n_key!r}")
        if not spec.source.startswith("S6-"):
            problems.append(f"{code} 来源必须是冻结文档：{spec.source!r}")

    # legacy 不得与同名 canonical 冲突地"自我引用"
    for code, spec in ERROR_SPECS.items():
        if spec.legacy_code == code:
            problems.append(f"{code} 的 legacy_code 指向自身")

    if GRAPH_INTERNAL not in ERROR_SPECS:
        problems.append("缺少 GRAPH_INTERNAL 兜底码")

    # 三源计数下限（S6-6 四个 / ADD-1 六个 / ADD-2 十四个）
    if len(ADDENDUM1_CODES) != 6:
        problems.append(f"ADDENDUM-1 码数应为 6，实际 {len(ADDENDUM1_CODES)}")
    if len(ADDENDUM2_CODES) != 14:
        problems.append(f"ADDENDUM-2 码数应为 14，实际 {len(ADDENDUM2_CODES)}")
    if len(S6_ONLY_CODES) < 4:
        problems.append(f"S6 码数应 ≥4，实际 {len(S6_ONLY_CODES)}")

    return problems


def codes_by_source() -> dict[str, tuple[str, ...]]:
    """按冻结来源分组（测试/审计用）。"""
    groups: dict[str, list[str]] = {}
    for spec in ERROR_SPECS.values():
        groups.setdefault(spec.source, []).append(spec.code)
    return {k: tuple(sorted(v)) for k, v in sorted(groups.items())}


def iter_specs() -> Iterable[ErrorSpec]:
    return tuple(ERROR_SPECS.values())
