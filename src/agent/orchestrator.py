"""Agent loop — the heart of the system.

Single-loop design with native Anthropic tool use:
- Each call to `run_turn` adds the user message, then loops calling Claude
  until Claude returns `stop_reason='end_turn'` (no more tool calls needed).
- Tool inputs from Claude are validated against the Pydantic input schema
  before dispatch, so hallucinated arguments fail at the boundary.
- The escalate tool gets context fields (user_id, user_name, services_touched,
  tools_consulted) injected from ConversationState — Claude doesn't see those
  in the tool schema.
- A max_iterations guard prevents runaway tool-calling loops.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from agent.llm import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, get_client
from agent.prompts import SYSTEM_PROMPT
from agent.scope import classify_scope, out_of_scope_reply
from agent.schemas import (
    CheckSystemStatusInput,
    EscalateInput,
    EscalationSummary,
    LookupUserInput,
    SearchHistoryInput,
    SearchKBInput,
    ToolResult,
)
from agent.state import ConversationState
from agent.trace import Tracer
from tools.registry import TOOLS, TOOL_SCHEMAS


# Maps tool name to its Pydantic input schema for runtime validation
INPUT_SCHEMAS = {
    "lookup_user": LookupUserInput,
    "search_kb": SearchKBInput,
    "check_system_status": CheckSystemStatusInput,
    "search_history": SearchHistoryInput,
    "escalate": EscalateInput,
}


def _execute_tool(
    name: str, raw_input: dict[str, Any], state: ConversationState
) -> ToolResult:
    """Validate input against schema, dispatch to the tool, inject context for escalate."""
    schema = INPUT_SCHEMAS.get(name)
    func = TOOLS.get(name)
    if schema is None or func is None:
        return ToolResult(name=name, success=False, error=f"unknown tool: {name}")

    try:
        validated = schema.model_validate(raw_input)
    except ValidationError as exc:
        return ToolResult(
            name=name,
            success=False,
            error=f"invalid arguments: {exc.errors(include_url=False)}",
        )

    args = validated.model_dump()

    if name == "escalate":
        # Inject context the LLM doesn't author
        user_record = state.user_record or {}
        args.update(
            user_id=state.user_id,
            user_name=user_record.get("name", "unknown"),
            services_involved=state.services_touched(),
            tools_consulted=state.tools_consulted(),
        )

    return func(**args)


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an anthropic content block (pydantic) to a JSON-safe dict."""
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json")
    return dict(block)


def _extract_text(content_blocks: list[Any]) -> str:
    """Join all text-type blocks into a single user-facing string."""
    parts: list[str] = []
    for block in content_blocks:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else ""
            )
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _serialize_tool_result(result: ToolResult) -> str:
    """Pack a ToolResult into the string content of an Anthropic tool_result block."""
    if result.success:
        return json.dumps(result.data, default=str, ensure_ascii=False)
    return result.error or "tool failed without error message"


def run_turn(
    state: ConversationState,
    user_input: str,
    *,
    tracer: Tracer | None = None,
    max_iterations: int = 12,
) -> str:
    """Process one user message; may take several LLM/tool round-trips internally.

    Returns the final assistant text. Mutates `state` in place. If `tracer` is
    provided, emits trace events for each tool call, tool result, and escalation.
    """
    state.add_user_message(user_input)

    scope_decision = classify_scope(user_input)
    if scope_decision.out_of_scope:
        reply = out_of_scope_reply(scope_decision)
        state.add_assistant_message(reply)
        return reply

    client = get_client()

    system = SYSTEM_PROMPT + "\n\n" + state.system_context()

    for _ in range(max_iterations):
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=state.to_anthropic_messages(),
        )

        assistant_blocks = [_block_to_dict(b) for b in response.content]
        state.add_assistant_message(assistant_blocks)

        if response.stop_reason == "end_turn":
            return _extract_text(response.content)

        if response.stop_reason == "tool_use":
            tool_result_blocks: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                tool_name = block.name
                tool_input = dict(block.input) if isinstance(block.input, dict) else {}

                if tracer is not None:
                    tracer.tool_call(tool_name, tool_input)

                result = _execute_tool(tool_name, tool_input, state)
                state.record_tool_result(result)

                if tracer is not None:
                    tracer.tool_result(result)

                # Side effect: if escalate succeeded, capture the summary in state
                if (
                    tool_name == "escalate"
                    and result.success
                    and isinstance(result.data, dict)
                ):
                    try:
                        summary = EscalationSummary.model_validate(result.data)
                        state.mark_escalated(summary)
                        if tracer is not None:
                            tracer.escalation(summary)
                    except ValidationError:
                        pass  # Best-effort; the file is still written.

                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _serialize_tool_result(result),
                        "is_error": not result.success,
                    }
                )

            state.add_tool_results_message(tool_result_blocks)
            continue

        # Any other stop reason (max_tokens, stop_sequence, refusal) — bail
        return _extract_text(response.content) or f"[stopped: {response.stop_reason}]"

    return "[stopped: max iterations reached]"
