"""ConversationState — single source of truth for one IT support conversation.

The agent loop mutates this object in place. Each turn appends to `messages`
and `investigation`; on escalation the orchestrator calls `mark_escalated()`
and the loop terminates.

Messages follow Anthropic's API shape (role + content blocks) so the list can
be passed straight to `client.messages.create(messages=...)`. Investigation
lives alongside the message log for traceability and for constructing the
escalation handoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
# Generate unique conversation IDs for each chat session.
# 为每次会话生成唯一 conversation_id，方便 trace / handoff 对齐。
from uuid import uuid4

# Pydantic provides typed state models; Field(default_factory=...) is used
# for fresh defaults like lists so conversations do not share mutable state.
# Pydantic 负责字段类型、默认值和校验；default_factory 用来给每个
#     ConversationState 创建独立 list，避免多个会话共享同一个可变对象。
from pydantic import BaseModel, ConfigDict, Field

from agent.schemas import EscalationSummary, ToolResult


def _new_conversation_id() -> str:
    return f"conv_{uuid4().hex[:8]}"


class ConversationState(BaseModel):
    """All mutable state for one ongoing IT support conversation.

    这是“一次聊天”的状态容器。main.py 创建它，orchestrator.py 在每轮
    对话中不断修改它，tools 本身不保存会话状态。
    """

    # Reject unexpected fields so conversation state stays predictable.
    # 禁止传入未定义字段，避免 state 里混入难追踪的脏数据。
    model_config = ConfigDict(extra="forbid")

    # Identity/profile fields for the current caller.
    # 当前用户身份字段；user_record 是目录里查到的完整/基础用户资料。
    conversation_id: str = Field(default_factory=_new_conversation_id)
    user_id: str
    user_record: dict[str, Any] | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Anthropic-shaped message history. Roles are user/assistant; content can
    # be plain text or Anthropic content blocks such as tool_use/tool_result.
    # 给 Anthropic API 用的完整消息历史；每次 LLM 调用都会传它。
    messages: list[dict[str, Any]] = Field(default_factory=list)

    # Investigation trail: every tool result in order, used for trace/handoff.
    # 工具调用结果流水账；升级人工时会用它整理 tools/services 摘要。
    investigation: list[ToolResult] = Field(default_factory=list)

    # Termination state. Escalation ends the CLI loop.
    # 会话结束状态；升级成功后 finished=True，main.py 的 while 循环会停止。
    escalated: bool = False
    escalation: EscalationSummary | None = None
    finished: bool = False

    # ---- Mutations ---------------------------------------------------------

    def add_user_message(self, text: str) -> None:
        """Append a plain-text user message.

        用户输入永远以 role=user 写入 Anthropic message history。
        """
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, content: list[dict[str, Any]] | str) -> None:
        """Append the assistant's response.

        `content` is either a plain string (when only text was returned) or a list
        of content blocks (text + tool_use), matching Anthropic's response shape.

        assistant 可能只回复文本，也可能回复 text + tool_use block。
        tool_use 必须保留在 history 里，后续 tool_result 才能对上。
        """
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results_message(self, results: list[dict[str, Any]]) -> None:
        """Append a user-role message whose content is a list of tool_result blocks.

        Each block has the shape:
            {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": bool}

        这是 Anthropic tool-use 协议要求的格式：工具结果以 role=user
        追加，并通过 tool_use_id 指回模型刚才发起的那次工具调用。
        """
        self.messages.append({"role": "user", "content": results})

    def record_tool_result(self, result: ToolResult) -> None:
        """Track a tool execution for the investigation log + escalation handoff.

        这里只记录工具结果，不影响 Anthropic message history；history
        由 add_tool_results_message() 单独维护。
        """
        self.investigation.append(result)

    def mark_escalated(self, escalation: EscalationSummary) -> None:
        # Store the handoff package and stop the interactive session.
        # 保存人工交接包，并让 CLI 主循环结束。
        self.escalated = True
        self.escalation = escalation
        self.finished = True

    # ---- Derived views -----------------------------------------------------

    def tools_consulted(self) -> list[str]:
        """Distinct tool names called so far, used in human escalation summaries.

        去重但保留第一次出现顺序，让人工团队知道 agent 已经查过哪些工具。
        """
        seen: list[str] = []
        for r in self.investigation:
            if r.name not in seen:
                seen.append(r.name)
        return seen

    def services_touched(self) -> list[str]:
        """Distinct services checked so far, used in human escalation summaries.

        只从成功的 check_system_status 结果里提取服务名；失败结果不算。
        """
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
        """Return chat/tool history for each Anthropic API call.

        现在只是浅拷贝，因为内部已经按 Anthropic 格式存好了。
        浅拷贝可以避免调用方直接 append 到 self.messages 本体。
        """
        return list(self.messages)

    def system_context(self) -> str:
        """Build user context appended to the system prompt on each LLM call.

        This is what tells the agent which `user_id` to pass to `lookup_user` and
        provides quick situational context (role, location, priority) without
        requiring an extra round-trip just to learn who's on the other end.

        这段不是给终端用户看的，而是拼到 system prompt 里给模型看。
        它告诉模型当前 user_id 和基础 profile；更敏感/完整的信息仍要求
        模型在需要时调用 lookup_user。
        """
        if self.user_record is None:
            # Unknown user IDs still keep the CLI usable, but profile context is limited.
            # 用户目录没查到时仍继续聊天，只告诉模型“profile not loaded”。
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
