"""S9 派生检索索引（只读事实 → 可重建缓存；S9-3/S9-11）。

事实源：``DataSource``（B1，只读投影）。派生索引**只**写入
``{kb}/.memoria/cache/graph/retrieval/<edition>.json``（S9-3 唯一 cache 域），
可删除重建；不写 sidecar/registry（S6-1/D-3）。

索引内容（v1，确定性）::

    entries[]        kp / file / anchor 三类候选（candidate_ref 唯一）
    semantic_edges[] 仅 contain_kind=="semantic" 的边（graph 召回用；结构/引用贡献=0）
    metadata          edition/data_source_sha/rebuildable/model_id/dim/license

为什么不放 cluster：cluster 依赖 run（edition 内可选派生），由 retriever 在请求时
按需生成（S9-8：id 对齐 run_id/cluster_key），避免索引与 run 产生第二事实源。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from memoria.graph.multilevel.datasource import DataSource, DataSourceReader
from memoria.graph.multilevel.errors import (
    GRAPH_INTERNAL,
    GRAPH_RETRIEVAL_UNAVAILABLE,
    GRAPH_TOOL_INPUT_INVALID,
    GraphError,
)

INDEX_VERSION = 1
CACHE_SUBDIR = Path(".memoria") / "cache" / "graph" / "retrieval"
MODEL_ID = "keyword-only"          # v1 不启 embedding：显式记录，不用假 model_id 冒充
MODEL_DIM = 0
MODEL_LICENSE = "n/a"
#: 估算 token 用的粗略系数（0.4237 tok/字 的实测值来自会话；索引条目按字符数估）
TOKENS_PER_CHAR = 0.4237


def canonical_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _sha_file_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RetrievalIndex:
    """一次性构建、不可变内存索引（派生，不是事实）。"""

    edition: str
    data_source_sha: str
    entries: tuple[dict, ...]
    semantic_edges: tuple[dict, ...]
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "index_version": INDEX_VERSION,
            "edition": self.edition,
            "data_source_sha": self.data_source_sha,
            "entries": [copy.deepcopy(dict(e)) for e in self.entries],
            "semantic_edges": [copy.deepcopy(dict(e)) for e in self.semantic_edges],
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetrievalIndex":
        if not isinstance(data, dict) or int(data.get("index_version") or 0) != INDEX_VERSION:
            raise GraphError(GRAPH_INTERNAL, "检索索引版本不符（需重建）",
                             detail={"index_version": data.get("index_version")})
        return cls(
            edition=str(data.get("edition") or ""),
            data_source_sha=str(data.get("data_source_sha") or ""),
            entries=tuple(copy.deepcopy(dict(e)) for e in data.get("entries") or ()),
            semantic_edges=tuple(copy.deepcopy(dict(e)) for e in data.get("semantic_edges") or ()),
            metadata=copy.deepcopy(dict(data.get("metadata") or {})),
        )

    def canonical_sha(self) -> str:
        return sha256_canonical(self.to_dict())


def _is_semantic(edge: dict) -> bool:
    return str(edge.get("contain_kind") or "") == "semantic" or \
        str(edge.get("label") or "") == "semantic"


def _edge_id(edge: dict, target: str) -> str:
    return f"{edge.get('type') or ''}|{edge.get('source_id') or ''}|{target}"


def build_index(datasource: DataSource) -> RetrievalIndex:
    """从只读 DataSource 构建确定性索引（同 datasource ⇒ 同 bytes）。"""
    entries: list[dict] = []
    for kp in sorted(datasource.kps, key=lambda k: str(k.get("id"))):
        kp_id = str(kp.get("id") or "")
        if not kp_id:
            continue
        file = str(kp.get("file") or "")
        start = kp.get("start_line")
        end = kp.get("end_line")
        name = str(kp.get("name") or kp_id)
        description = str(kp.get("description") or "")
        entries.append({
            "candidate_ref": f"kp:{kp_id}",
            "kind": "kp",
            "kp_id": kp_id,
            "name": name,
            "description": description,
            "file": file,
            "line": start if isinstance(start, int) else None,
            "end_line": end if isinstance(end, int) else None,
            "anchor_complete": bool(file and isinstance(start, int) and isinstance(end, int)
                                    and kp.get("range_ok", True)),
            "text": f"{name}\n{description}".strip(),
            "source_hash": sha256_canonical(kp),
        })
        if file:
            entries.append({
                "candidate_ref": f"file:{file}",
                "kind": "file",
                "name": Path(file).name,
                "description": "",
                "file": file,
                "line": None,
                "end_line": None,
                "anchor_complete": True,
                "text": file,
                "source_hash": sha256_canonical({"file": file}),
            })
            if isinstance(start, int):
                entries.append({
                    "candidate_ref": f"anchor:{kp_id}",
                    "kind": "anchor",
                    "kp_id": kp_id,
                    "name": name,
                    "description": "",
                    "file": file,
                    "line": start,
                    "end_line": end if isinstance(end, int) else None,
                    "anchor_complete": True,
                    "text": f"{file}:{start}",
                    "source_hash": sha256_canonical({"file": file, "line": start,
                                                     "kp": kp_id}),
                })
    semantic_edges: list[dict] = []
    seen: set[str] = set()
    for edge in sorted(datasource.edges,
                       key=lambda e: (str(e.get("type")), str(e.get("source_id")),
                                      tuple(str(t) for t in e.get("targets") or ()))):
        if not _is_semantic(edge):
            continue
        for target in sorted(str(t) for t in edge.get("targets") or ()):
            eid = _edge_id(edge, target)
            if eid in seen:
                continue
            seen.add(eid)
            semantic_edges.append({
                "edge_id": eid,
                "type": str(edge.get("type") or ""),
                "source": str(edge.get("source_id") or ""),
                "target": target,
                "relation_class": "semantic",
            })
    metadata = {
        "index_version": INDEX_VERSION,
        "edition": datasource.canonical_id,
        "data_source_sha": sha256_canonical(datasource.to_dict()),
        "rebuildable": True,
        "model_id": MODEL_ID,
        "dim": MODEL_DIM,
        "license": MODEL_LICENSE,
        "embedding_enabled": False,
        "built_by": "memoria.graph.retrieval.index",
        "entry_count": len(entries),
        "semantic_edge_count": len(semantic_edges),
    }
    return RetrievalIndex(
        edition=datasource.canonical_id,
        data_source_sha=metadata["data_source_sha"],
        entries=tuple(sorted(entries, key=lambda e: e["candidate_ref"])),
        semantic_edges=tuple(semantic_edges),
        metadata=metadata,
    )


class IndexStore:
    """``.memoria/cache/graph/retrieval/`` 的构建 / 原子写 / 加载（可删重建）。"""

    def __init__(self, kb_path: str | Path) -> None:
        self.kb_path = Path(kb_path)
        self.root = self.kb_path / CACHE_SUBDIR

    @property
    def indexPath(self) -> Path:
        return self.root

    def path_for(self, edition: str) -> Path:
        if not edition:
            raise GraphError(GRAPH_INTERNAL, "索引 edition 为空")
        return self.root / f"{edition}.json"

    def load(self, edition: str) -> RetrievalIndex:
        path = self.path_for(edition)
        if not path.is_file():
            raise GraphError(GRAPH_RETRIEVAL_UNAVAILABLE,
                             f"检索索引不存在（需重建）：{edition}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return RetrievalIndex.from_dict(data)

    def write(self, index: RetrievalIndex) -> dict:
        """原子写：同目录临时文件 + ``os.replace``；metadata 可复算。"""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(index.edition)
        raw = canonical_bytes(index.to_dict())
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, path)
        return {"path": str(path), "sha256": _sha_file_bytes(raw), "bytes": len(raw)}

    def build(self, datasource: DataSource) -> RetrievalIndex:
        return build_index(datasource)

    def load_or_build(
        self,
        datasource: DataSource | None = None,
        *,
        rebuild: bool = False,
    ) -> tuple[RetrievalIndex, bool]:
        """返回 ``(index, built_now)``；edition 变化或 rebuild=True ⇒ 全量重建。"""
        ds = datasource if datasource is not None else DataSourceReader(self.kb_path).read()
        expected = ds.canonical_id
        if not rebuild:
            try:
                cached = self.load(expected)
            except GraphError:
                cached = None
            if cached is not None and cached.data_source_sha == sha256_canonical(ds.to_dict()):
                return cached, False
        index = self.build(ds)
        self.write(index)
        return index, True

    def rebuild(self, datasource: DataSource | None = None) -> RetrievalIndex:
        ds = datasource if datasource is not None else DataSourceReader(self.kb_path).read()
        index = self.build(ds)
        self.write(index)
        return index

    def is_stale(self, index: RetrievalIndex, datasource: DataSource | None = None) -> bool:
        ds = datasource if datasource is not None else DataSourceReader(self.kb_path).read()
        return index.edition != ds.canonical_id or \
            index.data_source_sha != sha256_canonical(ds.to_dict())


def estimate_candidate_tokens(candidate: dict) -> int:
    """候选的保守 token 估算（用于 budget=4000 的显式截断；不藏 token）。"""
    ref = str(candidate.get("candidate_ref") or "")
    reason = str(candidate.get("reason") or "")
    name = str(candidate.get("name") or "")
    return int((len(ref) + len(reason) + len(name)) * TOKENS_PER_CHAR) + 8


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
