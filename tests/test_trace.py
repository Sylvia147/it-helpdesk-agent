"""Tests for src/agent/trace.py — Tracer summarizers and JSONL persistence."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from agent.schemas import EscalationSummary, PolicyDecision, ToolResult
from agent.trace import Tracer


# Use a non-rendering console with output captured
def _silent_console() -> Console:
    return Console(record=True, width=120)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- summarizers -----------------------------------------------------------


def test_summarize_lookup_user_includes_locked_flag():
    r = ToolResult(
        name="lookup_user",
        success=True,
        data={"name": "Alice Chen", "location": "Chicago, IL", "account_locked": True},
    )
    s = Tracer._summarize_success(r)
    assert "Alice Chen" in s
    assert "locked=True" in s


def test_summarize_check_system_status_lists_incidents_and_changes():
    r = ToolResult(
        name="check_system_status",
        success=True,
        data={
            "service": "Salesforce",
            "status": "degraded",
            "incidents": [{"incident_id": "x"}],
            "recent_changes": [],
        },
    )
    s = Tracer._summarize_success(r)
    assert "Salesforce" in s
    assert "status=degraded" in s
    assert "1 incident(s)" in s
    assert "0 change(s)" in s


def test_summarize_search_kb_with_top_hit():
    r = ToolResult(
        name="search_kb",
        success=True,
        data={"hits": [{"article_id": "KB-NET-001", "score": 7.2}, {}, {}]},
    )
    s = Tracer._summarize_success(r)
    assert "3 hit(s)" in s
    assert "KB-NET-001" in s


def test_summarize_no_hits():
    r = ToolResult(name="search_history", success=True, data={"hits": []})
    s = Tracer._summarize_success(r)
    assert "no hits" in s


# --- JSONL persistence -----------------------------------------------------


def test_user_message_event_persisted(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False)
    t.user_message("Salesforce is slow")

    rows = _read_jsonl(log)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "user_message"
    assert rows[0]["payload"]["text"] == "Salesforce is slow"


def test_assistant_message_event_persisted(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False)
    t.assistant_message("This is a known incident.")

    rows = _read_jsonl(log)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "assistant_message"
    assert rows[0]["payload"]["text"] == "This is a known incident."


def test_tool_call_event_persisted(tmp_path):
    log = tmp_path / "traces.jsonl"
    conv_dir = tmp_path / "conversations"
    t = Tracer(
        "conv_test",
        console=_silent_console(),
        log_path=log,
        conversation_log_dir=conv_dir,
        render=False,
    )
    t.tool_call("lookup_user", {"user_id": "u_001"})

    rows = _read_jsonl(log)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "tool_call"
    assert rows[0]["conversation_id"] == "conv_test"
    assert rows[0]["payload"]["name"] == "lookup_user"
    assert rows[0]["payload"]["input"] == {"user_id": "u_001"}

    conv_rows = _read_jsonl(conv_dir / "conv_test.jsonl")
    assert conv_rows == rows


def test_tool_result_event_records_success(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False)
    t.tool_result(
        ToolResult(
            name="check_system_status",
            success=True,
            data={"service": "Okta", "status": "operational", "incidents": []},
            latency_ms=2.5,
        )
    )

    rows = _read_jsonl(log)
    assert rows[0]["event_type"] == "tool_result"
    assert rows[0]["payload"]["success"] is True
    assert rows[0]["payload"]["latency_ms"] == 2.5
    assert rows[0]["payload"]["data"] == {
        "service": "Okta",
        "status": "operational",
        "incidents": [],
    }
    assert rows[0]["payload"]["data_summary"] is not None


def test_tool_result_event_records_error(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False)
    t.tool_result(
        ToolResult(name="search_kb", success=False, error="empty query")
    )

    rows = _read_jsonl(log)
    assert rows[0]["payload"]["success"] is False
    assert rows[0]["payload"]["error"] == "empty query"
    assert rows[0]["payload"]["data_summary"] is None


def test_escalation_event_serialized(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False)

    summary = EscalationSummary(
        handoff_id="ESC-20260517-001",
        created_at="2026-05-17T14:30:00+00:00",
        user_id="u_001",
        user_name="Alice",
        issue_summary="Account locked",
        urgency="high",
        services_involved=["okta"],
        tools_consulted=["lookup_user"],
        attempted_steps=[],
        suspected_cause="Failed login attempts",
        recommended_team="Identity Access Management",
        policy_action="account_unlock",
        policy_decision=PolicyDecision(
            action="account_unlock",
            agent_allowed=False,
            risk_level="high",
            requires=["iam_team"],
            escalate_to="Identity Access Management",
            rationale="Account unlocks require IAM review.",
        ),
    )
    t.escalation(summary)

    rows = _read_jsonl(log)
    assert rows[0]["event_type"] == "escalation"
    assert rows[0]["payload"]["handoff_id"] == "ESC-20260517-001"
    assert rows[0]["payload"]["recommended_team"] == "Identity Access Management"


def test_multiple_events_accumulate(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False)
    t.tool_call("lookup_user", {"user_id": "u_001"})
    t.tool_result(ToolResult(name="lookup_user", success=True, data={"name": "Alice"}))
    t.tool_call("search_kb", {"query": "vpn", "top_k": 3})

    rows = _read_jsonl(log)
    assert len(rows) == 3
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result", "tool_call"]


# --- render switch ---------------------------------------------------------


def test_render_false_does_not_print(tmp_path):
    log = tmp_path / "traces.jsonl"
    console = _silent_console()
    t = Tracer("conv_test", console=console, log_path=log, render=False)
    t.tool_call("lookup_user", {"user_id": "u_001"})
    # Nothing should have been printed
    assert console.export_text() == ""


def test_persist_false_does_not_write(tmp_path):
    log = tmp_path / "traces.jsonl"
    t = Tracer("conv_test", console=_silent_console(), log_path=log, render=False, persist=False)
    t.tool_call("lookup_user", {"user_id": "u_001"})
    assert not log.exists()
