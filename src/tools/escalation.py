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
    """ESC-YYYYMMDD-NNN where NNN is the next sequence number for today (UTC)."""
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
    """Build an EscalationSummary, validate it, write it to disk, return it."""
    start = time.perf_counter()

    if (err := simulated_failure("escalate")):
        return ToolResult(
            name="escalate",
            success=False,
            error=err,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    policy_decision = check_action(policy_action)
    if not policy_decision.agent_allowed and policy_decision.escalate_to:
        recommended_team = policy_decision.escalate_to

    try:
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
        return ToolResult(
            name="escalate",
            success=False,
            error=f"Invalid escalation payload: {exc}",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    out_path = LOG_DIR / f"{summary.handoff_id}.json"
    out_path.write_text(summary.model_dump_json(indent=2))

    return ToolResult(
        name="escalate",
        success=True,
        data=summary.model_dump(mode="json"),
        latency_ms=(time.perf_counter() - start) * 1000,
    )
