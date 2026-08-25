"""Pins top_n_by_similarity's vectorized rewrite against the same output the
original per-pair Python loop produced (numpy matrix op replacing a fresh
np.array() allocation per candidate — see project-log)."""

import random

from app.matching.embeddings import cosine_similarity, top_n_by_similarity


def _reference_top_n(query_embedding, candidate_embeddings, n):
    scored = [(cid, cosine_similarity(query_embedding, emb)) for cid, emb in candidate_embeddings.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in scored[:n]]


def test_matches_reference_loop_implementation():
    random.seed(0)
    query = [random.random() for _ in range(16)]
    candidates = {f"c{i}": [random.random() for _ in range(16)] for i in range(200)}

    assert top_n_by_similarity(query, candidates, n=10) == _reference_top_n(query, candidates, n=10)


def test_empty_pool_returns_empty_list():
    assert top_n_by_similarity([1.0, 0.0], {}, n=5) == []


def test_n_larger_than_pool_returns_everything():
    candidates = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    result = top_n_by_similarity([1.0, 0.0], candidates, n=10)
    assert set(result) == {"a", "b"}


def test_zero_vector_candidate_does_not_crash():
    candidates = {"a": [1.0, 0.0], "zero": [0.0, 0.0]}
    result = top_n_by_similarity([1.0, 0.0], candidates, n=2)
    assert result[0] == "a"
