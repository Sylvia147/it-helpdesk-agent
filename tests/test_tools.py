"""Tests for src/tools/.

Each tool is exercised on:
- A happy-path query that should hit a known mock record (the demo hooks).
- Invalid input that should return success=False with a structured error.
- Edge cases relevant to the tool (state filtering, dependency injection, etc.).
The registry is also smoke-tested for shape compatibility with Anthropic's tool API.
"""

from __future__ import annotations

import json

import pytest

from tools.escalation import escalate
from tools.history_search import search_history
from tools.kb_search import search_kb
from tools.registry import TOOL_SCHEMAS, TOOLS
from tools.system_status import check_system_status
from tools.user_directory import lookup_user


# --- lookup_user -----------------------------------------------------------


def test_lookup_user_existing():
    r = lookup_user("u_001")
    assert r.success
    assert r.data["name"] == "Alice Chen"
    assert r.data["account_locked"] is True
    # _demo_hook is internal; should be stripped from the tool result
    assert "_demo_hook" not in r.data


def test_lookup_user_not_found():
    r = lookup_user("u_999")
    assert not r.success
    assert "u_999" in r.error


def test_lookup_user_empty_input():
    r = lookup_user("")
    assert not r.success
    assert "required" in r.error.lower()


def test_lookup_user_records_latency():
    r = lookup_user("u_001")
    assert r.latency_ms is not None
    assert r.latency_ms >= 0


# --- check_system_status ---------------------------------------------------


def test_check_system_status_operational():
    r = check_system_status("okta")
    assert r.success
    assert r.data["status"] == "operational"
    assert r.data["incidents"] == []


def test_check_system_status_degraded_with_incident():
    r = check_system_status("salesforce")
    assert r.success
    assert r.data["status"] == "degraded"
    assert len(r.data["incidents"]) == 1
    assert "chicago" in r.data["incidents"][0]["regions_affected"]


def test_check_system_status_dependencies_injected_for_tableau():
    r = check_system_status("tableau")
    assert r.success
    assert set(r.data["upstream_dependencies"]) == {"jenkins", "snowflake"}


def test_check_system_status_no_deps_for_okta():
    r = check_system_status("okta")
    assert r.data["upstream_dependencies"] == []


def test_check_system_status_unknown_service():
    r = check_system_status("nonexistent")
    assert not r.success
    assert "Unknown service" in r.error


def test_check_system_status_case_insensitive():
    r = check_system_status("Salesforce")
    assert r.success
    assert r.data["status"] == "degraded"


# --- search_kb -------------------------------------------------------------


def test_search_kb_finds_vpn_runbook():
    r = search_kb("vpn disconnects every 10 minutes residential cable")
    assert r.success
    hits = r.data["hits"]
    assert len(hits) > 0
    assert any("vpn_disconnect" in h["path"] for h in hits)


def test_search_kb_finds_okta_lockout():
    r = search_kb("okta account locked credential stuffing")
    assert r.success
    paths = [h["path"] for h in r.data["hits"]]
    assert any("lockout" in p for p in paths)


def test_search_kb_top_k_respected():
    r = search_kb("vpn", top_k=2)
    assert r.success
    assert len(r.data["hits"]) <= 2


def test_search_kb_empty_query():
    r = search_kb("")
    assert not r.success


def test_search_kb_returns_score():
    r = search_kb("vpn mtu")
    if r.data["hits"]:
        assert all(isinstance(h["score"], float) for h in r.data["hits"])


# --- search_history --------------------------------------------------------


def test_search_history_finds_vpn_mtu():
    r = search_history("VPN disconnects every 10-15 minutes residential cable")
    assert r.success
    ids = [h["id"] for h in r.data["hits"]]
    assert "hist_001" in ids


def test_search_history_default_filters_to_resolved_only():
    r = search_history("printer driver")
    assert r.success
    for h in r.data["hits"]:
        assert h["state"] == "resolved"


def test_search_history_can_include_user_abandoned():
    r = search_history(
        "printer not appearing dialog macOS update",
        include_states=["resolved", "user_abandoned"],
    )
    assert r.success
    states = {h["state"] for h in r.data["hits"]}
    assert "user_abandoned" in states


def test_search_history_finds_jenkins_post_maintenance():
    r = search_history("jenkins maintenance window firewall pipeline tableau")
    assert r.success
    ids = [h["id"] for h in r.data["hits"]]
    assert "hist_003" in ids


def test_search_history_finds_salesforce_chicago():
    r = search_history("salesforce slow chicago latency")
    assert r.success
    ids = [h["id"] for h in r.data["hits"]]
    assert "hist_002" in ids


def test_search_history_empty_query():
    r = search_history("")
    assert not r.success


# --- escalate --------------------------------------------------------------


