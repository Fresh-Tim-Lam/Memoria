"""I-01 `DataSourceReader`：事实的**只读投影**（nodes / edges / ``E_relation_min``）。

## 单一真源与只读（S6-1、S6-2）

- 事实**只**来自 `.md` 正文 + `.memoria/sidecars/**` + `.memoria/manifest.yaml`（**只读**）。
- 本模块输出 ``DataSource`` 是**派生投影**，不是事实；不缓存、不落盘。
- **D-3：绝不写 sidecar**。``read()`` 全程套在 :func:`read_only_guard` 里：
  KB 内任何文件被新增/删除/改内容 ⇒ 抛 ``GRAPH_WRITE_FORBIDDEN``（不是警告，是失败）。

## 复用既有只读能力（不重复造）

节点/边的几何派生已由 ``memoria.graph.collector.collect_graph_data`` 实现（只读：
``load_sidecar_for_md`` + ``build_kp_index``，实测读写前后 KB 零变化）。
本模块只做三件事：① 套 D-3 守卫；② 归一成契约形状（``kind="kp"``）；③ 用 I-13 校验。

## ``E_relation_min``（S0-3 R-1，冻结）

``{contain(structural), contain(semantic), reference, extend}`` —— **只能加不能删**；
``semantic/structural`` 只是标签，不是 ``e_relation`` 过滤条件。边的 ``type`` 字段
只允许 ``contain/reference/extend`` 三种基础类型（见 ``schemas/edge.json``）。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from memoria.graph.multilevel.errors import GRAPH_INTERNAL, GRAPH_WRITE_FORBIDDEN, GraphError
from memoria.graph.multilevel.schema import assert_contract_bindings, validate_or_raise

#: S0-3 R-1 冻结的 ``E_relation_min``。**顺序固定**（写入 canonical_id，不可随意重排）。
E_RELATION_MIN: tuple[str, ...] = (
    "contain(structural)",
    "contain(semantic)",
    "reference",
    "extend",
)

#: DataSource 的两种状态（S6-2 的 data_state 同名字面量）。
STATUS_OK = "ok"
STATUS_EMPTY_NOSEMANTIC = "empty_nosemantic"

#: 归一后节点允许的 kind（S6-2）。
NODE_KINDS: tuple[str, ...] = ("kp", "cluster")

#: 参与 sha 快照的 KB 内文件后缀/名字（事实源 + 派生缓存都算"被写"，宁可严格）。
_SNAPSHOT_ALL = True


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_kb(kb_path: str | Path) -> dict[str, str]:
    """对 KB 全树做 ``{相对路径: sha256}`` 快照（用于 D-3 前后比对）。

    只读：只打开文件读取，不创建任何临时文件。
    """
    root = Path(kb_path)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:  # pragma: no cover - rglob 结果必在 root 下
            continue
        out[rel] = _sha256_file(path)
    return out


#: **事实源**路径判定（S6-1 / AGENTS.md §1）。
#: 只有这三类才是"事实"：``*.md`` 正文、``.memoria/sidecars/**``、``.memoria/manifest.yaml``。
#: ``.memoria/cache/**``（含 embeddings/undo-debug.log）、``.memoria/pending.json`` 等属
#: **可再生缓存/队列**，不是事实源 ⇒ 后台线程写它们**不构成 D-3 违规**。
_FACT_SIDECAR_PREFIX = ".memoria/sidecars/"
_FACT_MANIFEST = ".memoria/manifest.yaml"


def is_fact_path(rel_path: str) -> bool:
    """该相对路径是否属于**事实源**（D-3 只保护这一范围）。

    ⚠️ 注意：不能用 ``str.lstrip("./")`` —— 那是**字符集**剥离，会把 ``.memoria`` 的
    前导点也吃掉（本仓库踩过这个坑）。这里按**前缀**逐次剥离。
    """
    rel = rel_path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if rel == _FACT_MANIFEST:
        return True
    if rel.startswith(_FACT_SIDECAR_PREFIX):
        return True
    return rel.endswith(".md")


def snapshot_facts(kb_path: str | Path) -> dict[str, str]:
    """**只**对事实源做 ``{相对路径: sha256}`` 快照（D-3 守卫的默认比较域）。

    为什么不全树：实测应用有后台任务在 `.memoria/cache/**`（embeddings 索引、
    undo-debug.log）和 `.memoria/pending.json` 上写 —— 那些是派生/队列，不是事实；
    全树比对会把它们误判成 D-3 违规（B4.1 实测 RPC 12 次里 4 次假失败）。
    """
    return {rel: sha for rel, sha in snapshot_kb(kb_path).items() if is_fact_path(rel)}


def detect_writes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """比对两份快照，返回人类可读的写痕迹（空 = 未写）。"""
    problems: list[str] = []
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in before if k in after and before[k] != after[k])
    if added:
        problems.append(f"新增文件 {added[:5]}{'…' if len(added) > 5 else ''}")
    if removed:
        problems.append(f"删除文件 {removed[:5]}{'…' if len(removed) > 5 else ''}")
    if changed:
        problems.append(f"修改文件 {changed[:5]}{'…' if len(changed) > 5 else ''}")
    return problems


GUARD_SCOPES = ("facts", "all")


@contextlib.contextmanager
def read_only_guard(kb_path: str | Path, *, scope: str = "facts") -> Iterator[None]:
    """D-3 守卫：代码块内若**事实源**被写，退出时抛 ``GRAPH_WRITE_FORBIDDEN``。

    :param scope: ``"facts"``（默认，S6-1 口径：md + sidecars + manifest）或
        ``"all"``（全树；仅用于离线的强断言场景，在线读取会被后台缓存写误报）。

    D-3 的本意是"**读取者不得写 sidecar / 事实**"，不是"整个 KB 目录冻结"；
    因此默认只监视事实源（见 :func:`snapshot_facts` 的实测说明）。
    """
    if scope not in GUARD_SCOPES:
        raise GraphError(GRAPH_INTERNAL, f"未知 guard scope：{scope!r}",
                         detail={"allowed": list(GUARD_SCOPES)})
    snap = snapshot_facts if scope == "facts" else snapshot_kb
    before = snap(kb_path)
    try:
        yield
    except BaseException:
        # 主体已失败：仍要如实报告"期间是否发生写"（不掩盖原异常，附加为 detail）
        problems = detect_writes(before, snap(kb_path))
        if problems:
            raise GraphError(
                GRAPH_WRITE_FORBIDDEN,
                "只读读取期间事实源被写入（D-3 违规，且主体已失败）",
                detail={"kb_path": str(kb_path), "scope": scope, "writes": problems},
            ) from None
        raise
    problems = detect_writes(before, snap(kb_path))
    if problems:
        raise GraphError(
            GRAPH_WRITE_FORBIDDEN,
            "只读读取期间事实源被写入（D-3：禁止写 sidecar / 事实源）",
            detail={"kb_path": str(kb_path), "scope": scope, "writes": problems},
        )


@dataclass(frozen=True)
class DataSource:
    """DataSource 只读投影（``schemas/datasource.json`` 的稳定形状）。"""

    status: str
    canonical_id: str
    e_relation_min: tuple[str, ...]
    kps: tuple[dict, ...]
    edges: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "canonical_id": self.canonical_id,
            "e_relation_min": list(self.e_relation_min),
            "kps": [dict(k) for k in self.kps],
            "edges": [dict(e) for e in self.edges],
        }


def canonical_bytes(payload: object) -> bytes:
    """规范化字节：键排序 + 无空格 + 单个结尾 LF + UTF-8（跨平台可复算）。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


