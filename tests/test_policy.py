"""Tests for src/agent/policy.py."""

from __future__ import annotations

from agent.policy import check_action, list_actions
from agent.schemas import PolicyDecision


# --- Specific high-stakes actions -----------------------------------------


def test_password_reset_guidance_is_low_risk_allowed():
    d = check_action("password_reset_guidance")
    assert d.agent_allowed is True
    assert d.risk_level == "low"
    assert d.escalate_to is None


def test_mfa_reset_is_high_risk_forbidden():
    d = check_action("mfa_reset")
    assert d.agent_allowed is False
    assert d.risk_level == "high"
    assert d.escalate_to == "Identity Access Management"


def test_account_unlock_requires_iam():
    d = check_action("account_unlock")
    assert d.agent_allowed is False
    assert "iam_team" in d.requires
    assert d.escalate_to == "Identity Access Management"


def test_snowflake_prod_requires_two_approvals():
    d = check_action("snowflake_prod_access")
    assert d.agent_allowed is False
    assert "manager_approval" in d.requires
    assert "data_owner_approval" in d.requires
    assert d.escalate_to == "Data Platform Team"


def test_grafana_readonly_is_self_service():
    d = check_action("grafana_readonly_access")
    assert d.agent_allowed is True
    assert d.risk_level == "low"


def test_production_incident_investigation_forbidden():
    d = check_action("production_incident_investigation")
    assert d.agent_allowed is False
    assert d.risk_level == "high"


# --- Default-deny path ----------------------------------------------------


def test_unknown_action_defaults_to_deny():
    d = check_action("delete_all_user_data")
    assert d.agent_allowed is False
    assert d.risk_level == "high"
    assert d.escalate_to == "IT Service Desk"
    assert "not in the policy table" in d.rationale


def test_unknown_action_echoes_action_name():
    d = check_action("some_made_up_action")
    assert d.action == "some_made_up_action"


def test_empty_string_action_also_denied():
    d = check_action("")
    assert d.agent_allowed is False


# --- Coverage / shape -----------------------------------------------------


def test_all_12_known_actions_return_valid_decisions():
    """Every action in policies.json must produce a valid PolicyDecision."""
    for action in list_actions():
        d = check_action(action)
        assert isinstance(d, PolicyDecision)
        assert d.action == action
        # rationale must always be present and non-empty
        assert d.rationale.strip() != ""


def test_list_actions_returns_at_least_known_critical_actions():
    actions = set(list_actions())
    must_have = {"mfa_reset", "account_unlock", "snowflake_prod_access"}
    assert must_have.issubset(actions)


def test_returned_decision_type_is_pydantic_model():
    d = check_action("password_reset_guidance")
    assert isinstance(d, PolicyDecision)
    # And it round-trips through JSON cleanly
    restored = PolicyDecision.model_validate_json(d.model_dump_json())
    assert restored == d
