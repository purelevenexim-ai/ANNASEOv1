"""
relevance.py — TF-IDF cosine similarity ranking for bs_snippets.

Given a target keyword and a list of snippet dicts (from bs_snippets),
returns them sorted by relevance score (descending).
"""
from __future__ import annotations
from typing import List, Dict, Any


def rank_snippets_for_keyword(
    keyword: str,
    snippets: List[Dict[str, Any]],
    top_n: int = 8,
) -> List[Dict[str, Any]]:
    """
    Return up to `top_n` snippets ranked by TF-IDF cosine similarity to `keyword`.
    Falls back to returning all snippets if sklearn is unavailable or corpus is tiny.

    Each returned dict is the original snippet dict with an added `_score` float.
    """
    if not snippets or not keyword:
        return snippets[:top_n]

    texts = [s.get("text", "") for s in snippets]
    corpus = [keyword] + texts  # query is index 0

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(min_df=1, stop_words="english")
        matrix = vec.fit_transform(corpus)
        # Similarity between query (row 0) and each snippet (rows 1..)
        sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()

        scored = []
        for snippet, score in zip(snippets, sims):
            s = dict(snippet)
            s["_score"] = float(score)
            scored.append(s)

        scored.sort(key=lambda x: x["_score"], reverse=True)
        return scored[:top_n]

    except Exception:
        # If sklearn not available, return as-is with neutral score
        for s in snippets:
            s.setdefault("_score", 0.5)
        return snippets[:top_n]
