"""escalate — create a structured handoff package and persist to logs/escalations/."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from agent.policy import check_action
from agent.schemas import EscalationSummary, ToolResult
from tools._data import simulated_failure


LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "escalations"


def _generate_handoff_id() -> str:
    """ESC-YYYYMMDD-NNN where NNN is the next sequence number for today (UTC).

    生成类似 ESC-20260528-001 的交接单号；按当天已有文件数量递增。
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    existing = sum(1 for _ in LOG_DIR.glob(f"ESC-{today}-*.json"))
    return f"ESC-{today}-{existing + 1:03d}"


def escalate(
    policy_action: str,
    issue_summary: str,
    urgency: str,
    suspected_cause: str,
    recommended_team: str,
    attempted_steps: list[str] | None = None,
    # Context fields injected by the orchestrator from ConversationState:
    user_id: str = "unknown",
    user_name: str = "unknown",
    services_involved: list[str] | None = None,
    tools_consulted: list[str] | None = None,
) -> ToolResult:
    """Build an EscalationSummary, validate it, write it to disk, return it.

    escalation 是“创建人工交接包”，不是执行高权限操作。agent 不会解锁
    账号、重置 MFA、授予权限；它只把完整上下文交给对应人工团队。
    """
    start = time.perf_counter()

    if (err := simulated_failure("escalate")):
        # Simulated escalation failure for reliability tests.
        # 用于测试升级工具失败时 agent 的降级行为。
        return ToolResult(
            name="escalate",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    # Code-level policy check can override the model's recommended route.
    # 代码层 policy 会再次检查权限；如果 policy 指定团队，覆盖模型建议团队。
    policy_decision = check_action(policy_action)
    if not policy_decision.agent_allowed and policy_decision.escalate_to:
        recommended_team = policy_decision.escalate_to

    try:
        # EscalationSummary is the durable handoff contract for humans.
        # EscalationSummary 是写入文件、给人工团队看的结构化交接合同。
        summary = EscalationSummary(
            handoff_id=_generate_handoff_id(),
            created_at=datetime.now(timezone.utc),
            user_id=user_id or "unknown",
            user_name=user_name or "unknown",
            issue_summary=issue_summary,
            urgency=urgency,
            services_involved=list(services_involved or []),
            tools_consulted=list(tools_consulted or []),
            attempted_steps=list(attempted_steps or []),
            suspected_cause=suspected_cause,
            recommended_team=recommended_team,
            policy_action=policy_action,
            policy_decision=policy_decision,
        )
    except ValidationError as exc:
        # Bad handoff payload becomes a tool error for the model to handle.
        # 交接包字段不合法时返回工具失败，让模型告知用户或重试。
        return ToolResult(
            name="escalate",
            success=False,
            error=f"Invalid escalation payload: {exc}",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    # Persist the handoff so it survives beyond the chat session.
    # 把交接包落盘，聊天结束后也能追踪。
    out_path = LOG_DIR / f"{summary.handoff_id}.json"
    out_path.write_text(summary.model_dump_json(indent=2))

    return ToolResult(
        name="escalate",
        success=True,
        data=summary.model_dump(mode="json"),
        latency_ms=(time.perf_counter() - start) * 1000,
    )
