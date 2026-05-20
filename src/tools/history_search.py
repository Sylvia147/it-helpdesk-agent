"""search_history — BM25 search over resolution_history.json with state filtering."""

from __future__ import annotations

import time
from functools import lru_cache

from rank_bm25 import BM25Okapi

from agent.schemas import ToolResult
from tools._data import load_history, simulated_failure, tokenize


_DEFAULT_STATES = ("resolved",)


@lru_cache(maxsize=1)
def _history_index() -> tuple[tuple[dict, ...], BM25Okapi]:
    cases = load_history()
    corpus = [tokenize(_doc_text(c)) for c in cases]
    return tuple(cases), BM25Okapi(corpus)


def _doc_text(case: dict) -> str:
    """Concatenate searchable fields of a case into one string for BM25."""
    parts = [
        case.get("issue_summary", ""),
        case.get("user_role", ""),
        case.get("user_location", ""),
        " ".join(case.get("diagnosis_path", [])),
        case.get("root_cause", ""),
        case.get("resolution", ""),
        " ".join(case.get("tags", [])),
    ]
    return " ".join(parts)


def search_history(
    query: str,
    top_k: int = 3,
    include_states: list[str] | None = None,
) -> ToolResult:
    """Return up to top_k historical cases ranked by BM25, filtered by state."""
    start = time.perf_counter()

    if (err := simulated_failure("search_history")):
        return ToolResult(
            name="search_history",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not query or not query.strip():
        return ToolResult(
            name="search_history",
            success=False,
            error="query is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    states = tuple(include_states) if include_states else _DEFAULT_STATES
    cases, bm25 = _history_index()
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(scores, cases), key=lambda pair: pair[0], reverse=True)

    hits = []
    for score, case in ranked:
        if score <= 0:
            continue
        if case.get("state") not in states:
            continue
        hits.append(
            {
                "id": case["id"],
                "state": case["state"],
                "issue_summary": case["issue_summary"],
                "root_cause": case.get("root_cause", ""),
                "resolution": case.get("resolution", ""),
                "tags": case.get("tags", []),
                "score": round(float(score), 3),
                "escalated": case.get("escalated", False),
                "escalated_to": case.get("escalated_to"),
            }
        )
        if len(hits) >= top_k:
            break

    return ToolResult(
        name="search_history",
        success=True,
        data={"hits": hits, "query": query, "states_searched": list(states)},
        latency_ms=(time.perf_counter() - start) * 1000,
    )
