"""check_system_status — return current status, incidents, recent_changes,
and upstream dependencies for one service.
"""

from __future__ import annotations

import time

from agent.schemas import ToolResult
from tools._data import load_status, simulated_failure


def check_system_status(service: str) -> ToolResult:
    """Return the status record for the named service, with upstream deps injected."""
    start = time.perf_counter()

    if (err := simulated_failure("check_system_status")):
        return ToolResult(
            name="check_system_status",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not service or not service.strip():
        return ToolResult(
            name="check_system_status",
            success=False,
            error="service is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    services, deps = load_status()
    key = service.lower().strip()
    record = services.get(key)
    latency = (time.perf_counter() - start) * 1000

    if record is None:
        return ToolResult(
            name="check_system_status",
            success=False,
            error=(
                f"Unknown service '{service}'. "
                f"Known services: {sorted(services.keys())}"
            ),
            latency_ms=latency,
        )

    payload = dict(record)
    payload["upstream_dependencies"] = deps.get(key, [])
    return ToolResult(
        name="check_system_status",
        success=True,
        data=payload,
        latency_ms=latency,
    )
