"""Tool registry — single source of truth for what tools exist.

`TOOLS` maps tool names to callables.
`TOOL_SCHEMAS` is the list passed verbatim to anthropic.messages.create(tools=...).
"""

from __future__ import annotations

from typing import Any, Callable

from agent.schemas import (
    CheckSystemStatusInput,
    EscalateInput,
    LookupUserInput,
    SearchHistoryInput,
    SearchKBInput,
)
from tools.escalation import escalate
from tools.history_search import search_history
from tools.kb_search import search_kb
from tools.system_status import check_system_status
from tools.user_directory import lookup_user


# Runtime dispatch table: orchestrator calls TOOLS[name](**validated_args).
# 运行时工具分发表：orchestrator 校验参数后，用工具名找到真正函数。
TOOLS: dict[str, Callable[..., Any]] = {
    "lookup_user": lookup_user,
    "check_system_status": check_system_status,
    "search_kb": search_kb,
    "search_history": search_history,
    "escalate": escalate,
}


def _build_tool_schema(name: str, model_cls) -> dict[str, Any]:
    """Convert a Pydantic input model into Anthropic's tool schema shape.

    Anthropic 需要每个工具提供 name、description、input_schema。
    input_schema 来自 Pydantic 的 JSON Schema，字段 description 会被模型看到。
    """
    schema = model_cls.model_json_schema()
    # Prefer explicit JSON Schema description; otherwise use class docstring.
    # 优先用 schema description；没有就用 Pydantic model 的 docstring。
    description = schema.pop("description", None) or (model_cls.__doc__ or "").strip()
    # Tool schemas do not need Pydantic's generated title.
    # Anthropic 工具 schema 不需要 Pydantic 自动生成的 title。
    schema.pop("title", None)
    return {
        "name": name,
        "description": description,
        "input_schema": schema,
    }


# This list is passed directly to client.messages.create(tools=...).
# 这个列表会原样传给 Anthropic API 的 tools 参数，告诉模型有哪些工具可用。
TOOL_SCHEMAS: list[dict[str, Any]] = [
    _build_tool_schema("lookup_user", LookupUserInput),
    _build_tool_schema("check_system_status", CheckSystemStatusInput),
    _build_tool_schema("search_kb", SearchKBInput),
    _build_tool_schema("search_history", SearchHistoryInput),
    _build_tool_schema("escalate", EscalateInput),
]
