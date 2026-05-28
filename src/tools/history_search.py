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
    """Build a BM25 index over historical tickets.

    给历史工单建 BM25 索引，用于从过去案例里找相似症状/根因。
    """
    cases = load_history()
    corpus = [tokenize(_doc_text(c)) for c in cases]
    return tuple(cases), BM25Okapi(corpus)


def _doc_text(case: dict) -> str:
    """Concatenate searchable fields of a case into one string for BM25.

    一个历史 case 有很多字段；这里把症状、角色、地点、诊断路径、
    根因、解决方案、标签拼起来，作为可检索文本。
    """
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
    """Return up to top_k historical cases ranked by BM25, filtered by state.

    历史案例搜索工具。默认只返回 resolved 工单，避免拿未解决/不可复现
    案例误导 agent。
    """
    start = time.perf_counter()

    if (err := simulated_failure("search_history")):
        # Simulated tool failure path for reliability tests.
        # 可靠性测试用的故障注入路径。
        return ToolResult(
            name="search_history",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not query or not query.strip():
        # Empty query is invalid tool input.
        # 空 query 无法检索，返回结构化错误。
        return ToolResult(
            name="search_history",
            success=False,
            error="query is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    # include_states lets evals broaden the search, but default is resolved-only.
    # include_states 可以扩大搜索范围；默认只搜 resolved。
    states = tuple(include_states) if include_states else _DEFAULT_STATES
    cases, bm25 = _history_index()
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(scores, cases), key=lambda pair: pair[0], reverse=True)

    hits = []
    for score, case in ranked:
        if score <= 0:
            continue
        if case.get("state") not in states:
            # Skip cases outside the requested terminal states.
            # 跳过不在 include_states 里的历史工单。
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
