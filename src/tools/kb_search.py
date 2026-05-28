"""search_kb — BM25 full-text search over kb/*.md."""

from __future__ import annotations

import time
from functools import lru_cache

from rank_bm25 import BM25Okapi

from agent.schemas import ToolResult
from tools._data import load_kb, simulated_failure, tokenize


@lru_cache(maxsize=1)
def _kb_index() -> tuple[tuple[dict, ...], BM25Okapi]:
    """Build the BM25 index lazily on first call. Returned tuple is hashable for cache.

    第一次 search_kb 时才建 BM25 索引；之后复用缓存，避免每次重复分词。
    """
    articles = load_kb()
    # BM25 works over tokenized document text.
    # BM25 接收的是每篇文章的 token 列表。
    corpus = [tokenize(a["content"]) for a in articles]
    return tuple(articles), BM25Okapi(corpus)


def search_kb(query: str, top_k: int = 3) -> ToolResult:
    """Return up to top_k KB articles ranked by BM25 against the query.

    知识库搜索工具。返回文章 ID、标题、路径、分数和摘录，让模型能引用 KB。
    """
    start = time.perf_counter()

    if (err := simulated_failure("search_kb")):
        # Simulate search failure for reliability evals.
        # 可靠性评测用：强制搜索失败，看模型是否会承认失败。
        return ToolResult(
            name="search_kb",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not query or not query.strip():
        # Empty queries are tool misuse, returned as structured failure.
        # 空 query 返回结构化失败，不抛异常。
        return ToolResult(
            name="search_kb",
            success=False,
            error="query is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    articles, bm25 = _kb_index()
    scores = bm25.get_scores(tokenize(query))
    # Rank highest BM25 score first.
    # BM25 分数越高，文本匹配越强，排序越靠前。
    ranked = sorted(zip(scores, articles), key=lambda pair: pair[0], reverse=True)

    hits = []
    for score, article in ranked[:top_k]:
        if score <= 0:
            # Zero-score documents are not useful evidence.
            # 分数为 0 的文章不算有效命中，不返回给模型。
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