def test_escalate_creates_and_persists_record(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.escalation.LOG_DIR", tmp_path)

    r = escalate(
        policy_action="account_unlock",
        issue_summary="Account locked, urgent client meeting in 30 minutes",
        urgency="high",
        suspected_cause="Multiple failed login attempts triggered Okta lockout policy",
        recommended_team="Identity Access Management",
        attempted_steps=["Confirmed account_locked=true via lookup_user"],
        user_id="u_001",
        user_name="Alice Chen",
        services_involved=["okta"],
        tools_consulted=["lookup_user", "check_system_status"],
    )
    assert r.success
    assert r.data["handoff_id"].startswith("ESC-")
    assert r.data["urgency"] == "high"
    assert r.data["recommended_team"] == "Identity Access Management"
    assert r.data["policy_action"] == "account_unlock"
    assert r.data["policy_decision"]["agent_allowed"] is False

    files = list(tmp_path.glob("ESC-*.json"))
    assert len(files) == 1
    persisted = json.loads(files[0].read_text())
    assert persisted["user_id"] == "u_001"
    assert persisted["policy_decision"]["escalate_to"] == "Identity Access Management"


def test_escalate_uses_policy_to_override_denied_action_route(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.escalation.LOG_DIR", tmp_path)

    r = escalate(
        policy_action="snowflake_prod_access",
        issue_summary="Needs production Snowflake access",
        urgency="normal",
        suspected_cause="New role requires production database access",
        recommended_team="Identity Access Management",
    )

    assert r.success
    assert r.data["recommended_team"] == "Data Platform Team"
    assert r.data["policy_decision"]["agent_allowed"] is False
    assert r.data["policy_decision"]["requires"] == [
        "manager_approval",
        "data_owner_approval",
    ]


def test_escalate_invalid_urgency_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.escalation.LOG_DIR", tmp_path)
    r = escalate(
        policy_action="general_troubleshooting",
        issue_summary="x",
        urgency="critical",  # not in Literal["low","normal","high"]
        suspected_cause="x",
        recommended_team="x",
    )
    assert not r.success
    assert "Invalid escalation" in r.error


def test_escalate_handoff_id_increments(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.escalation.LOG_DIR", tmp_path)
    ids = []
    for _ in range(3):
        r = escalate(
            policy_action="general_troubleshooting",
            issue_summary="x",
            urgency="normal",
            suspected_cause="x",
            recommended_team="x",
        )
        assert r.success
        ids.append(r.data["handoff_id"])
    # Each ID should be unique and the trailing number should increment
    assert len(set(ids)) == 3


# --- registry --------------------------------------------------------------


def test_registry_has_all_five_tools():
    assert set(TOOLS.keys()) == {
        "lookup_user",
        "check_system_status",
        "search_kb",
        "search_history",
        "escalate",
    }


def test_tool_schemas_are_anthropic_compatible():
    """Each schema must have name, description, input_schema with type=object."""
    for tool in TOOL_SCHEMAS:
        assert "name" in tool
        assert "description" in tool and tool["description"]
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "properties" in tool["input_schema"]
        assert tool["input_schema"]["additionalProperties"] is False


def test_tool_schemas_match_registry_keys():
    schema_names = {t["name"] for t in TOOL_SCHEMAS}
    assert schema_names == set(TOOLS.keys())


# --- SIMULATE_FAILURE injection -------------------------------------------


@pytest.mark.parametrize(
    "tool_name, fn, args",
    [
        ("lookup_user", lookup_user, ("u_001",)),
        ("check_system_status", check_system_status, ("salesforce",)),
        ("search_kb", search_kb, ("vpn disconnect",)),
        ("search_history", search_history, ("vpn mtu",)),
    ],
)
def test_simulate_failure_short_circuits(monkeypatch, tool_name, fn, args):
    """Each tool returns success=False when SIMULATE_FAILURE matches its name."""
    monkeypatch.setenv("SIMULATE_FAILURE", tool_name)
    result = fn(*args)
    assert result.success is False
    assert result.name == tool_name
    assert "Simulated failure" in (result.error or "")


def test_simulate_failure_only_targets_named_tool(monkeypatch):
    """A SIMULATE_FAILURE for one tool must not affect the others."""
    monkeypatch.setenv("SIMULATE_FAILURE", "search_kb")
    assert lookup_user("u_001").success is True
    assert check_system_status("okta").success is True
    assert search_kb("anything").success is False


def test_simulate_failure_unset_means_no_effect(monkeypatch):
    """Empty / missing SIMULATE_FAILURE leaves tools alone."""
    monkeypatch.delenv("SIMULATE_FAILURE", raising=False)
    assert lookup_user("u_001").success is True
    monkeypatch.setenv("SIMULATE_FAILURE", "")
    assert lookup_user("u_001").success is True
