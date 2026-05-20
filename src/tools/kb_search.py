"""search_kb — BM25 full-text search over kb/*.md."""

from __future__ import annotations

import time
from functools import lru_cache

from rank_bm25 import BM25Okapi

from agent.schemas import ToolResult
from tools._data import load_kb, simulated_failure, tokenize


@lru_cache(maxsize=1)
def _kb_index() -> tuple[tuple[dict, ...], BM25Okapi]:
    """Build the BM25 index lazily on first call. Returned tuple is hashable for cache."""
    articles = load_kb()
    corpus = [tokenize(a["content"]) for a in articles]
    return tuple(articles), BM25Okapi(corpus)


def search_kb(query: str, top_k: int = 3) -> ToolResult:
    """Return up to top_k KB articles ranked by BM25 against the query."""
    start = time.perf_counter()

    if (err := simulated_failure("search_kb")):
        return ToolResult(
            name="search_kb",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not query or not query.strip():
        return ToolResult(
            name="search_kb",
            success=False,
            error="query is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    articles, bm25 = _kb_index()
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(scores, articles), key=lambda pair: pair[0], reverse=True)

    hits = []
    for score, article in ranked[:top_k]:
        if score <= 0:
            continue
        hits.append(
            {
                "article_id": article["article_id"],
                "title": article["title"],
                "path": article["path"],
                "score": round(float(score), 3),
                "excerpt": article["content"][:600],
            }
        )

    return ToolResult(
        name="search_kb",
        success=True,
        data={"hits": hits, "query": query},
        latency_ms=(time.perf_counter() - start) * 1000,
    )
