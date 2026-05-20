"""ConversationState — single source of truth for one IT support conversation.

The agent loop mutates this object in place. Each turn appends to `messages`,
`investigation`, and `hypotheses`; on escalation the orchestrator calls
`mark_escalated()` and the loop terminates.

Messages follow Anthropic's API shape (role + content blocks) so the list can
be passed straight to `client.messages.create(messages=...)`. Investigation
and hypotheses live alongside the message log for traceability and for
constructing the escalation handoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent.schemas import EscalationSummary, Hypothesis, ToolResult


def _new_conversation_id() -> str:
    return f"conv_{uuid4().hex[:8]}"


class ConversationState(BaseModel):
    """All mutable state for one ongoing IT support conversation."""

    model_config = ConfigDict(extra="forbid")

    # Identity
    conversation_id: str = Field(default_factory=_new_conversation_id)
    user_id: str
    user_record: dict[str, Any] | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Anthropic-shaped message history (roles: user / assistant; content can be
    # str or a list of content blocks)
    messages: list[dict[str, Any]] = Field(default_factory=list)

    # Investigation trail — every tool call's result, in order
    investigation: list[ToolResult] = Field(default_factory=list)

    # Working hypotheses the agent has formed
    hypotheses: list[Hypothesis] = Field(default_factory=list)

    # Termination state
    escalated: bool = False
    escalation: EscalationSummary | None = None
    finished: bool = False

    # ---- Mutations ---------------------------------------------------------

    def add_user_message(self, text: str) -> None:
        """Append a plain-text user message."""
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, content: list[dict[str, Any]] | str) -> None:
        """Append the assistant's response.

        `content` is either a plain string (when only text was returned) or a list
        of content blocks (text + tool_use), matching Anthropic's response shape.
        """
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results_message(self, results: list[dict[str, Any]]) -> None:
        """Append a user-role message whose content is a list of tool_result blocks.

        Each block has the shape:
            {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": bool}
        """
        self.messages.append({"role": "user", "content": results})

    def record_tool_result(self, result: ToolResult) -> None:
        """Track a tool execution for the investigation log + escalation handoff."""
        self.investigation.append(result)

    def add_hypothesis(self, h: Hypothesis) -> None:
        self.hypotheses.append(h)

    def mark_escalated(self, escalation: EscalationSummary) -> None:
        self.escalated = True
        self.escalation = escalation
        self.finished = True

    # ---- Derived views -----------------------------------------------------

    def tools_consulted(self) -> list[str]:
        """Distinct tool names called so far, in first-call order."""
        seen: list[str] = []
        for r in self.investigation:
            if r.name not in seen:
                seen.append(r.name)
        return seen

    def services_touched(self) -> list[str]:
        """Distinct service names referenced by successful check_system_status calls."""
        services: list[str] = []
        for r in self.investigation:
            if r.name != "check_system_status" or not r.success:
                continue
            if not isinstance(r.data, dict):
                continue
            svc = r.data.get("service") or r.data.get("name")
            if isinstance(svc, str) and svc not in services:
                services.append(svc)
        return services

    def to_anthropic_messages(self) -> list[dict[str, Any]]:
        """Return the messages list in the shape expected by Anthropic's API."""
        return list(self.messages)

    def system_context(self) -> str:
        """One-line addendum identifying the current user, appended to the system prompt.

        This is what tells the agent which `user_id` to pass to `lookup_user` and
        provides quick situational context (role, location, priority) without
        requiring an extra round-trip just to learn who's on the other end.
        """
        if self.user_record is None:
            return f"# Current conversation\n\nuser_id: {self.user_id} (profile not yet loaded)"
        rec = self.user_record
        lines = [
            "# Current conversation",
            "",
            f"You are talking with user_id `{self.user_id}`.",
            "",
            "Their directory record (already retrieved for you, but call `lookup_user` if you "
            "need the full record including permissions or account_locked status):",
            "",
            f"- Name: {rec.get('name', 'unknown')}",
            f"- Role: {rec.get('role', 'unknown')}",
            f"- Department: {rec.get('department', 'unknown')}",
            f"- Location: {rec.get('location', 'unknown')}",
            f"- Priority: {rec.get('priority', 'unknown')}",
        ]
        return "\n".join(lines)
