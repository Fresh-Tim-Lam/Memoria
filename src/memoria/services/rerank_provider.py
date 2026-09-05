"""P3 Embed-Rerank（cross-encoder 精排）。

对 search_kernel RRF 融合后的 Top-K 结果用 cross-encoder 重新排序。
失败时降级到原顺序。
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any

# 必须在任何 HF/transformers 相关 import 之前设置，否则 huggingface_hub
# 会在 import 时缓存 online 状态，后续 setdefault 无效
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# 发布包（PyInstaller frozen）内置离线模型于 <exe 目录>/hf（构建见 packaging/build.py）
if getattr(sys, "frozen", False):
    _bundled_hf = os.path.join(os.path.dirname(sys.executable), "hf")
    if os.path.isdir(_bundled_hf):
        os.environ.setdefault("HF_HOME", _bundled_hf)

from memoria.services.model_router import embed_rerank_model, is_role_enabled
from memoria.services.text_normalize import normalize_math_for_semantic
from memoria.storage.ui_settings import load_ui_settings

_reranker_cache: dict[str, Any] = {}
_reranker_lock = threading.Lock()


def _search_settings() -> dict:
    raw = load_ui_settings().get("search")
    return raw if isinstance(raw, dict) else {}


def is_rerank_enabled() -> bool:
    return bool(_search_settings().get("rerank_enabled"))


def _build_doc_text(rec: dict) -> str:
    """构建用于 rerank 的文档文本（name + tags + description + body 节选）。"""
    parts = [
        str(rec.get("name") or ""),
        " ".join(str(t) for t in (rec.get("tags") or [])),
        str(rec.get("kp_description") or ""),
        str(rec.get("body_excerpt") or "")[:512],
    ]
    return normalize_math_for_semantic(" ".join(p for p in parts if p))


class _CrossEncoderReranker:
    """Wraps transformers AutoTokenizer + AutoModelForSequenceClassification.

    bge-reranker-v2-m3 输出 single logit per (query, doc) pair。
    """

    def __init__(self, model_name: str):
        import sys as _sys
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        _diag = os.environ.get("MEMORIA_EMB_DIAG")
        if _diag:
            print(f"[rerank-diag] loading tokenizer: {model_name}", file=_sys.stderr, flush=True)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        if _diag:
            print(f"[rerank-diag] tokenizer OK, loading model: {model_name}", file=_sys.stderr, flush=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name, local_files_only=True
        )
        self.model.eval()
        self._name = model_name
        if _diag:
            print(f"[rerank-diag] model OK: {type(self.model).__name__}", file=_sys.stderr, flush=True)

    def predict(self, pairs: list[tuple[str, str]], *, batch_size: int = 8) -> list[float]:
        """对 (query, doc) pairs 计算相关性分数。返回 logits 列表。"""
        import torch

        torch.set_num_threads(1)
        scores: list[float] = []
        with torch.no_grad():
            for i in range(0, len(pairs), batch_size):
                batch = pairs[i : i + batch_size]
                texts_a = [p[0] for p in batch]
                texts_b = [p[1] for p in batch]
                inputs = self.tokenizer(
                    texts_a,
                    texts_b,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=256,
                )
                outputs = self.model(**inputs)
                logits = outputs.logits.squeeze(-1).float().cpu().tolist()
                if isinstance(logits, float):
                    logits = [logits]
                scores.extend(logits)
        return scores


def _load_reranker(model_name: str):
    name = (model_name or "").strip()
    if not name:
        return None
    if name in _reranker_cache:
        return _reranker_cache[name]
    with _reranker_lock:
        if name in _reranker_cache:
            return _reranker_cache[name]
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            model = _CrossEncoderReranker(name)
        except (OSError, ValueError, ImportError):
            return None
        _reranker_cache[name] = model
        return model


def rerank_search_results(
    query: str,
    results: list[dict],
    *,
    kb_path: str,
    top_k: int = 20,
) -> list[dict]:
    """对 search 结果重新排序。

    1. 从 lexical_index 获取每个 result 的 record text
    2. 用 cross-encoder 计算 (query, doc) 相关性
    3. 按分数重新排序

    失败时降级到原顺序。
    """
    if not results:
        return results

    if not is_rerank_enabled():
        return results

    model_name = embed_rerank_model(kb_path=kb_path)
    if not model_name:
        return results

    reranker = _load_reranker(model_name)
    if reranker is None:
        return results

    # 获取 lexical records 以提取文档文本
    from memoria.services.lexical_index import ensure_lexical_index

    lexical = ensure_lexical_index(kb_path)
    records_by_id: dict[str, dict] = {}
    for rec in lexical.get("records") or []:
        kid = str(rec.get("kp_id") or "")
        if kid:
            records_by_id[kid] = rec

    # 构建 (query, doc_text) pairs
    q = normalize_math_for_semantic(query)
    pairs: list[tuple[str, str]] = []
    for r in results:
        kid = str(r.get("kp_id") or "")
        rec = records_by_id.get(kid, {})
        doc_text = _build_doc_text(rec)
        pairs.append((q, doc_text))

    try:
        scores = reranker.predict(pairs)
    except Exception:
        return results

    # 按分数重新排序
    scored = list(zip(scores, results))
    scored.sort(key=lambda x: -x[0])

    out: list[dict] = []
    max_score = max(abs(s) for s in scores) if scores else 1.0
    if max_score == 0:
        max_score = 1.0

    for i, (score, r) in enumerate(scored[:top_k]):
        r = dict(r)
        r["rerank_score"] = round(float(score), 4)
        # 归一化到 0-100 区间作为 display score
        normalized = (float(score) / max_score) * 100.0
        r["score"] = round(normalized, 1)
        r["rerank_rank"] = i + 1
        out.append(r)

    return out