class DataSourceReader:
    """读取一个 KB 的只读投影。

    :param kb_path: 知识库根目录（含 ``.memoria/``）
    :param contract_guard: 是否在读取前校验契约 sha 绑定（默认 True；测试可关以隔离）
    """

    def __init__(self, kb_path: str | Path, *, contract_guard: bool = True) -> None:
        self.kb_path = Path(kb_path)
        self.contract_guard = contract_guard

    # ── 读取 ────────────────────────────────────────────────────────
    def read(self) -> DataSource:
        """只读读取；D-3 守卫 + 契约绑定 + schema fail-closed 校验。"""
        if not self.kb_path.is_dir():
            raise GraphError(GRAPH_INTERNAL, f"KB 目录不存在：{self.kb_path}",
                             detail={"kb_path": str(self.kb_path)})
        if self.contract_guard:
            assert_contract_bindings()
        with read_only_guard(self.kb_path):
            raw = self._collect_raw()
            ds = self._normalize(raw)
            self._validate(ds)
        return ds

    def _collect_raw(self) -> dict:
        """真正的读（可被测试替换以注入写操作，验证 D-3 守卫有效）。"""
        from memoria.graph.collector import collect_graph_data

        return collect_graph_data(str(self.kb_path))

    # ── 归一 ────────────────────────────────────────────────────────
    def _normalize(self, raw: dict) -> DataSource:
        manifest_sha = self._manifest_sha()
        kps = tuple(self._norm_kp(n) for n in raw.get("nodes") or [])
        edges = tuple(self._norm_edge(e) for e in raw.get("edges") or [])
        status = STATUS_OK if (kps and edges) else STATUS_EMPTY_NOSEMANTIC
        canonical_id = _sha256_bytes(canonical_bytes({
            "e_relation_min": list(E_RELATION_MIN),
            "manifest_sha": manifest_sha,
            "kps": sorted(
                ({k: v for k, v in kp.items() if v is not None} for kp in kps),
                key=lambda d: str(d.get("id")),
            ),
            "edges": sorted(
                ({k: v for k, v in e.items() if v is not None} for e in edges),
                key=lambda d: (str(d.get("type")), str(d.get("source_id")),
                               tuple(d.get("targets") or ())),
            ),
        }))
        return DataSource(
            status=status,
            canonical_id=canonical_id,
            e_relation_min=E_RELATION_MIN,
            kps=kps,
            edges=edges,
        )

    @staticmethod
    def _norm_kp(node: dict) -> dict:
        """collector 节点 → 契约节点（``kind="kp"``，字段取白名单，None 归一为缺省）。"""
        kp = {
            "id": str(node.get("id") or ""),
            "kind": "kp",
        }
        for key in ("name", "label", "description", "file"):
            if node.get(key) is not None:
                kp[key] = str(node[key])
        if "range_ok" in node:
            kp["range_ok"] = bool(node["range_ok"])
        for key in ("start_line", "end_line"):
            if isinstance(node.get(key), int) and not isinstance(node.get(key), bool):
                kp[key] = node[key]
        return kp

    @staticmethod
    def _norm_edge(edge: dict) -> dict:
        """collector 边 → 契约边（只保留白名单键；``line`` 仅在有值时出现）。"""
        out: dict = {
            "type": str(edge.get("type") or ""),
            "source_id": str(edge.get("source_id") or ""),
            "targets": [str(t) for t in (edge.get("targets") or [])],
        }
        if isinstance(edge.get("relevance"), (int, float)) and not isinstance(edge["relevance"], bool):
            out["relevance"] = float(edge["relevance"])
        if "derived" in edge:
            out["derived"] = bool(edge["derived"])
        if edge.get("origin") is not None:
            out["origin"] = str(edge["origin"])
        if edge.get("file") is not None:
            out["file"] = str(edge["file"])
        if isinstance(edge.get("line"), int) and not isinstance(edge["line"], bool):
            out["line"] = edge["line"]
        if "no_build" in edge:
            out["no_build"] = bool(edge["no_build"])
        if edge.get("derived_by") is not None:
            out["derived_by"] = str(edge["derived_by"])
        # R-B2-3 / task-354：语义标记与策展身份必须**透传**（否则 E_sem 无法从
        # DataSource 派生，B3 Admission 会漏语义边）。形状对齐 S0-1 G_sem。
        if edge.get("contain_kind") is not None:
            out["contain_kind"] = str(edge["contain_kind"])
        if isinstance(edge.get("assertion_source"), dict):
            out["assertion_source"] = dict(edge["assertion_source"])
        if edge.get("curated_by") is not None:
            out["curated_by"] = str(edge["curated_by"])
        if edge.get("curated_at") is not None:
            out["curated_at"] = str(edge["curated_at"])
        return out

    def _manifest_sha(self) -> str:
        """``.memoria/manifest.yaml`` 的 sha（无则空串）；只读。"""
        path = self.kb_path / ".memoria" / "manifest.yaml"
        if not path.is_file():
            return ""
        return _sha256_file(path)

    # ── 校验（I-13，fail-closed）────────────────────────────────────
    @staticmethod
    def _validate(ds: DataSource) -> None:
        for kp in ds.kps:
            validate_or_raise(kp, "kp")
        for edge in ds.edges:
            validate_or_raise(edge, "edge")
        validate_or_raise(ds.to_dict(), "datasource")
