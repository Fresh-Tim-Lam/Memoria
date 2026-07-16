"""Debug: check lexical index records and embedding build (no exception swallowing)."""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

LOG = open(ROOT / "benchmarks/beir_scifact/_debug_emb.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

from memoria.services import lexical_index as li
from memoria.storage import ui_settings
ui_settings.save_ui_settings({"search": {"embedding_enabled": True, "allow_model_download": True}})

from memoria.services import embedding_provider as ep

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold_subset")
log("rebuilding lexical index...")
li.rebuild_lexical_index(KB)
log("done")

log("building embedding index (debug mode)...")
try:
    from memoria.services.embedding_provider import (
        is_embedding_enabled, embedding_model_name, ensure_lexical_index,
        load_embedding_index, _record_text, _record_desc_text, _combined_fingerprint,
        _load_model, _make_out_record, _index_meta, save_embedding_index,
    )

    if not is_embedding_enabled():
        log("ERROR: embedding not enabled!")
        sys.exit(1)

    model_name = embedding_model_name()
    log(f"model: {model_name}")

    lexical = ensure_lexical_index(KB)
    lexical_records = lexical.get("records") or []
    lexical_built_at = str(lexical.get("built_at") or "")
    log(f"lexical records: {len(lexical_records)}")

    cached = load_embedding_index(KB)
    cached_by_id = {}
    if cached:
        for rec in cached.get("records") or []:
            kid = str(rec.get("kp_id") or "")
            if kid:
                cached_by_id[kid] = rec

    out_records = []
    pending = []

    for lex_rec in lexical_records:
        kid = str(lex_rec.get("kp_id") or "")
        if not kid:
            continue
        text = _record_text(lex_rec)
        desc_text = _record_desc_text(lex_rec)
        text_fp = _combined_fingerprint(text, desc_text)
        old = cached_by_id.get(kid)
        old_vec = old.get("vector") if isinstance(old, dict) else None
        old_desc = old.get("desc_vector") if isinstance(old, dict) else None
        if (
            isinstance(old_vec, list)
            and old_vec
            and isinstance(old_desc, list)
            and old_desc
            and str(old.get("text_fp") or "") == text_fp
        ):
            out_records.append(_make_out_record(lex_rec, [float(x) for x in old_vec], [float(x) for x in old_desc], text_fp))
            continue
        pending.append((lex_rec, text, desc_text, text_fp))

    log(f"pending: {len(pending)} records to encode")

    if pending:
        log("loading model...")
        st_model = _load_model(model_name)
        log(f"model loaded: {type(st_model).__name__}")

        log("encoding (this may take a while)...")
        batch = []
        for _lex_rec, text, desc_text, _fp in pending:
            batch.append(text)
            batch.append(desc_text)
        log(f"batch size: {len(batch)}")

        # Encode in small batches to show progress
        all_vectors = []
        batch_size = 32
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            vecs = st_model.encode(chunk, normalize_embeddings=True, show_progress_bar=False)
            all_vectors.extend(vecs)
            if (i // batch_size + 1) % 5 == 0:
                log(f"  encoded {len(all_vectors)}/{len(batch)}")

        log(f"encoded {len(all_vectors)} vectors")

        for i, (lex_rec, _text, _desc_text, text_fp) in enumerate(pending):
            out_records.append(
                _make_out_record(lex_rec, all_vectors[i * 2], all_vectors[i * 2 + 1], text_fp)
            )

    out_records.sort(key=lambda r: str(r.get("kp_id") or ""))
    index = _index_meta(model_name, lexical_built_at=lexical_built_at, records=out_records)
    save_embedding_index(KB, index)
    log(f"DONE: {len(out_records)} records saved")
except Exception as e:
    log(f"EXCEPTION: {type(e).__name__}: {e}")
    traceback.print_exc(file=LOG)
finally:
    LOG.close()
