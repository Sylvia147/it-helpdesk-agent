"""lookup_user — return a single employee record by user_id."""

from __future__ import annotations

import time

from agent.schemas import ToolResult
from tools._data import load_users, simulated_failure


def lookup_user(user_id: str) -> ToolResult:
    """Return the employee record for the given user_id, or a not-found error."""
    start = time.perf_counter()

    if (err := simulated_failure("lookup_user")):
        return ToolResult(
            name="lookup_user",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not user_id or not user_id.strip():
        return ToolResult(
            name="lookup_user",
            success=False,
            error="user_id is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    record = load_users().get(user_id.strip())
    latency = (time.perf_counter() - start) * 1000

    if record is None:
        return ToolResult(
            name="lookup_user",
            success=False,
            error=f"No user found with id '{user_id}'",
            latency_ms=latency,
        )

    cleaned = {k: v for k, v in record.items() if not k.startswith("_")}
    return ToolResult(
        name="lookup_user",
        success=True,
        data=cleaned,
        latency_ms=latency,
    )
