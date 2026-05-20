"""Tests for orchestrator tool dispatch that do not call the live LLM."""

from __future__ import annotations

from agent.orchestrator import _execute_tool
from agent.state import ConversationState


def test_execute_tool_requires_policy_action_for_escalate():
    state = ConversationState(user_id="u_001")

    result = _execute_tool(
        "escalate",
        {
            "issue_summary": "Account locked",
            "urgency": "high",
            "suspected_cause": "Okta lockout",
            "recommended_team": "Identity Access Management",
        },
        state,
    )

    assert result.success is False
    assert "policy_action" in (result.error or "")


def test_execute_tool_injects_context_and_enforces_policy_route(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.escalation.LOG_DIR", tmp_path)
    state = ConversationState(
        user_id="u_004",
        user_record={"name": "David Kim"},
    )

    result = _execute_tool(
        "escalate",
        {
            "policy_action": "snowflake_prod_access",
            "issue_summary": "New Data Engineering hire needs Snowflake prod access",
            "urgency": "normal",
            "suspected_cause": "Missing production database permission",
            "recommended_team": "Identity Access Management",
            "attempted_steps": ["Verified the request is for production access"],
        },
        state,
    )

    assert result.success is True
    assert result.data["user_id"] == "u_004"
    assert result.data["user_name"] == "David Kim"
    assert result.data["recommended_team"] == "Data Platform Team"
    assert result.data["policy_decision"]["agent_allowed"] is False
