"""CLI entry — interactive chat with FirstLine, the IT support agent.

Run: `uv run itagent --user u_001`  (or any user_id from data/users.json)
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agent.orchestrator import run_turn
from agent.state import ConversationState
from agent.trace import Tracer
from tools.user_directory import lookup_user


def cli() -> None:
    parser = argparse.ArgumentParser(
        prog="itagent",
        description="FirstLine — IT support agent CLI",
    )
    parser.add_argument(
        "--user",
        required=True,
        help="Employee user_id, e.g., u_001 (Alice), u_003 (Carol), u_004 (David), u_005 (Emma).",
    )
    args = parser.parse_args()

    console = Console()
    state = ConversationState(user_id=args.user)
    tracer = Tracer(conversation_id=state.conversation_id, console=console)

    # Pre-load user record so the agent can greet appropriately.
    pre_lookup = lookup_user(args.user)
    if pre_lookup.success and isinstance(pre_lookup.data, dict):
        state.user_record = pre_lookup.data
        console.print(
            Panel(
                Text.from_markup(
                    f"Hi [bold]{pre_lookup.data['name']}[/]!  "
                    f"I'm FirstLine, your IT helper. What can I help you with today?"
                ),
                title="agent",
                border_style="magenta",
            )
        )
    else:
        console.print(
            f"[yellow]Warning: user '{args.user}' not in directory. Continuing anyway.[/]"
        )

    while not state.finished:
        try:
            user_input = console.input("[bold green]you ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            return

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/]")
            return

        try:
            reply = run_turn(state, user_input, tracer=tracer)
        except Exception as exc:  # surface API / network errors without killing the session
            console.print(f"[red]Error:[/] {exc}")
            continue

        console.print(Panel(reply, title="agent", border_style="magenta"))

        if state.escalated and state.escalation is not None:
            console.print(
                f"[bold yellow]✓ Escalated as {state.escalation.handoff_id} "
                f"to {state.escalation.recommended_team}.[/]"
            )

    console.print(
        f"[dim]Session ended. Conversation id: {state.conversation_id}[/]"
    )


if __name__ == "__main__":
    cli()
