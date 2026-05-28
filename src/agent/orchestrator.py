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
import re
from typing import Any, cast

from anthropic.types import MessageParam, ToolUnionParam
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


# Map each tool name to the Pydantic model that validates its input.
# 把“工具名”映射到对应的 Pydantic 参数模型，用来校验工具入参。
#
# The LLM proposes tool calls as raw dictionaries, so the orchestrator
# checks those arguments here before dispatching to the real Python tool.
# 大模型给出的 tool call 参数只是普通 dict，不能直接信任；
#     在真正执行 Python 工具函数前，先在这里做结构化校验。
INPUT_SCHEMAS = {
    "lookup_user": LookupUserInput,
    "search_kb": SearchKBInput,
    "check_system_status": CheckSystemStatusInput,
    "search_history": SearchHistoryInput,
    "escalate": EscalateInput,
}


# Requests that require a recognized employee profile before we can safely help.
# 这些请求需要先识别员工身份；游客/未知 user_id 不能查账号状态、权限或升级人工。
_PROFILE_REQUIRED_RE = re.compile(
    r"\b(okta|sso|mfa|password|account|locked|unlock|login|permission|permissions)\b"
    r"|\blog\s+in\b"
    r"|\b(access request|grant access|need access|request access|prod access|production access)\b",
    re.IGNORECASE,
)


def _requires_profile(text: str) -> bool:
    """Return True when the request needs a recognized user profile.

    General service-status questions can still work for unknown users, but
    account, login, MFA, and access/permission requests should not proceed
    without a directory record.

    普通服务状态问题可以在未知用户下继续处理；但账号、登录、MFA、权限类
    问题必须先有可识别的员工资料。
    """
    return bool(_PROFILE_REQUIRED_RE.search(text))


def _missing_profile_reply(user_id: str) -> str:
    """User-facing reply for identity-sensitive requests from unknown users.

    未识别用户请求账号/权限相关操作时的固定回复。
    """
    return (
        f"I can't check account status, permissions, or create an IAM handoff for "
        f"user_id `{user_id}` because that ID was not found in the employee "
        "directory.\n\n"
        "Please restart with a valid employee user_id, or contact the IT Service "
        "Desk through your normal sign-in/helpdesk channel so they can verify "
        "your identity."
    )


