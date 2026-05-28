"""check_system_status — return current status, incidents, recent_changes,
and upstream dependencies for one service.
"""

from __future__ import annotations

import time

from agent.schemas import ToolResult
from tools._data import load_status, simulated_failure


def check_system_status(service: str) -> ToolResult:
    """Return the status record for the named service, with upstream deps injected.

    系统状态查询工具。它返回服务健康状态、active incidents、recent changes，
    并附带上游依赖，帮助 agent 诊断多系统连锁问题。
    """
    start = time.perf_counter()

    if (err := simulated_failure("check_system_status")):
        # Simulated reliability failure path.
        # 用环境变量触发的模拟故障路径。
        return ToolResult(
            name="check_system_status",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    if not service or not service.strip():
        # Required argument guard for direct/tool misuse.
        # service 不能为空；工具内部也做基础参数检查。
        return ToolResult(
            name="check_system_status",
            success=False,
            error="service is required",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    services, deps = load_status()
    # Service names are normalized so "Salesforce" and "salesforce" both work.
    # 服务名做小写去空格，用户/模型大小写不一致也能查到。
    key = service.lower().strip()
    record = services.get(key)
    latency = (time.perf_counter() - start) * 1000

    if record is None:
        # Include known services to help the model recover with a better call.
        # 返回可用服务列表，方便模型下一轮改用正确 service 名。
        return ToolResult(
            name="check_system_status",
            success=False,
            error=(
                f"Unknown service '{service}'. "
                f"Known services: {sorted(services.keys())}"
            ),
            latency_ms=latency,
        )

    # Copy before injecting dependencies so cached source data is not mutated.
    # 先复制 record，再注入 upstream_dependencies，避免改坏缓存数据。
    payload = dict(record)
    payload["upstream_dependencies"] = deps.get(key, [])
    return ToolResult(
        name="check_system_status",
        success=True,
        data=payload,
        latency_ms=latency,
    )
