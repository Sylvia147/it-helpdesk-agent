"""Pydantic schemas for tool I/O, agent reasoning state, policy decisions, and trace events.

Conventions:
- Tool input schemas (*Input) are converted to JSON Schema for Anthropic's tool use API
  via .model_json_schema(). Their field descriptions become the tool documentation the
  model sees.
- All models forbid extra fields, so a hallucinated argument or typo is caught at the
  validation boundary instead of propagating into the agent loop.
- PolicyDecision deliberately mirrors the field naming in data/policies.json so the
  policy engine is a thin filter, not a translation layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Tool input schemas — converted to JSON Schema for Anthropic's tool use API
# ---------------------------------------------------------------------------


class LookupUserInput(BaseModel):
    """Look up an employee by their user_id."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(description="Employee identifier, e.g., 'u_001'.")


class SearchKBInput(BaseModel):
    """Full-text search across the IT knowledge base markdown articles."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        description="Free-text query, e.g., 'VPN disconnects every 10 minutes residential cable'."
    )
    top_k: int = Field(
        default=3, ge=1, le=10, description="Maximum number of articles to return."
    )


class CheckSystemStatusInput(BaseModel):
    """Get current status, active incidents, and recent changes for one service."""

    model_config = ConfigDict(extra="forbid")

    service: str = Field(
        description="Lowercase service name, e.g., 'okta', 'salesforce', 'jenkins'."
    )


HistoryState = Literal["resolved", "user_abandoned", "could_not_reproduce", "duplicate"]


class SearchHistoryInput(BaseModel):
    """Search past IT support tickets for similar issue patterns."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Free-text query describing the symptom or context.")
    top_k: int = Field(
        default=3, ge=1, le=10, description="Maximum number of cases to return."
    )
    include_states: list[HistoryState] = Field(
        default_factory=lambda: ["resolved"],
        description=(
            "Which terminal states to include. Defaults to 'resolved' only; broaden "
            "when stress-testing agent behavior on noisy archives."
        ),
    )


Urgency = Literal["low", "normal", "high"]
PolicyAction = Literal[
    "password_reset_guidance",
    "mfa_reset",
    "account_unlock",
    "vpn_troubleshooting_guidance",
    "saas_outage_communication",
    "snowflake_prod_access",
    "snowflake_dev_access",
    "grafana_readonly_access",
    "production_incident_investigation",
    "new_hardware_request",
    "software_license_request",
    "general_troubleshooting",
]


class EscalateInput(BaseModel):
    """Escalate the conversation to a human team with a structured handoff package."""

    model_config = ConfigDict(extra="forbid")

    policy_action: PolicyAction = Field(
        description=(
            "The policy action that triggered or justifies escalation. Choose the "
            "closest value from the policy table, e.g. 'account_unlock', "
            "'mfa_reset', 'snowflake_prod_access', or "
            "'production_incident_investigation'."
        )
    )
    issue_summary: str = Field(
        description="One-paragraph summary of the user's problem in your own words."
    )
    urgency: Urgency = Field(
        description="How urgent the user described it: 'low', 'normal', or 'high'."
    )
    suspected_cause: str = Field(
        description="Best current hypothesis. Use 'unknown' if you cannot form one."
    )
    recommended_team: str = Field(
        description="Team to route to, e.g., 'Identity Access Management', 'DevOps'."
    )
    attempted_steps: list[str] = Field(
        default_factory=list,
        description="Troubleshooting or clarification steps already tried with the user.",
    )


# ---------------------------------------------------------------------------
# Tool execution result — uniform shape every tool returns
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Uniform return shape for every tool. Consumed by both the agent loop and trace."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name of the tool that produced this result.")
    success: bool
    data: Any | None = Field(
        default=None, description="Result payload when success is True."
    )
    error: str | None = Field(
        default=None, description="Error message when success is False."
    )
    latency_ms: float | None = Field(
        default=None, ge=0, description="Wall-clock time spent inside the tool."
    )


# ---------------------------------------------------------------------------
# Agent reasoning state
# ---------------------------------------------------------------------------


class Hypothesis(BaseModel):
    """A working hypothesis the agent has formed during diagnosis."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(description="Plain-English description of the suspected cause.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Agent's confidence in this hypothesis, 0 to 1."
    )
    evidence: list[str] = Field(
        default_factory=list, description="Supporting evidence lines."
    )
    sources_used: list[str] = Field(
        default_factory=list,
        description="Tool names whose results contributed to this hypothesis.",
    )


# ---------------------------------------------------------------------------
# Policy engine decision — mirrors data/policies.json field naming
# ---------------------------------------------------------------------------


RiskLevel = Literal["low", "medium", "high"]


class PolicyDecision(BaseModel):
    """Result of looking up a policy action.

    Field names deliberately mirror data/policies.json so the policy engine is a thin
    filter rather than a translation layer.
    """

    model_config = ConfigDict(extra="forbid")

    action: str
    agent_allowed: bool
    risk_level: RiskLevel
    requires: list[str] = Field(default_factory=list)
    escalate_to: str | None = None
    rationale: str


# ---------------------------------------------------------------------------
# Escalation handoff package — written to logs/escalations/ on escalate
# ---------------------------------------------------------------------------


class EscalationSummary(BaseModel):
    """Complete handoff record produced when the agent escalates."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str = Field(description="Generated ID, e.g., 'ESC-20260517-001'.")
    created_at: datetime
    user_id: str
    user_name: str
    issue_summary: str
    urgency: Urgency
    services_involved: list[str] = Field(default_factory=list)
    tools_consulted: list[str] = Field(default_factory=list)
    attempted_steps: list[str] = Field(default_factory=list)
    suspected_cause: str
    recommended_team: str
    policy_action: str
    policy_decision: PolicyDecision


# ---------------------------------------------------------------------------
# Trace event — appended to logs/traces.jsonl, one row per event
# ---------------------------------------------------------------------------


TraceEventType = Literal[
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "hypothesis",
    "policy_check",
    "escalation",
]


class TraceEvent(BaseModel):
    """One row in logs/traces.jsonl. Payload shape varies by event_type."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    event_type: TraceEventType
    conversation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