def _execute_tool(
    name: str, raw_input: dict[str, Any], state: ConversationState
) -> ToolResult:
    """Validate input, dispatch the tool, and inject handoff context for escalation.

    Used by run_turn() when Claude returns a tool_use block.
    run_turn() 在模型返回 tool_use block 时调用这里。

    这是 LLM tool call 到真实 Python 工具之间的安全边界：
    先找 schema 和函数，再校验参数，最后才执行工具。
    """
    # Look up both the validator and the actual Python function for this tool.
    # 同时查两张表：INPUT_SCHEMAS 负责校验参数，TOOLS 负责真正执行。
    schema = INPUT_SCHEMAS.get(name)
    func = TOOLS.get(name)
    if schema is None or func is None:
        # Unknown tool names become tool errors, not process crashes.
        # 未知工具返回结构化失败结果，不让整个 CLI 崩掉。
        return ToolResult(name=name, success=False, error=f"unknown tool: {name}")

    try:
        # Validate LLM-authored raw arguments before calling real code.
        # 大模型可能写错字段名或类型；这里用 Pydantic 拦住坏参数。
        validated = schema.model_validate(raw_input)
    except ValidationError as exc:
        return ToolResult(
            name=name,
            success=False,
            error=f"invalid arguments: {exc.errors(include_url=False)}",
        )

    args = validated.model_dump()

    if name == "escalate":
        if state.user_record is None:
            return ToolResult(
                name=name,
                success=False,
                error=(
                    "Cannot create an escalation without a recognized employee "
                    "profile; ask the user to restart with a valid user_id or "
                    "contact the IT Service Desk through an authenticated channel."
                ),
            )
        # Inject factual handoff context the LLM should not author itself.
        # 升级交接里的事实字段由代码注入，不让模型自己编：
        #     user_id、user_name、查过的服务、用过的工具。
        user_record = state.user_record or {}
        args.update(
            user_id=state.user_id,
            user_name=user_record.get("name", "unknown"),
            services_involved=state.services_touched(),
            tools_consulted=state.tools_consulted(),
        )

    # Dispatch to the real tool function, e.g. check_system_status(service="vpn").
    # 最后才真正调用工具函数；所有工具统一返回 ToolResult。
    return func(**args)


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an Anthropic content block to a JSON-safe dict.

    Used before saving assistant responses into ConversationState.messages.
    用在保存 assistant 回复到 ConversationState.messages 之前。

    Anthropic SDK 返回的 block 往往不是普通 dict，而是 SDK/Pydantic 对象。
    为了把 assistant 回复稳定保存进 state.messages，需要先转成 JSON-safe dict。
    """
    # Anthropic SDK content blocks are Pydantic-like objects.
    # 正常线上路径：SDK 对象有 model_dump()，直接转 JSON-safe dict。
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json")
    # Tests or future adapters may already provide plain dict blocks.
    # 测试或其他兼容层可能已经传入普通 dict。
    if isinstance(block, dict):
        return dict(block)
    # Anything else is unexpected; fail clearly so message history is not corrupted.
    # 其他类型说明上游返回形状异常，明确报错比悄悄写坏 history 更安全。
    try:
        return dict(block)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Unsupported Anthropic content block type: {type(block).__name__}"
        ) from exc


def _extract_text(content_blocks: list[Any]) -> str:
    """Join all text-type blocks into a single user-facing string.

    Used when the model is done and we need the final reply to print in the CLI.
    用在模型完成本轮回复后，从 response.content 里提取要打印给用户看的文本。

    Example input / 输入例子:
        [{"type": "text", "text": "Checking Salesforce."},
         {"type": "tool_use", "name": "check_system_status", "input": {...}},
         {"type": "text", "text": "It is degraded."}]

    Output / 输出:
        "Checking Salesforce.\n\nIt is degraded."

    Anthropic 的 content 可能混着 text 和 tool_use。这个函数只抽取
    text block，作为最终要显示给用户的自然语言回复。
    """
    parts: list[str] = []
    for block in content_blocks:
        # Anthropic returns SDK objects; tests may use plain dicts.
        # 兼容 SDK 对象的 block.type，也兼容 dict 的 block["type"]。
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            # Only text blocks are user-facing; tool_use blocks are handled separately.
            # tool_use 是给 orchestrator 执行工具用的，不直接展示给用户。
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else ""
            )
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _serialize_tool_result(result: ToolResult) -> str:
    """Pack a ToolResult into the string content of an Anthropic tool_result block.

    Used to send tool outputs back to Claude, not for console tracing.
    用来把工具结果传回 Claude，不是给 tracer/终端展示用的。

    Anthropic 的 tool_result block 里 content 是字符串，所以成功结果转 JSON，
    失败结果直接把 error 字符串传回模型，让模型知道工具失败了。
    """
    if result.success:
        return json.dumps(result.data, default=str, ensure_ascii=False)
    return result.error or "tool failed without error message"


def run_turn(
    state: ConversationState,
    user_input: str,
    # Arguments after * must be passed by keyword, e.g. tracer=tracer.
    # * 后面的参数必须用关键字传入，避免把 tracer/max_iterations 的位置搞混。
    *,
    tracer: Tracer | None = None,
    max_iterations: int = 12,
) -> str:
    """Process one user message; may take several LLM/tool round-trips internally.

    Returns the final assistant text. Mutates `state` in place. If `tracer` is
    provided, emits trace events for each tool call, tool result, and escalation.

    处理“一轮用户输入”。这一轮内部可能会经历多次：
    LLM -> tool_use -> 执行工具 -> tool_result -> 再问 LLM。
    直到模型返回 end_turn，才把最终文本回复给 CLI。
    """
    # Store the user's turn before any scope check or model call.
    # 先把用户消息写进会话历史，这样后续 LLM 调用能看到当前问题。
    state.add_user_message(user_input)
    if tracer is not None:
        tracer.user_message(user_input)

    # Deterministic guard for clearly non-IT requests; no LLM/tool cost needed.
    # 明确不是 IT 范围的问题直接兜底，不消耗 LLM，也不调用工具。
    scope_decision = classify_scope(user_input)
    if scope_decision.out_of_scope:
        reply = out_of_scope_reply(scope_decision)
        state.add_assistant_message(reply)
        if tracer is not None:
            tracer.assistant_message(reply)
        return reply

    # Unknown users can still ask general IT questions, but identity-sensitive
    # work needs a directory record. Do not let a fake/unknown user_id escalate
    # account, login, MFA, or permission issues.
    # 未识别用户仍可问一般 IT 问题；但账号/登录/MFA/权限问题需要目录资料。
    # 这里直接返回，不调用 LLM，也不创建人工 handoff。
    if state.user_record is None and _requires_profile(user_input):
        reply = _missing_profile_reply(state.user_id)
        state.add_assistant_message(reply)
        if tracer is not None:
            tracer.assistant_message(reply)
        return reply

    client = get_client()

    # Static system prompt + dynamic user/profile context for this conversation.
    # 固定系统提示词负责角色/规则；system_context 注入当前用户身份信息。
    system = SYSTEM_PROMPT + "\n\n" + state.system_context()

    for _ in range(max_iterations):
        # Each iteration sends the full message history because LLM APIs are stateless.
        # LLM API 本身不记忆历史，所以每次都要把 state.messages 全量传进去。
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            # Casts keep static type checkers happy; runtime values are JSON-like dicts.
            # cast 只是告诉 IDE/类型检查器这些 dict 符合 Anthropic 参数形状，不改变运行时值。
            tools=cast(list[ToolUnionParam], TOOL_SCHEMAS),
            messages=cast(list[MessageParam], state.to_anthropic_messages()),
        )

        # Persist the assistant response exactly enough to continue tool-use protocol.
        # 保存 assistant block，尤其是 tool_use block；下一条 tool_result 要引用它的 id。
        assistant_blocks = [_block_to_dict(b) for b in response.content]
        state.add_assistant_message(assistant_blocks)

        if response.stop_reason == "end_turn":
            # No more tools requested; extract the final text for the CLI.
            # 模型说这一轮结束了，只取 text block 展示给用户。
            reply = _extract_text(response.content)
            if tracer is not None:
                tracer.assistant_message(reply)
            return reply

        if response.stop_reason == "tool_use":
            tool_result_blocks: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                # Tool name/input are authored by the model, then validated in _execute_tool.
                # 工具名和参数来自模型；真正执行前会在 _execute_tool 里校验。
                tool_name = block.name
                tool_input = dict(block.input) if isinstance(block.input, dict) else {}

                if tracer is not None:
                    tracer.tool_call(tool_name, tool_input)

                result = _execute_tool(tool_name, tool_input, state)
                state.record_tool_result(result)

                if tracer is not None:
                    tracer.tool_result(result)

                # If escalate succeeded, capture the handoff and mark the session finished.
                # escalate 成功后，把交接摘要存进 state，并结束当前会话。
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

                # Anthropic requires tool_result blocks to point back to tool_use_id.
                # tool_result 必须带 tool_use_id，告诉模型“这是哪个工具调用的结果”。
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _serialize_tool_result(result),
                        "is_error": not result.success,
                    }
                )

            # Tool results are appended as a user-role message per Anthropic protocol.
            # 按 Anthropic 协议，工具结果作为 role=user 的消息追加回历史。
            state.add_tool_results_message(tool_result_blocks)
            continue

        # Any other stop reason (max_tokens, stop_sequence, refusal) exits safely.
        # 其他停止原因不继续循环，尽量返回已有文本或明确说明停止原因。
        reply = _extract_text(response.content) or f"[stopped: {response.stop_reason}]"
        if tracer is not None:
            tracer.assistant_message(reply)
        return reply

    # Guardrail against infinite tool loops.
    # 防止模型反复要求工具调用导致无限循环。
    reply = "[stopped: max iterations reached]"
    if tracer is not None:
        tracer.assistant_message(reply)
    return reply
