"""Trace — render agent behavior to console + persist as JSONL.

Two outputs:
- Live console rendering via rich (between user prompt and agent reply, the
  CLI prints each tool call and result so the operator can see what the agent
  is actually doing).
- Append-only JSONL at logs/traces.jsonl, one TraceEvent per line. Each line
  carries the conversation_id so multi-session logs can be filtered later
  with `jq 'select(.conversation_id=="conv_xxx")'`.
- Per-conversation JSONL at logs/conversations/<conversation_id>.jsonl, with the
  same events but already separated for easier reading.

Hook points (called from orchestrator.run_turn):
- user_message(text)            — user submitted a turn
- assistant_message(text)       — final user-facing assistant reply
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
DEFAULT_CONVERSATION_LOG_DIR = (
    Path(__file__).resolve().parent.parent.parent / "logs" / "conversations"
)


class Tracer:
    """Renders trace events to a rich Console and appends them to a JSONL log file.

    Tracer 不参与决策，只负责“可观察性”：终端上展示工具过程，
    同时把结构化事件写到 logs/traces.jsonl 和单独的会话文件，
    方便事后回看。
    """

    def __init__(
        self,
        conversation_id: str,
        console: Console | None = None,
        log_path: Path | None = None,
        conversation_log_dir: Path | None = None,
        render: bool = True,
        persist: bool = True,
    ) -> None:
        # render controls terminal output; persist controls JSONL logging.
        # render 控制是否打印到终端，persist 控制是否写 JSONL 文件。
        self.conversation_id = conversation_id
        self.console = console or Console()
        self.log_path = log_path or DEFAULT_LOG_PATH
        self.conversation_log_dir = conversation_log_dir or DEFAULT_CONVERSATION_LOG_DIR
        self.conversation_log_path = (
            self.conversation_log_dir / f"{self.conversation_id}.jsonl"
        )
        self.render = render
        self.persist = persist
        if self.persist:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.conversation_log_dir.mkdir(parents=True, exist_ok=True)

    # ---- Public hooks -----------------------------------------------------

    def user_message(self, text: str) -> None:
        """Record the user's message for transcript-style replay.

        记录用户原文，方便之后按 conversation_id 还原完整对话。
        """
        self._persist(
            event_type="user_message",
            payload={"text": text},
        )

    def assistant_message(self, text: str) -> None:
        """Record the final assistant reply shown to the user.

        记录最终展示给用户的大模型回复；这不是缓存，只是复盘日志。
        """
        self._persist(
            event_type="assistant_message",
            payload={"text": text},
        )

    def tool_call(self, name: str, raw_input: dict[str, Any]) -> None:
        """Record that the model requested a tool call.

        在真正执行工具前调用；用户会在 CLI 里看到 agent 准备查什么。
        """
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
        """Record a completed tool result.

        工具执行后调用；成功时展示一行摘要，失败时展示错误。
        """
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
                "data": result.data,
                "data_summary": (
                    self._summarize_success(result) if result.success else None
                ),
            },
        )

    def escalation(self, summary: EscalationSummary) -> None:
        """Record a successful escalation handoff.

        escalate 工具成功后调用，显示 handoff id 和推荐团队。
        """
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
        """Append one TraceEvent row to JSONL unless persistence is disabled.

        每行都是独立 JSON。事件会写两份：全局 traces.jsonl 和当前会话自己的
        logs/conversations/<conversation_id>.jsonl。
        """
        if not self.persist:
            return
        event = TraceEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,  # type: ignore[arg-type]
            conversation_id=self.conversation_id,
            payload=payload,
        )
        with self.log_path.open("a") as f:
            line = event.model_dump_json() + "\n"
            f.write(line)
        with self.conversation_log_path.open("a") as f:
            f.write(line)

    # Static methods live on the class but do not receive `self` automatically.
    # This helper does not read or mutate Tracer state, so keep it static.
    # staticmethod 放在类里面，但调用时不会自动传入 self。
    # 这个 helper 不读取也不修改 Tracer 实例状态，只做参数格式化，所以用 staticmethod。
    @staticmethod
    def _format_args(name: str, raw_input: dict[str, Any]) -> str:
        """Compact display of tool args; long fields get truncated.

        终端 trace 只需要让人快速看懂，不展示过长字段。
        """
        # For escalate, only show the most relevant top-level fields.
        # escalate 的 issue_summary/attempted_steps 可能很长，只展示关键字段。
        if name == "escalate":
            keys = ("urgency", "recommended_team")
            shown = {k: raw_input[k] for k in keys if k in raw_input}
        else:
            shown = {k: v for k, v in raw_input.items() if k != "include_states"}
        parts: list[str] = []
        for k, v in shown.items():
            if isinstance(v, str) and len(v) > 60:
                # Keep trace output one-line and readable.
                # 截断长字符串，避免终端 trace 被挤爆。
                v = v[:57] + "..."
            parts.append(f"{k}={v!r}")
        return ", ".join(parts)

    # This summarizer only depends on the ToolResult passed in, not on self.
    # 这个摘要函数只依赖传入的 ToolResult，不依赖 self，所以也用 staticmethod。
    @staticmethod
    def _summarize_success(result: ToolResult) -> str:
        """Compact one-line summary of a successful tool result, for the operator.

        不把完整工具 payload 打到终端，只展示最能帮助理解的一行摘要。
        """
        data = result.data
        if not isinstance(data, dict):
            return result.name

        if result.name == "lookup_user":
            # Identity lookups highlight user name/location and lock status.
            # 用户查询重点展示姓名、地点、账号是否 locked。
            return (
                f"lookup_user → {data.get('name', '?')}, "
                f"{data.get('location', '?')}, "
                f"locked={data.get('account_locked', False)}"
            )
        if result.name == "check_system_status":
            # Status checks highlight service health plus incident/change counts.
            # 系统状态查询重点展示健康状态、incident 数、change 数。
            return (
                f"check_system_status({data.get('service', '?')}) → "
                f"status={data.get('status', '?')}, "
                f"{len(data.get('incidents', []))} incident(s), "
                f"{len(data.get('recent_changes', []))} change(s)"
            )
        if result.name in ("search_kb", "search_history"):
            # Searches show hit count and top result ID/score for citation tracing.
            # 搜索工具展示命中数和 top id/score，方便确认引用来源。
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
