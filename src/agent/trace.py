"""Trace — render agent behavior to console + persist as JSONL.

Two outputs:
- Live console rendering via rich (between user prompt and agent reply, the
  CLI prints each tool call and result so the operator can see what the agent
  is actually doing).
- Append-only JSONL at logs/traces.jsonl, one TraceEvent per line. Each line
  carries the conversation_id so multi-session logs can be filtered later
  with `jq 'select(.conversation_id=="conv_xxx")'`.

Hook points (called from orchestrator.run_turn):
- tool_call(name, input)        — agent decided to call a tool
- tool_result(ToolResult)       — tool finished
- escalation(EscalationSummary) — escalate succeeded; conversation will end
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from agent.schemas import EscalationSummary, ToolResult, TraceEvent


DEFAULT_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "logs" / "traces.jsonl"
)


class Tracer:
    """Renders trace events to a rich Console and appends them to a JSONL log file."""

    def __init__(
        self,
        conversation_id: str,
        console: Console | None = None,
        log_path: Path | None = None,
        render: bool = True,
        persist: bool = True,
    ) -> None:
        self.conversation_id = conversation_id
        self.console = console or Console()
        self.log_path = log_path or DEFAULT_LOG_PATH
        self.render = render
        self.persist = persist
        if self.persist:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Public hooks -----------------------------------------------------

    def tool_call(self, name: str, raw_input: dict[str, Any]) -> None:
        if self.render:
            args_str = self._format_args(name, raw_input)
            self.console.print(
                f"  [dim cyan]→[/] [cyan]{name}[/][dim cyan]({args_str})[/]",
                highlight=False,
            )
        self._persist(
            event_type="tool_call",
            payload={"name": name, "input": raw_input},
        )

    def tool_result(self, result: ToolResult) -> None:
        if self.render:
            if result.success:
                summary = self._summarize_success(result)
                latency = (
                    f"{result.latency_ms:.0f}ms"
                    if result.latency_ms is not None
                    else "?"
                )
                self.console.print(
                    f"    [dim]✓ {summary}[/] [dim italic]({latency})[/]",
                    highlight=False,
                )
            else:
                self.console.print(
                    f"    [red]✗ {result.name}: {result.error}[/]",
                    highlight=False,
                )
        self._persist(
            event_type="tool_result",
            payload={
                "name": result.name,
                "success": result.success,
                "error": result.error,
                "latency_ms": result.latency_ms,
                "data_summary": (
                    self._summarize_success(result) if result.success else None
                ),
            },
        )

    def escalation(self, summary: EscalationSummary) -> None:
        if self.render:
            self.console.print(
                f"  [bold yellow]⚠ Escalated[/] [yellow]{summary.handoff_id} → "
                f"{summary.recommended_team}[/]",
                highlight=False,
            )
        self._persist(
            event_type="escalation",
            payload=summary.model_dump(mode="json"),
        )

    # ---- Internal helpers --------------------------------------------------

    def _persist(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.persist:
            return
        event = TraceEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,  # type: ignore[arg-type]
            conversation_id=self.conversation_id,
            payload=payload,
        )
        with self.log_path.open("a") as f:
            f.write(event.model_dump_json() + "\n")

    @staticmethod
    def _format_args(name: str, raw_input: dict[str, Any]) -> str:
        """Compact display of tool args; long fields get truncated."""
        # For escalate, only show the most relevant top-level fields
        if name == "escalate":
            keys = ("urgency", "recommended_team")
            shown = {k: raw_input[k] for k in keys if k in raw_input}
        else:
            shown = {k: v for k, v in raw_input.items() if k != "include_states"}
        parts: list[str] = []
        for k, v in shown.items():
            if isinstance(v, str) and len(v) > 60:
                v = v[:57] + "..."
            parts.append(f"{k}={v!r}")
        return ", ".join(parts)

    @staticmethod
    def _summarize_success(result: ToolResult) -> str:
        """Compact one-line summary of a successful tool result, for the operator."""
        data = result.data
        if not isinstance(data, dict):
            return result.name

        if result.name == "lookup_user":
            return (
                f"lookup_user → {data.get('name', '?')}, "
                f"{data.get('location', '?')}, "
                f"locked={data.get('account_locked', False)}"
            )
        if result.name == "check_system_status":
            return (
                f"check_system_status({data.get('service', '?')}) → "
                f"status={data.get('status', '?')}, "
                f"{len(data.get('incidents', []))} incident(s), "
                f"{len(data.get('recent_changes', []))} change(s)"
            )
        if result.name in ("search_kb", "search_history"):
            hits = data.get("hits", []) or []
            if not hits:
                return f"{result.name} → no hits"
            top = hits[0]
            top_id = (
                top.get("id")
                or top.get("article_id")
                or top.get("path", "?")
            )
            return (
                f"{result.name} → {len(hits)} hit(s), "
                f"top={top_id} score={top.get('score', '?')}"
            )
        if result.name == "escalate":
            return f"escalate → {data.get('handoff_id', '?')}"
        return result.name
