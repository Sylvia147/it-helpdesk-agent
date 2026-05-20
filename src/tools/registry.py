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


TOOLS: dict[str, Callable[..., Any]] = {
    "lookup_user": lookup_user,
    "check_system_status": check_system_status,
    "search_kb": search_kb,
    "search_history": search_history,
    "escalate": escalate,
}


def _build_tool_schema(name: str, model_cls) -> dict[str, Any]:
    """Convert a Pydantic input model into the dict shape Anthropic's tool use API expects."""
    schema = model_cls.model_json_schema()
    description = schema.pop("description", None) or (model_cls.__doc__ or "").strip()
    schema.pop("title", None)
    return {
        "name": name,
        "description": description,
        "input_schema": schema,
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _build_tool_schema("lookup_user", LookupUserInput),
    _build_tool_schema("check_system_status", CheckSystemStatusInput),
    _build_tool_schema("search_kb", SearchKBInput),
    _build_tool_schema("search_history", SearchHistoryInput),
    _build_tool_schema("escalate", EscalateInput),
]
