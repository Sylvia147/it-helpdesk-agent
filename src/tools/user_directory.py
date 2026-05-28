"""lookup_user — return a single employee record by user_id."""

from __future__ import annotations

import time

from agent.schemas import ToolResult
from tools._data import load_users, simulated_failure


def lookup_user(user_id: str) -> ToolResult:
    """Return the employee record for the given user_id, or a not-found error.

    员工目录查询工具。它只读 mock data/users.json，不修改任何账号状态。
    """
    start = time.perf_counter()

    if (err := simulated_failure("lookup_user")):
        # Fault injection path used by evals; shape matches a real tool failure.
        # 测试用故障注入；返回结构和真实失败保持一致。
        return ToolResult(
            name="lookup_user",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not user_id or not user_id.strip():
        # Tool functions validate basic required fields too, not only schemas.
        # 即使 schema 校验过，工具内部仍做基础防御，方便单独调用测试。
        return ToolResult(
            name="lookup_user",
            success=False,
            error="user_id is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    # Directory records are keyed by user_id, e.g. u_001.
    # users.json 以 user_id 作为 key。
    record = load_users().get(user_id.strip())
    latency = (time.perf_counter() - start) * 1000

    if record is None:
        # Unknown users are a structured tool error, not an exception.
        # 查不到用户时返回 ToolResult(success=False)，由 agent 决定后续怎么说。
        return ToolResult(
            name="lookup_user",
            success=False,
            error=f"No user found with id '{user_id}'",
            latency_ms=latency,
        )

    # Hide demo-only metadata fields from the agent.
    # `_demo_hook` 这类演示注释不应该暴露给模型，所以过滤掉。
    cleaned = {k: v for k, v in record.items() if not k.startswith("_")}
    return ToolResult(
        name="lookup_user",
        success=True,
        data=cleaned,
        latency_ms=latency,
    )
