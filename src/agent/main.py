"""CLI entry — interactive chat with FirstLine, the IT support agent.

Run: `uv run itagent --user u_001`  (or any user_id from data/users.json)
"""

# Delay evaluating type annotations, which helps with forward references.
# 延迟解析类型注解；遇到前向引用/循环引用时更稳。
from __future__ import annotations

import argparse
import sys

# Rich makes the CLI output easier to read with styled terminal UI elements.
# Rich 用来美化终端输出，比如彩色文字、输入提示和边框面板。
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agent.orchestrator import run_turn
from agent.state import ConversationState
from agent.trace import Tracer
from tools.user_directory import lookup_user


def cli() -> None:
    # argparse defines the CLI contract. The agent requires a user_id so the
    # conversation can be tied to an employee record.
    # argparse 定义命令行参数。这里强制要求 --user，因为 agent 需要知道
    # 当前员工是谁，才能注入 user context 或查目录。
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

    # Console owns terminal I/O; state owns conversation memory; tracer shows
    # and persists what the agent did between user input and assistant reply.
    # console 负责终端输入输出；state 负责会话记忆；tracer 负责把工具调用
    # 过程展示出来并写日志。
    console = Console()
    # Keep track of the current user's conversation state.
    # 创建当前用户这次会话的状态对象。
    state = ConversationState(user_id=args.user)
    # Trace this conversation and print diagnostic output through the Rich console.
    # tracer 会把工具调用/结果打印在终端，也会写入 logs/traces.jsonl。
    tracer = Tracer(conversation_id=state.conversation_id, console=console)

    # Pre-load user record so the agent can greet appropriately and include
    # profile context in state.system_context().
    # 启动时先查用户目录：查到就缓存到 state，后续 system prompt 能带上
    # 姓名、角色、地点、优先级等基础信息。
    pre_lookup = lookup_user(args.user)
    if pre_lookup.success and isinstance(pre_lookup.data, dict):
        # Cache the directory record so later turns can use profile context.
        # 把用户资料放进 state；后续 LLM 调用会通过 system_context 看到。
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
        # Continue with only the user_id; profile-based checks are limited.
        # 查不到用户也不退出，但只能当“未识别用户”处理，profile/权限判断受限。
        console.print(
            f"[yellow]Warning: user '{args.user}' not in directory. Continuing anyway.[/]"
        )

    # Main interactive loop: keep taking user messages until the session ends.
    # CLI 主循环。只要 state.finished 还是 False，就继续等待用户输入。
    while not state.finished:
        try:
            # Print the styled prompt separately, then let built-in input() read
            # only the user's text. This avoids occasional duplicate prompt
            # rendering from rich Console.input in some terminals.
            # 先用 Rich 打印彩色提示，再用原生 input() 只读取用户文本；
            # 避免某些终端里 Console.input 偶尔重复显示 `you ›`。
            console.print("[bold green]you ›[/] ", end="")
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl-D / Ctrl-C should exit gracefully instead of showing a traceback.
            # 用户按 Ctrl-D 或 Ctrl-C 时优雅退出，不打印异常堆栈。
            console.print("\n[dim]Goodbye.[/]")
            return

        # Ignore blank input and keep waiting for a real message.
        # 空输入不交给 agent，直接进入下一轮等待。
        if not user_input:
            continue
        # Support a few quick commands for ending the CLI session.
        # 支持几个手动退出命令。
        if user_input.lower() in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/]")
            return

        try:
            # Process one user message; may call the LLM and several tools internally.
            # 处理一轮用户消息；内部可能多次调用 LLM 和工具，最终返回文本回复。
            reply = run_turn(state, user_input, tracer=tracer)
        except Exception as exc:  # surface API / network errors without killing the session
            # API/network errors should not kill the CLI; user can retry.
            # API 或网络错误只显示错误，不结束整个会话，方便用户重试。
            console.print(f"[red]Error:[/] {exc}")
            continue

        console.print(Panel(reply, title="agent", border_style="magenta"))

        # If the turn created a human handoff, show the ticket/team summary.
        # 如果本轮触发人工升级，额外显示 handoff id 和推荐团队。
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
