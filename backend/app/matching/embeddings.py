"""Cosine-similarity pre-filter over stored embeddings — the cheap, fast stage
that narrows hundreds of candidates down to a shortlist before any per-
candidate LLM call happens. No external vector DB needed at this scale
(swap for pgvector/Pinecone behind the storage backend later if it grows)."""

import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def top_n_by_similarity(
    query_embedding: list[float], candidate_embeddings: dict[str, list[float]], n: int
) -> list[str]:
    """Ranks every candidate by cosine similarity to the query in one matrix
    op instead of looping cosine_similarity() per candidate (which rebuilt
    fresh numpy arrays on every single pairwise call — the dominant cost at
    real volume, since this runs once per "Run matching" click over the
    entire candidate pool)."""
    if not candidate_embeddings:
        return []
    ids = list(candidate_embeddings.keys())
    matrix = np.array([candidate_embeddings[cid] for cid in ids], dtype=np.float64)
    query = np.array(query_embedding, dtype=np.float64)

    matrix_norms = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(query)
    denom = matrix_norms * query_norm
    similarities = np.divide(
        matrix @ query, denom, out=np.zeros_like(matrix_norms), where=denom != 0
    )

    top_indices = np.argsort(-similarities)[:n]
    return [ids[i] for i in top_indices]
