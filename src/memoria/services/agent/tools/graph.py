"""S7 agent 只读消费：5 个只读工具（冻结依据 `S7-agent-v1.md` + S7a 注记）。

工具面（snake_case，v1 **无 graph_path**）::

    graph_focus           H 层一跳取景（ViewResponse；edges 只含 shown）
    graph_explain_edge    受控解释单条边（含 suppressed/unknown/rule_id/claim_type）
    graph_expand_cluster  一次 drill 的只读 ViewResponse（**不改 S5 nav 状态**）
    graph_summary         SummaryResponse（clusters/counts/data_state/truncated）
    graph_resolve_ref     引用解析（有界 source_excerpt ≤500 字；stale 显式）

只读边界（S7-1/S7-6）：本模块不写 sidecar/registry/cache、不提供写工具；唯一写入是
S7-5 要求的 append-only 审计 ``.memoria/agent/audit/graph/audit.jsonl``。所有工具参数
可选 ``expected_edition``；响应回带 ``edition_sha``/``audit_id``；幂等键
``(tool,args,edition,budget)``（同键同 **结果 payload**；审计仍每次追加 —— append-only）。

G7（S7-12/S8-6）：``G7_EVENT`` 只记 id/anchor 引用/counts，**绝不落正文/excerpt/PII**；
``g7_envelope()`` 生成可被 ``G7Store.assert_g_g7`` 校验的 G7 快照载体。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from memoria.graph.multilevel.admission import (
    AdmissionService,
    assert_semantic_marker_evidence,
    make_frame_spec,
)
from memoria.graph.multilevel.audit import AuditError, AuditLog
from memoria.graph.multilevel.cluster_run import ClusterRunBuilder
from memoria.graph.multilevel.datasource import DataSource, DataSourceReader
from memoria.graph.multilevel.errors import (
    GRAPH_ANCHOR_STALE,
    GRAPH_INTERNAL,
    GRAPH_TOOL_AUDIT_FAILED,
    GRAPH_TOOL_BUDGET_EXCEEDED,
    GRAPH_TOOL_INPUT_INVALID,
    GraphError,
)
from memoria.graph.multilevel.graph_view import GraphViewBuilder, ViewFamily
from memoria.graph.multilevel.view_model import ViewModelBuilder
from memoria.services.agent.tools.registry import Tool, ToolOutput

DEFAULT_MAX_TOKENS = 4000
DEFAULT_MAX_NODES = 200
DEFAULT_MAX_EDGES = 400
TOKENS_PER_CHAR = 0.4237
EXCERPT_LIMIT = 500
TOOL_NAMES: tuple[str, ...] = (
    "graph_focus",
    "graph_explain_edge",
    "graph_expand_cluster",
    "graph_summary",
    "graph_resolve_ref",
)
#: v1 只读工具：任何写语义的名字都不允许出现（机检用）。
WRITE_TOOL_NAMES: tuple[str, ...] = (
    "graph_write", "graph_apply", "graph_curate", "graph_update", "graph_delete",
    "graph_propose", "graph_import",
)
VIEW_FAMILY_ID = "h-default"
LEVEL_ID = "kp"
DIMENSION_ID = "H"


def _canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _sha(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _estimate_tokens(payload: object) -> int:
    return int(len(json.dumps(payload, ensure_ascii=False)) * TOKENS_PER_CHAR) + 8


def _view_family(dimension_id: str) -> ViewFamily:
    return ViewFamily(family_id=VIEW_FAMILY_ID, basis="hierarchy",
                      dimension_id=dimension_id, level_chain=(LEVEL_ID,))


def _json_ok(payload: Mapping) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)


class GraphToolset:
    """一个 KB 的 S7 工具集（只读 + 审计）。可被 agent 工具注册层包装为 `Tool`。"""

    def __init__(
        self,
        kb_path: str | Path,
        *,
        memory_dir: str | Path | None = None,
        audit_filename: str = "audit.jsonl",
        session_id: str = "agent",
    ) -> None:
        self.kb_path = Path(kb_path)
        if not self.kb_path.is_dir():
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"KB 目录不存在：{self.kb_path}")
        self.session_id = session_id
        self._memory_dir = Path(memory_dir) if memory_dir else self.kb_path / ".memoria"
        self._audit = AuditLog(self._memory_dir, filename=audit_filename)
        self._idempotent: dict[str, str] = {}
        self.g7_events: list[dict] = []
        self._datasource: DataSource | None = None
        self._cluster_run_cache = None

    # -- 只读事实 -----------------------------------------------------
    @property
    def datasource(self) -> DataSource:
        if self._datasource is None:
            self._datasource = DataSourceReader(self.kb_path).read()
        return self._datasource

    @property
    def edition_sha(self) -> str:
        return self.datasource.canonical_id

    def _refresh(self) -> None:
        """每次工具调用重新读 edition（S7-9：写入后 edition 变化必须可见）。"""
        self._datasource = DataSourceReader(self.kb_path).read()

    # -- 审计 / 幂等 ---------------------------------------------------
    def _audit_call(self, tool: str, args: Mapping, *, edition: str, tokens: int,
                    refs: int, unknown: int, truncated: bool,
                    decision: str = "ok", error_code: str | None = None,
                    audit_id: str | None = None) -> str:
        detail = {
            "tool": tool,
            "args_sha": _sha(dict(args)),
            "edition": edition,
            "budget": {"max_tokens": args.get("max_tokens"), "max_nodes": args.get("max_nodes")},
            "tokens": int(tokens),
            "refs": int(refs),
            "unknown": int(unknown),
            "truncated": bool(truncated),
            "write_attempts": 0,
            "read_only": True,
        }
        if error_code:
            detail["error_code"] = error_code
        try:
            record = self._audit.append(
                kind="graph_tool_call", actor=self.session_id, ref=tool,
                decision=decision, detail=detail,
            )
        except AuditError as exc:  # pragma: no cover - 由测试注入 audit 失败
            raise GraphError(GRAPH_TOOL_AUDIT_FAILED, f"工具审计失败：{exc}") from exc
        return record.audit_id

    def _idempotency_key(self, tool: str, args: Mapping) -> str:
        return _sha({"tool": tool, "args": dict(args),
                     "edition": self.edition_sha,
                     "budget": {"max_tokens": args.get("max_tokens"),
                                "max_nodes": args.get("max_nodes")}})

    def _g7_event(self, tool: str, args: Mapping, *, tokens: int, refs: int,
                  unknown: int, truncated: bool, edition: str,
                  frame_id: str | None, run_id: str | None,
                  error_code: str | None) -> None:
        self.g7_events.append({
            "tool": tool,
            "tokens": int(tokens),
            "refs": int(refs),
            "unknown": int(unknown),
            "truncated": bool(truncated),
            "edition": edition,
            "frame_id": frame_id,
            "run_id": run_id,
            "write_attempts": 0,
            "read_only": True,
            "error_code": error_code,
        })

    def g7_envelope(self, *, data_source_sha: str | None = None,
                    run_ids: Sequence[str] = (), frame_ids: Sequence[str] = ()) -> dict:
        """由累计的 G7_EVENT 生成 G7 快照载体（只计数/引用；无正文）。"""
        events = self.g7_events
        return {
            "g7_version": 1,
            "data_source_sha": data_source_sha or self.edition_sha,
            "run_ids": sorted({str(r) for r in run_ids}),
            "frame_ids": sorted({str(f) for f in frame_ids}),
            "tool_calls": len(events),
            "tokens": sum(int(e["tokens"]) for e in events),
            "write_attempts": sum(int(e["write_attempts"]) for e in events),
            "read_only_ratio": 1.0 if events else 1.0,
            "reference_completeness": (
                sum(1 for e in events if e["refs"] > 0) / len(events) if events else 1.0
            ),
            "unknown_ratio": (
                sum(1 for e in events if e["unknown"] > 0) / len(events) if events else 0.0
            ),
            "degraded_count": sum(1 for e in events if e["error_code"]),
        }

    # -- 入口包装 ------------------------------------------------------
    def _run(self, tool: str, args: Mapping, fn) -> ToolOutput:  # noqa: ANN001
        args = dict(args or {})
        try:
            edition = self._refresh() or self.edition_sha
        except GraphError as exc:
            return self._error_output(tool, args, exc, edition="")
        key = self._idempotency_key(tool, args)
        cached = self._idempotent.get(key)
        try:
            payload = fn(args)
            if cached is not None:
                payload = json.loads(cached)
            body = _json_ok(payload)
            tokens = _estimate_tokens(payload)
            refs = int(payload.get("refs_count") or len(
                payload.get("edges") or payload.get("candidates") or ()) or 0)
            unknown = int(payload.get("unknown_count") or 0)
            truncated = bool(payload.get("truncated"))
            audit_id = self._audit_call(tool, args, edition=payload.get("edition_sha", edition),
                                       tokens=tokens, refs=refs, unknown=unknown,
                                       truncated=truncated)
            payload["audit_id"] = audit_id
            body = _json_ok(payload)
            self._idempotent.setdefault(key, _json_ok(
                {k: v for k, v in payload.items() if k != "audit_id"}))
            self._g7_event(tool, args, tokens=tokens, refs=refs, unknown=unknown,
                           truncated=truncated, edition=payload.get("edition_sha", edition),
                           frame_id=payload.get("frame_id"),
                           run_id=payload.get("run_id"), error_code=None)
            return ToolOutput(text=body, meta={"tool": tool, "audit_id": audit_id,
                                               "idempotency_key": key})
        except GraphError as exc:
            return self._error_output(tool, args, exc, edition=edition, key=key)

    def _error_output(self, tool: str, args: Mapping, exc: GraphError, *,
                      edition: str, key: str | None = None) -> ToolOutput:
        envelope = exc.to_envelope()
        try:
            audit_id = self._audit_call(tool, args, edition=edition, tokens=0, refs=0,
                                       unknown=0, truncated=False,
                                       decision="error", error_code=exc.code)
        except GraphError:
            audit_id = ""
        envelope["audit_id"] = envelope.get("audit_id") or audit_id
        envelope["edition_sha"] = edition
        self._g7_event(tool, args, tokens=0, refs=0, unknown=1, truncated=False,
                       edition=edition, frame_id=None, run_id=None, error_code=exc.code)
        return ToolOutput(text=_json_ok(envelope), error=True, code=exc.code)

    # -- 公共校验 ------------------------------------------------------
    @staticmethod
    def _require(args: Mapping, name: str) -> str:
        value = args.get(name)
        if not isinstance(value, str) or not value.strip():
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"缺少/非法参数 {name}")
        return value.strip()

    @staticmethod
    def _budget(args: Mapping) -> tuple[int, int, int]:
        max_tokens = args.get("max_tokens", DEFAULT_MAX_TOKENS)
        max_nodes = args.get("max_nodes", DEFAULT_MAX_NODES)
        max_edges = args.get("max_edges", DEFAULT_MAX_EDGES)
        for name, value in (("max_tokens", max_tokens), ("max_nodes", max_nodes),
                            ("max_edges", max_edges)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"{name} 必须是 ≥1 整数")
        return int(max_tokens), min(int(max_nodes), DEFAULT_MAX_NODES), \
            min(int(max_edges), DEFAULT_MAX_EDGES)

    def _check_dimension(self, args: Mapping) -> str:
        dimension = str(args.get("dimension") or DIMENSION_ID)
        if dimension != DIMENSION_ID:
            raise GraphError(
                GRAPH_TOOL_INPUT_INVALID,
                f"v1 仅支持 dimension=H（A 维度需 S1 registry，B6 未做）：{dimension}",
                detail={"dimension": dimension},
            )
        return dimension

    def _check_edition(self, args: Mapping) -> str:
        expected = args.get("expected_edition")
        current = self.edition_sha
        if expected is not None and str(expected) != current:
            raise GraphError(
                GRAPH_ANCHOR_STALE,
                "expected_edition 与当前 edition 不一致（需刷新）",
                detail={"expected_edition": str(expected), "edition_sha": current,
                        "legacy_code": "GRAPH_EDITION_STALE"},
            )
        return current

    def _frame(self, focus: str, dimension_id: str, *, max_nodes: int,
               max_edges: int, hop: int = 1):
        return make_frame_spec(level=LEVEL_ID, view_family=VIEW_FAMILY_ID,
                               dimension_id=dimension_id, focus=focus, hop=hop,
                               max_nodes=max_nodes, max_edges=max_edges)

    def _view(self, dimension_id: str = DIMENSION_ID):
        return GraphViewBuilder().build(self.datasource, level=LEVEL_ID,
                                        view_family=_view_family(dimension_id))

    def _cluster_run(self):
        if self._cluster_run_cache is None:
            run = ClusterRunBuilder().build(
                self.datasource, level_id=LEVEL_ID, view_family_id=VIEW_FAMILY_ID,
                corpus_manifest_sha=self.datasource.canonical_id,
            )
            self._cluster_run_cache = run
        return self._cluster_run_cache

    # -- 工具 1：focus --------------------------------------------------
    def focus(self, args: Mapping) -> dict:
        focus = self._require(args, "focus")
        dimension = self._check_dimension(args)
        max_tokens, max_nodes, max_edges = self._budget(args)
        edition = self._check_edition(args)
        view = self._view(dimension)
        kp_ids = {str(n["id"]) for n in view.nodes}
        if focus not in kp_ids:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             f"focus {focus!r} 不在 KP 层（可用 graph_summary 先看概览）")
        frame = self._frame(focus, dimension, max_nodes=max_nodes, max_edges=max_edges)
        result = AdmissionService().admit(
            frame_spec=frame, graph_view=view, datasource=self.datasource,
            relation_sources=None,
        )
        vm = ViewModelBuilder().build(result)
        shown_edges = [dict(e) for e in vm["edges"] if e.get("presence") == "shown"]
        counts = result.counts()
        clusters: list[dict] = []
        try:
            run = self._cluster_run()
            clusters = [
                {
                    "cluster_id": str(c.get("cluster_id")),
                    "run_id": run.run_id,
                    "cluster_key": str(c.get("cluster_key")),
                    "label": f"cluster-{c.get('local_seq')}",
                    "member_count": int(c.get("size") or 0),
                    "coverage": round(float(c.get("size") or 0) /
                                      max(1, len(self.datasource.kps)), 6),
                }
                for c in run.clusters if focus in (c.get("members") or ())
            ]
            clusters.sort(key=lambda c: c["cluster_id"])
        except GraphError:
            clusters = []
        payload = {
            "kb_id": str(args.get("kb_id") or self.kb_path.name),
            "level_id": LEVEL_ID,
            "view_family_id": VIEW_FAMILY_ID,
            "dimension_id": dimension,
            "focus": focus,
            "data_state": view.data_state,
            "nodes": [dict(n) for n in vm["nodes"]],
            "edges": shown_edges,
            "clusters": clusters,
            "suppressed_count": counts["suppressed"],
            "unknown_count": counts["unknown"],
            "suppressed_summary": result.suppressed_summary(),
            "rule_histogram": dict(result.rule_histogram),
            "truncated": False,
            "omitted": {"nodes": 0, "edges": 0},
            "frame_id": frame.canonical_sha(),
            "edition_sha": edition,
            "meta": {"max_tokens": max_tokens, "max_nodes": max_nodes,
                     "max_edges": max_edges, "hop": 1,
                     "edition_source": ("expected" if args.get("expected_edition")
                                        else "current")},
        }
        payload["refs_count"] = len(payload["nodes"]) + len(shown_edges)
        return self._fit_budget(payload, max_tokens)

    # -- 工具 2：explain_edge ------------------------------------------
    def explain_edge(self, args: Mapping) -> dict:
        edge_id = self._require(args, "edge_id")
        edition = self._check_edition(args)
        parts = edge_id.split("|")
        if len(parts) != 3:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             "edge_id 形如 type|source_id|target_id")
        etype, source, target = parts
        matched = [
            e for e in self.datasource.edges
            if str(e.get("type")) == etype and str(e.get("source_id")) == source
            and target in [str(t) for t in e.get("targets") or ()]
        ]
        if not matched:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"找不到边：{edge_id}")
        assert_semantic_marker_evidence(matched)
        semantic = any(str(e.get("contain_kind") or "") == "semantic"
                       or str(e.get("label") or "") == "semantic" for e in matched)
        kp_ids = {str(k.get("id")) for k in self.datasource.kps}
        presence = "shown"
        rule_id = None
        if source not in kp_ids or target not in kp_ids:
            presence = "unknown"
            rule_id = "endpoint.unresolved"
        else:
            view = self._view()
            frame = self._frame(source, DIMENSION_ID, max_nodes=DEFAULT_MAX_NODES,
                                max_edges=DEFAULT_MAX_EDGES)
            result = AdmissionService().admit(frame_spec=frame, graph_view=view,
                                              datasource=self.datasource)
            record = next((e for e in result.edges if e.get("id") == edge_id), None)
            if record is not None:
                presence = record.get("presence") or "unknown"
                rule_id = record.get("rule_id")
            else:
                presence = "unknown"
                rule_id = "admission.undecided"
        source_refs = []
        for e in matched:
            src = e.get("assertion_source")
            if isinstance(src, Mapping):
                source_refs.append({"file": src.get("file"),
                                    "line_start": src.get("line_start"),
                                    "line_end": src.get("line_end")})
        alternate_frames = []
        for alt_focus in (source, target):
            if alt_focus not in kp_ids or alt_focus == source and alternate_frames:
                continue
            try:
                alt_view = self._view()
                alt_frame = self._frame(alt_focus, DIMENSION_ID,
                                        max_nodes=DEFAULT_MAX_NODES,
                                        max_edges=DEFAULT_MAX_EDGES)
                alt_result = AdmissionService().admit(
                    frame_spec=alt_frame, graph_view=alt_view,
                    datasource=self.datasource)
            except GraphError:
                continue
            alt_record = next((e for e in alt_result.edges
                               if e.get("id") == edge_id), None)
            alternate_frames.append({
                "focus": alt_focus,
                "presence": (alt_record or {}).get("presence"),
                "rule_id": (alt_record or {}).get("rule_id"),
            })
        explanation = {
            "semantic": semantic,
            "relation_class": "semantic" if semantic else "structural",
            "reason": ("语义边（来自 E_sem；不参与结构伪边）" if semantic
                       else "结构/引用边：语义贡献=0（S9-4）"),
        }
        return {
            "kb_id": str(args.get("kb_id") or self.kb_path.name),
            "edge_id": edge_id,
            "type": etype,
            "source_id": source,
            "targets": [target],
            "presence": presence,
            "rule_id": rule_id,
            "relation_class": explanation["relation_class"],
            "claim_type": "graph_relation",
            "source_refs": source_refs,
            "alternate_frames": alternate_frames,
            "explanation": explanation,
            "edition_sha": edition,
            "refs_count": 1,
            "truncated": False,
        }

    # -- 工具 3：expand_cluster -----------------------------------------
    def expand_cluster(self, args: Mapping) -> dict:
        cluster_id = self._require(args, "cluster_id")
        edition = self._check_edition(args)
        run = self._cluster_run()
        cluster = next((c for c in run.clusters if str(c.get("cluster_id")) == cluster_id), None)
        if cluster is None:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             f"cluster_id 不存在：{cluster_id}（run={run.run_id}）")
        members = sorted(str(m) for m in cluster.get("members") or ())
        member_set = set(members)
        edge_rows = []
        for e in self.datasource.edges:
            src = str(e.get("source_id"))
            targets = [str(t) for t in e.get("targets") or ()]
            if src in member_set or any(t in member_set for t in targets):
                edge_rows.append({"type": str(e.get("type")), "source_id": src,
                                  "targets": targets})
        edge_rows.sort(key=lambda e: (e["type"], e["source_id"], tuple(e["targets"])))
        return {
            "kb_id": str(args.get("kb_id") or self.kb_path.name),
            "cluster_id": cluster_id,
            "run_id": run.run_id,
            "cluster_key": cluster.get("cluster_key"),
            "level_id": LEVEL_ID,
            "dimension_id": DIMENSION_ID,
            "data_state": "ok" if run.status == "ok" else "empty_nosemantic",
            "members": members,
            "nodes": [{"id": m, "kind": "kp", "presence": "shown"} for m in members],
            "edges": edge_rows,
            "nav_unchanged": True,
            "truncated": False,
            "edition_sha": edition,
            "refs_count": len(members) + len(edge_rows),
        }

    # -- 工具 4：summary ------------------------------------------------
    def summary(self, args: Mapping) -> dict:
        edition = self._check_edition(args)
        dimension = self._check_dimension(args)
        ds = self.datasource
        run = self._cluster_run()
        clusters = [
            {
                "cluster_id": str(c.get("cluster_id")),
                "run_id": run.run_id,
                "cluster_key": str(c.get("cluster_key")),
                "label": f"cluster-{c.get('local_seq')}",
                "member_count": int(c.get("size") or 0),
                "coverage": round(float(c.get("size") or 0) / max(1, len(ds.kps)), 6),
            }
            for c in run.clusters
        ]
        clusters.sort(key=lambda c: c["cluster_id"])
        return {
            "kb_id": str(args.get("kb_id") or self.kb_path.name),
            "dimension_id": dimension,
            "data_state": "ok" if run.status == "ok" else "empty_nosemantic",
            "clusters": clusters,
            "counts": {
                "kps": len(ds.kps),
                "edges": len(ds.edges),
                "semantic_edges": sum(
                    1 for e in ds.edges
                    if str(e.get("contain_kind") or "") == "semantic"),
                "clusters": len(clusters),
                "suppressed": 0,
                "unknown": 0,
            },
            "suppressed_summary": {},
            "rule_histogram": {},
            "truncated": False,
            "edition_sha": edition,
            "refs_count": len(clusters),
            "run_id": run.run_id,
        }

    # -- 工具 5：resolve_ref -------------------------------------------
    def resolve_ref(self, args: Mapping) -> dict:
        edition = self._check_edition(args)
        kp_id = args.get("kp_id")
        file_rel = args.get("file")
        line = args.get("line")
        anchor = args.get("anchor")
        if anchor is not None:
            if isinstance(anchor, Mapping):
                file_rel = anchor.get("file")
                line = anchor.get("line")
            elif isinstance(anchor, str) and ":" in anchor:
                file_rel, _, raw_line = anchor.rpartition(":")
                try:
                    line = int(raw_line)
                except ValueError:
                    line = None
        if kp_id is not None:
            kp = next((k for k in self.datasource.kps if str(k.get("id")) == str(kp_id)), None)
            if kp is None:
                return self._resolve_payload(
                    args, edition, resolved=False, code=GRAPH_ANCHOR_STALE,
                    detail={"reason": "kp 不存在（可能已迁移/重切）", "kp_id": str(kp_id)},
                )
            if not kp.get("range_ok", True):
                return self._resolve_payload(
                    args, edition, resolved=False, code=GRAPH_ANCHOR_STALE,
                    detail={"reason": "kp range 解析失败（range_ok=false）",
                            "kp_id": str(kp_id)},
                )
            file_rel = kp.get("file")
            line = kp.get("start_line")
        if not isinstance(file_rel, str) or not file_rel:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             "需要 kp_id，或 file+line，或 anchor{file,line}")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, "line 必须是 ≥1 整数")
        target = (self.kb_path / file_rel).resolve()
        root = self.kb_path.resolve()
        if root not in target.parents and target != root:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, "file 越界（必须在 KB 内）")
        if not target.is_file():
            return self._resolve_payload(args, edition, resolved=False,
                                         code=GRAPH_ANCHOR_STALE,
                                         detail={"reason": "file 不存在", "file": file_rel})
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if line > len(lines):
            return self._resolve_payload(args, edition, resolved=False,
                                         code=GRAPH_ANCHOR_STALE,
                                         detail={"reason": "line 越界", "file": file_rel,
                                                 "line": line, "total_lines": len(lines)})
        matched_kp = next((k for k in self.datasource.kps
                           if str(k.get("file")) == file_rel
                           and isinstance(k.get("start_line"), int)
                           and k.get("start_line") <= line
                           and isinstance(k.get("end_line"), int)
                           and line <= k.get("end_line")), None)
        excerpt_lines = lines[line - 1: line - 1 + 6]
        excerpt = "\n".join(excerpt_lines)
        if len(excerpt) > EXCERPT_LIMIT:
            excerpt = excerpt[:EXCERPT_LIMIT]
        hard_stale = matched_kp is None
        return self._resolve_payload(
            args, edition, resolved=True, code=GRAPH_ANCHOR_STALE if hard_stale else None,
            detail={
                "kp_id": str(matched_kp.get("id")) if matched_kp else None,
                "file": file_rel,
                "line": line,
                "total_lines": len(lines),
                "stale": hard_stale,
                "anchor_verified": not hard_stale,
            },
            excerpt=excerpt,
        )

    def _resolve_payload(self, args: Mapping, edition: str, *, resolved: bool,
                         code: str | None, detail: Mapping,
                         excerpt: str | None = None) -> dict:
        payload = {
            "kb_id": str(args.get("kb_id") or self.kb_path.name),
            "resolved": bool(resolved),
            "code": code,
            "detail": dict(detail),
            "edition_sha": edition,
            "refs_count": 1,
            "truncated": False,
        }
        if excerpt is not None:
            payload["source_excerpt"] = excerpt
            payload["excerpt_limit"] = EXCERPT_LIMIT
        return payload

    # -- 预算 -----------------------------------------------------------
    def _fit_budget(self, payload: dict, max_tokens: int) -> dict:
        if _estimate_tokens(payload) <= max_tokens:
            return payload
        payload["truncated"] = True
        omitted_nodes = 0
        omitted_edges = 0
        while _estimate_tokens(payload) > max_tokens and payload["edges"]:
            payload["edges"] = payload["edges"][:-1]
            omitted_edges += 1
        while _estimate_tokens(payload) > max_tokens and payload["nodes"]:
            payload["nodes"] = payload["nodes"][:-1]
            omitted_nodes += 1
        payload["omitted"] = {"nodes": omitted_nodes, "edges": omitted_edges}
        if _estimate_tokens(payload) > max_tokens:
            raise GraphError(GRAPH_TOOL_BUDGET_EXCEEDED,
                             "连 summary 级响应都超过 max_tokens")
        return payload

    # -- Tool 包装 ------------------------------------------------------
    def tools(self) -> tuple[Tool, ...]:
        return (
            self._tool("graph_focus", "只读取景：以 focus KP 为中心的一跳视图（edges 只含 shown；suppressed/unknown 只给 counts+summary）。",
                       {"focus": {"type": "string"}, "dimension": {"type": "string"},
                        "expected_edition": {"type": "string"},
                        "max_tokens": {"type": "integer"}, "max_nodes": {"type": "integer"},
                        "max_edges": {"type": "integer"}},
                       ["focus"], self.focus, read_only=True),
            self._tool("graph_explain_edge", "受控解释单条边（presence/rule_id/claim_type/source_refs；不返回正文）。",
                       {"edge_id": {"type": "string"},
                        "expected_edition": {"type": "string"}},
                       ["edge_id"], self.explain_edge, read_only=True),
            self._tool("graph_expand_cluster", "一次 drill 的只读簇视图；不改导航（nav_unchanged=true）。",
                       {"cluster_id": {"type": "string"},
                        "expected_edition": {"type": "string"}},
                       ["cluster_id"], self.expand_cluster, read_only=True),
            self._tool("graph_summary", "只读摘要：簇/counts/data_state/truncated。",
                       {"dimension": {"type": "string"},
                        "expected_edition": {"type": "string"}},
                       [], self.summary, read_only=True),
            self._tool("graph_resolve_ref", "引用解析：kp_id 或 file+line 或 anchor；source_excerpt ≤500 字。",
                       {"kp_id": {"type": "string"}, "file": {"type": "string"},
                        "line": {"type": "integer"}, "anchor": {"type": "object"},
                        "expected_edition": {"type": "string"}},
                       [], self.resolve_ref, read_only=True),
        )

    def _tool(self, name: str, description: str, properties: Mapping,
              required: Sequence[str], handler, *, read_only: bool) -> Tool:
        params = {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                **{k: v for k, v in properties.items()},
            },
            "required": ["kb_id", *required],
            "additionalProperties": False,
        }
        return Tool(name=name, description=description, parameters=params,
                    handler=lambda arguments: self._run(
                        name, arguments,
                        lambda a: handler(self._with_kb_id(a))),
                    read_only=read_only)

    def _with_kb_id(self, args: Mapping) -> Mapping:
        out = dict(args)
        out.setdefault("kb_id", self.kb_path.name)
        return out


def make_graph_tools(kb_path: str | Path, **kwargs: Any) -> list[Tool]:
    """工厂：给 agent 工具注册层使用（B6 只交付出口，不改既有 kb.py 注册点）。"""
    return list(GraphToolset(kb_path, **kwargs).tools())
