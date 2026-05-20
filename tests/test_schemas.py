"""Tests for src/agent/schemas.py.

Coverage targets:
- Each tool input schema constructs with valid args and rejects invalid ones.
- All Literal-typed fields (urgency, risk_level, history state, event type) reject
  unknown values.
- Numeric bounds (top_k, confidence, latency_ms) are enforced.
- All schemas forbid extra fields.
- JSON serialization round-trips lossless on EscalationSummary and TraceEvent.
- Each tool input schema produces a JSON Schema consumable by Anthropic's tool use API.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.schemas import (
    CheckSystemStatusInput,
    EscalateInput,
    EscalationSummary,
    Hypothesis,
    LookupUserInput,
    PolicyDecision,
    SearchHistoryInput,
    SearchKBInput,
    ToolResult,
    TraceEvent,
)


# --- Tool input schemas ----------------------------------------------------


def test_lookup_user_input_valid():
    assert LookupUserInput(user_id="u_001").user_id == "u_001"


def test_search_kb_input_default_top_k():
    assert SearchKBInput(query="vpn disconnect").top_k == 3


def test_search_kb_input_top_k_bounds():
    with pytest.raises(ValidationError):
        SearchKBInput(query="x", top_k=0)
    with pytest.raises(ValidationError):
        SearchKBInput(query="x", top_k=11)


def test_check_system_status_input_valid():
    assert CheckSystemStatusInput(service="salesforce").service == "salesforce"


def test_search_history_default_filters_to_resolved():
    inp = SearchHistoryInput(query="vpn mtu")
    assert inp.include_states == ["resolved"]


def test_search_history_invalid_state_rejected():
    with pytest.raises(ValidationError):
        SearchHistoryInput(query="x", include_states=["bogus_state"])


def test_escalate_input_minimal():
    inp = EscalateInput(
        policy_action="account_unlock",
        issue_summary="Account locked",
        urgency="high",
        suspected_cause="Multiple failed login attempts",
        recommended_team="Identity Access Management",
    )
    assert inp.attempted_steps == []
    assert inp.policy_action == "account_unlock"


def test_escalate_input_invalid_policy_action_rejected():
    with pytest.raises(ValidationError):
        EscalateInput(
            policy_action="grant_everything_now",
            issue_summary="x",
            urgency="normal",
            suspected_cause="x",
            recommended_team="x",
        )


def test_escalate_input_invalid_urgency_rejected():
    with pytest.raises(ValidationError):
        EscalateInput(
            policy_action="general_troubleshooting",
            issue_summary="x",
            urgency="critical",
            suspected_cause="x",
            recommended_team="x",
        )


def test_input_schemas_forbid_extra_fields():
    with pytest.raises(ValidationError):
        LookupUserInput(user_id="u_001", extra_arg="oops")


# --- Tool result -----------------------------------------------------------


def test_tool_result_success_payload():
    r = ToolResult(name="lookup_user", success=True, data={"user_id": "u_001"})
    assert r.error is None
    assert r.data == {"user_id": "u_001"}


def test_tool_result_error_payload():
    r = ToolResult(name="lookup_user", success=False, error="not found")
    assert r.data is None


def test_tool_result_negative_latency_rejected():
    with pytest.raises(ValidationError):
        ToolResult(name="x", success=True, latency_ms=-1.0)


# --- Hypothesis ------------------------------------------------------------


def test_hypothesis_confidence_in_range():
    h = Hypothesis(statement="MTU mismatch", confidence=0.72)
    assert h.confidence == 0.72


def test_hypothesis_confidence_above_one_rejected():
    with pytest.raises(ValidationError):
        Hypothesis(statement="x", confidence=1.5)


def test_hypothesis_confidence_negative_rejected():
    with pytest.raises(ValidationError):
        Hypothesis(statement="x", confidence=-0.1)


# --- Policy decision -------------------------------------------------------


def test_policy_decision_mirrors_policies_json_fields():
    d = PolicyDecision(
        action="mfa_reset",
        agent_allowed=False,
        risk_level="high",
        requires=["iam_team"],
        escalate_to="Identity Access Management",
        rationale="MFA bypass is a critical attack vector",
    )
    assert d.agent_allowed is False
    assert d.risk_level == "high"


def test_policy_decision_invalid_risk_level_rejected():
    with pytest.raises(ValidationError):
        PolicyDecision(
            action="x",
            agent_allowed=True,
            risk_level="critical",
            rationale="x",
        )


# --- Escalation summary ----------------------------------------------------


def _sample_summary() -> EscalationSummary:
    policy_decision = PolicyDecision(
        action="account_unlock",
        agent_allowed=False,
        risk_level="high",
        requires=["iam_team"],
        escalate_to="Identity Access Management",
        rationale="Account unlocks require IAM review.",
    )
    return EscalationSummary(
        handoff_id="ESC-20260517-001",
        created_at=datetime(2026, 5, 17, 14, 30, tzinfo=timezone.utc),
        user_id="u_001",
        user_name="Alice Chen",
        issue_summary="Cannot log into Okta; account locked",
        urgency="high",
        services_involved=["okta"],
        tools_consulted=["lookup_user", "check_system_status"],
        attempted_steps=["Confirmed account_locked=true via lookup_user"],
        suspected_cause="Multiple failed login attempts triggered Okta lockout",
        recommended_team="Identity Access Management",
        policy_action="account_unlock",
        policy_decision=policy_decision,
    )


def test_escalation_summary_round_trip():
    s = _sample_summary()
    restored = EscalationSummary.model_validate_json(s.model_dump_json())
    assert restored == s


# --- Trace event -----------------------------------------------------------


def test_trace_event_round_trip():
    e = TraceEvent(
        timestamp=datetime(2026, 5, 17, 14, 30, tzinfo=timezone.utc),
        event_type="tool_call",
        conversation_id="conv_001",
        payload={"tool": "lookup_user", "args": {"user_id": "u_001"}},
    )
    restored = TraceEvent.model_validate_json(e.model_dump_json())
    assert restored == e


def test_trace_event_invalid_type_rejected():
    with pytest.raises(ValidationError):
        TraceEvent(
            timestamp=datetime.now(timezone.utc),
            event_type="bogus_event",
            conversation_id="x",
        )


# --- JSON schema generation (consumed by Anthropic tool use) ---------------


def test_tool_input_json_schemas_compile():
    """Each tool input must produce a JSON-serializable schema for Anthropic."""
    for cls in (
        LookupUserInput,
        SearchKBInput,
        CheckSystemStatusInput,
        SearchHistoryInput,
        EscalateInput,
    ):
        schema = cls.model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        json.dumps(schema)
