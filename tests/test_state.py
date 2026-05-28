"""Tests for src/agent/state.py — ConversationState shape, mutations, derived views."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.schemas import EscalationSummary, PolicyDecision, ToolResult
from agent.state import ConversationState


# --- Construction --------------------------------------------------------


def test_minimal_construction_only_requires_user_id():
    s = ConversationState(user_id="u_001")
    assert s.user_id == "u_001"
    assert s.messages == []
    assert s.investigation == []
    assert s.escalated is False
    assert s.finished is False


def test_conversation_id_auto_generated():
    s = ConversationState(user_id="u_001")
    assert re.match(r"^conv_[0-9a-f]{8}$", s.conversation_id)


def test_two_states_get_distinct_conversation_ids():
    a = ConversationState(user_id="u_001")
    b = ConversationState(user_id="u_001")
    assert a.conversation_id != b.conversation_id


def test_started_at_is_utc():
    s = ConversationState(user_id="u_001")
    assert s.started_at.tzinfo is not None


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ConversationState(user_id="u_001", oops="extra")


# --- Message appending ---------------------------------------------------


def test_add_user_message_appends_role_user():
    s = ConversationState(user_id="u_001")
    s.add_user_message("Hello, my VPN is broken")
    assert s.messages == [{"role": "user", "content": "Hello, my VPN is broken"}]


def test_add_assistant_message_with_string_content():
    s = ConversationState(user_id="u_001")
    s.add_assistant_message("I'll help you troubleshoot.")
    assert s.messages[0]["role"] == "assistant"
    assert s.messages[0]["content"] == "I'll help you troubleshoot."


def test_add_assistant_message_with_content_blocks():
    s = ConversationState(user_id="u_001")
    blocks = [
        {"type": "text", "text": "Looking into it"},
        {"type": "tool_use", "id": "tu_1", "name": "lookup_user", "input": {"user_id": "u_001"}},
    ]
    s.add_assistant_message(blocks)
    assert s.messages[0]["content"] == blocks


def test_add_tool_results_message_appends_user_role():
    s = ConversationState(user_id="u_001")
    s.add_tool_results_message(
        [{"type": "tool_result", "tool_use_id": "tu_1", "content": "..."}]
    )
    msg = s.messages[0]
    assert msg["role"] == "user"
    assert msg["content"][0]["type"] == "tool_result"


# --- Investigation tracking ----------------------------------------------


def test_record_tool_result_appends():
    s = ConversationState(user_id="u_001")
    s.record_tool_result(ToolResult(name="lookup_user", success=True, data={"user_id": "u_001"}))
    s.record_tool_result(ToolResult(name="search_kb", success=True, data={"hits": []}))
    assert len(s.investigation) == 2


def test_tools_consulted_dedupes_in_first_call_order():
    s = ConversationState(user_id="u_001")
    for name in ["lookup_user", "search_kb", "lookup_user", "check_system_status", "search_kb"]:
        s.record_tool_result(ToolResult(name=name, success=True, data={}))
    assert s.tools_consulted() == ["lookup_user", "search_kb", "check_system_status"]


def test_services_touched_extracts_from_check_system_status():
    s = ConversationState(user_id="u_001")
    s.record_tool_result(
        ToolResult(name="check_system_status", success=True, data={"service": "Salesforce"})
    )
    s.record_tool_result(
        ToolResult(name="check_system_status", success=True, data={"service": "Jenkins"})
    )
    s.record_tool_result(
        ToolResult(name="lookup_user", success=True, data={"user_id": "u_001"})
    )
    assert s.services_touched() == ["Salesforce", "Jenkins"]


def test_services_touched_skips_failed_calls():
    s = ConversationState(user_id="u_001")
    s.record_tool_result(
        ToolResult(name="check_system_status", success=False, error="not found")
    )
    assert s.services_touched() == []


# --- Escalation ----------------------------------------------------------


def _sample_escalation() -> EscalationSummary:
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
        issue_summary="Account locked",
        urgency="high",
        services_involved=["okta"],
        tools_consulted=["lookup_user"],
        attempted_steps=[],
        suspected_cause="Failed login attempts",
        recommended_team="Identity Access Management",
        policy_action="account_unlock",
        policy_decision=policy_decision,
    )


def test_mark_escalated_sets_state():
    s = ConversationState(user_id="u_001")
    s.mark_escalated(_sample_escalation())
    assert s.escalated is True
    assert s.escalation is not None
    assert s.escalation.handoff_id == "ESC-20260517-001"
    assert s.finished is True


# --- Anthropic message export --------------------------------------------


def test_to_anthropic_messages_returns_messages_copy():
    s = ConversationState(user_id="u_001")
    s.add_user_message("hi")
    out = s.to_anthropic_messages()
    assert out == s.messages
    out.append({"role": "user", "content": "leak"})
    # Original messages unaffected
    assert len(s.messages) == 1


# --- system_context ------------------------------------------------------


def test_system_context_without_record_still_includes_user_id():
    s = ConversationState(user_id="u_999")
    ctx = s.system_context()
    assert "u_999" in ctx
    assert "not yet loaded" in ctx


def test_system_context_with_record_includes_profile_fields():
    s = ConversationState(
        user_id="u_003",
        user_record={
            "name": "Carol Wang",
            "role": "Senior Software Engineer",
            "department": "Engineering",
            "location": "Remote (San Francisco, CA)",
            "priority": "normal",
        },
    )
    ctx = s.system_context()
    assert "u_003" in ctx
    assert "Carol Wang" in ctx
    assert "Engineering" in ctx
    assert "Remote (San Francisco, CA)" in ctx


# --- JSON serialization --------------------------------------------------


def test_full_round_trip_through_json():
    s = ConversationState(user_id="u_001", user_record={"name": "Alice", "department": "Sales"})
    s.add_user_message("VPN broken")
    s.record_tool_result(ToolResult(name="lookup_user", success=True, data={"user_id": "u_001"}))
    s.mark_escalated(_sample_escalation())

    raw = s.model_dump_json()
    restored = ConversationState.model_validate_json(raw)
    assert restored == s
