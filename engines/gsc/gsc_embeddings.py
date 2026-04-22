"""
GSC Phase 2 — Embedding Engine
Generates and caches keyword embeddings using local sentence-transformers.
Primary: all-MiniLM-L6-v2 (384 dims, free, fast, offline)
Fallback: Gemini embedding API if configured

Incremental: only embeds NEW keywords (skips already-embedded ones).
"""
import logging
import numpy as np
from typing import Optional

from . import gsc_db

log = logging.getLogger(__name__)

# ─── Lazy-loaded model singleton ──────────────────────────────────────────────

_model = None
_MODEL_NAME = "all-MiniLM-L6-v2"
_DIMS = 384


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        log.info(f"[GSC Embed] Loading {_MODEL_NAME} ...")
        _model = SentenceTransformer(_MODEL_NAME)
        log.info("[GSC Embed] Model loaded")
    return _model


def embed_keywords(keywords: list[str], batch_size: int = 256) -> np.ndarray:
    """Embed a list of keywords. Returns (N, 384) float32 array."""
    model = _get_model()
    vectors = model.encode(keywords, batch_size=batch_size, show_progress_bar=False,
                           normalize_embeddings=True)
    return np.array(vectors, dtype=np.float32)


def vector_to_bytes(vec: np.ndarray) -> bytes:
    """Serialize a single vector to bytes for SQLite BLOB storage."""
    return vec.astype(np.float32).tobytes()


def bytes_to_vector(b: bytes) -> np.ndarray:
    """Deserialize bytes back to numpy vector."""
    return np.frombuffer(b, dtype=np.float32)


# ─── Project-level operations ────────────────────────────────────────────────

def generate_embeddings(project_id: str, force: bool = False) -> dict:
    """
    Generate embeddings for all processed keywords in a project.
    Incremental: skips keywords that already have embeddings (unless force=True).

    Returns: {embedded: N, skipped: N, total: N}
    """
    processed = gsc_db.get_processed_keywords(project_id)
    if not processed:
        return {"embedded": 0, "skipped": 0, "total": 0}

    all_keywords = [kw["keyword"] for kw in processed if kw.get("keyword")]

    if force:
        to_embed = all_keywords
        skipped = 0
    else:
        already = gsc_db.get_embedded_keywords(project_id)
        to_embed = [k for k in all_keywords if k not in already]
        skipped = len(all_keywords) - len(to_embed)

    if not to_embed:
        log.info(f"[GSC Embed] No new keywords to embed ({skipped} already done)")
        return {"embedded": 0, "skipped": skipped, "total": len(all_keywords)}

    log.info(f"[GSC Embed] Embedding {len(to_embed)} keywords (skipping {skipped})")
    vectors = embed_keywords(to_embed)

    # Store in DB in batches
    rows = [
        {"keyword": kw, "vector": vector_to_bytes(vec), "model": _MODEL_NAME}
        for kw, vec in zip(to_embed, vectors)
    ]
    BATCH = 500
    for i in range(0, len(rows), BATCH):
        gsc_db.upsert_embeddings(project_id, rows[i:i + BATCH])

    log.info(f"[GSC Embed] Stored {len(to_embed)} embeddings")
    return {"embedded": len(to_embed), "skipped": skipped, "total": len(all_keywords)}


def load_vectors(project_id: str) -> tuple[list[str], np.ndarray]:
    """
    Load all stored embeddings for a project.
    Returns: (keywords_list, vectors_array) where vectors is (N, 384).
    """
    raw = gsc_db.get_embeddings(project_id)
    if not raw:
        return [], np.array([], dtype=np.float32).reshape(0, _DIMS)

    keywords = [r["keyword"] for r in raw]
    vectors = np.array([bytes_to_vector(r["vector"]) for r in raw], dtype=np.float32)
    return keywords, vectors


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity matrix. Assumes L2-normalized vectors."""
    if vectors.shape[0] == 0:
        return np.array([])
    # Already normalized by sentence-transformers, so dot product = cosine similarity
    return vectors @ vectors.T
