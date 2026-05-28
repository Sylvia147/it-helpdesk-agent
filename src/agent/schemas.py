"""Pydantic schemas for tool I/O, policy decisions, handoffs, and trace events.

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
# 工具输入模型：会被转换成 Anthropic tool schema，模型会看到这些字段说明。
# ---------------------------------------------------------------------------


class LookupUserInput(BaseModel):
    """Look up an employee by their user_id.

    lookup_user 的入参，只允许 user_id 这一个字段。
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(description="Employee identifier, e.g., 'u_001'.")


class SearchKBInput(BaseModel):
    """Full-text search across the IT knowledge base markdown articles.

    search_kb 的入参。top_k 有上下限，避免模型一次请求过多结果。
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        description="Free-text query, e.g., 'VPN disconnects every 10 minutes residential cable'."
    )
    top_k: int = Field(
        default=3, ge=1, le=10, description="Maximum number of articles to return."
    )


class CheckSystemStatusInput(BaseModel):
    """Get current status, active incidents, and recent changes for one service.

    check_system_status 的入参；service 是数据文件里的服务 key。
    """

    model_config = ConfigDict(extra="forbid")

    service: str = Field(
        description="Lowercase service name, e.g., 'okta', 'salesforce', 'jenkins'."
    )


HistoryState = Literal["resolved", "user_abandoned", "could_not_reproduce", "duplicate"]


class SearchHistoryInput(BaseModel):
    """Search past IT support tickets for similar issue patterns.

    search_history 的入参。默认只搜 resolved 历史案例，减少噪音。
    """

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
    """Escalate the conversation to a human team with a structured handoff package.

    escalate 的模型侧入参。注意 user_id、user_name、services_involved、
    tools_consulted 不在这里，因为这些事实字段由 orchestrator 从 state 注入。
    """

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
# 工具执行结果：所有工具统一返回这个结构，方便 orchestrator/trace 统一处理。
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Uniform return shape for every tool. Consumed by both the agent loop and trace.

    success=True 时看 data；success=False 时看 error。即使工具失败，
    也用同一个结构返回给 LLM，让模型能承认失败而不是编造结果。
    """

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
# Policy engine decision — mirrors data/policies.json field naming
# 策略判断结果：字段名刻意贴近 policies.json，让 policy.py 只做薄封装。
# ---------------------------------------------------------------------------


RiskLevel = Literal["low", "medium", "high"]


class PolicyDecision(BaseModel):
    """Result of looking up a policy action.

    Field names deliberately mirror data/policies.json so the policy engine is a thin
    filter rather than a translation layer.

    agent_allowed=False 表示 agent 不能直接执行，需要升级或给人工处理。
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
# 升级交接包：escalate 工具成功时写入 logs/escalations/*.json。
# ---------------------------------------------------------------------------


class EscalationSummary(BaseModel):
    """Complete handoff record produced when the agent escalates.

    这是给人工团队看的结构化摘要，包含用户、问题、紧急程度、已查工具、
    涉及服务、疑似原因、推荐团队和 policy 判断。
    """

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
# Trace 事件：每个工具调用/结果/升级都会写一行 JSONL，方便回放和排查。
# ---------------------------------------------------------------------------


TraceEventType = Literal[
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "policy_check",
    "escalation",
]


class TraceEvent(BaseModel):
    """One row in logs/traces.jsonl. Payload shape varies by event_type.

    payload 的具体字段取决于 event_type，例如 tool_call 会放 name/input，
    tool_result 会放 success/error/latency 等。
    """

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    event_type: TraceEventType
    conversation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
