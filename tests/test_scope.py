"""Tests for the lightweight out-of-scope guard."""

from __future__ import annotations

from agent.orchestrator import run_turn
from agent.scope import classify_scope, out_of_scope_reply
from agent.state import ConversationState


def test_classify_personal_equipment_as_out_of_scope():
    decision = classify_scope("How do I set up my personal fax machine at home?")

    assert decision.out_of_scope is True
    assert decision.category == "personal_device"


def test_classify_hr_question_as_out_of_scope():
    decision = classify_scope("Can you explain the PTO and vacation policy?")

    assert decision.out_of_scope is True
    assert decision.category == "hr"


def test_ambiguous_workplace_problem_stays_in_agent_flow():
    decision = classify_scope("Something at work isn't loading right.")

    assert decision.out_of_scope is False


def test_out_of_scope_reply_invites_company_it_reframe():
    decision = classify_scope("Can you review this NDA?")
    reply = out_of_scope_reply(decision)

    assert "company IT systems" in reply
    assert "company-managed device" in reply


def test_run_turn_short_circuits_clear_out_of_scope_without_tools():
    state = ConversationState(user_id="u_002")

    reply = run_turn(
        state,
        "How do I set up the fax machine I bought for my home office?",
    )

    assert "outside that scope" in reply
    assert state.investigation == []
    assert state.escalated is False
    assert state.messages[-1]["role"] == "assistant"
