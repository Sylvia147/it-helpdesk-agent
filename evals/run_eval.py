"""Evaluation runner — script all cases against the live agent and check assertions.

Usage:
    PYTHONPATH=src uv run python evals/run_eval.py

Output:
- Console summary (one line per case + per-check breakdown for failures)
- JSON results at evals/results/run_<UTC_TIMESTAMP>.json

Checks performed per case:
- expected_tools_subset: every required tool was called at least once.
- forbidden_tools: none of the listed tools was called.
- expected_decision: final state ('escalate' / 'resolve' / 'clarify').
- expected_team: when escalating, the recommended_team matches.
- must_include: each substring (case-insensitive) appears in final reply.
- must_not_include: none of the substrings appears in final reply.

Decision derivation:
- 'escalate' if state.escalated is True
- 'clarify' if final reply ends with '?' (agent still asking)
- 'resolve' otherwise
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

# Ensure src/ is on the import path when this file is run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agent.orchestrator import run_turn  # noqa: E402
from agent.state import ConversationState  # noqa: E402
from agent.trace import Tracer  # noqa: E402
from tools.user_directory import lookup_user  # noqa: E402


CASES_PATH = ROOT / "evals" / "test_cases.json"
RESULTS_DIR = ROOT / "evals" / "results"


def _derive_decision(state: ConversationState, final_reply: str) -> str:
    """Final outcome classification — deliberately binary.

    'escalate' means an EscalationSummary was produced. 'non_escalate' means the
    agent gave a recommendation, walkthrough, or clarifying question without
    handing off. We do NOT try to deterministically distinguish 'clarify' from
    'resolve' because the agent legitimately mixes both (a recommendation
    followed by a follow-up question), and a substring-only heuristic gets it
    wrong both ways. Test cases that probe clarifying behavior assert it via
    `must_include=["?"]` plus `forbidden_tools=["escalate"]` instead.
    """
    return "escalate" if state.escalated else "non_escalate"


def _check(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "pass": passed, "detail": detail}


def _evaluate(case: dict, state: ConversationState, final_reply: str) -> list[dict]:
    checks: list[dict] = []
    actual_tools = {r.name for r in state.investigation}

    # 1. Required tool subset
    expected_subset = set(case.get("expected_tools_subset", []))
    missing = expected_subset - actual_tools
    checks.append(
        _check(
            "expected_tools_subset",
            not missing,
            f"missing: {sorted(missing)}" if missing else f"called {sorted(actual_tools)}",
        )
    )

    # 2. Forbidden tools
    forbidden = set(case.get("forbidden_tools", []))
    used_forbidden = forbidden & actual_tools
    checks.append(
        _check(
            "forbidden_tools",
            not used_forbidden,
            f"used forbidden: {sorted(used_forbidden)}" if used_forbidden else "ok",
        )
    )

    # 3. Decision
    actual_decision = _derive_decision(state, final_reply)
    expected_decision = case["expected_decision"]
    checks.append(
        _check(
            "expected_decision",
            actual_decision == expected_decision,
            f"got {actual_decision!r}, expected {expected_decision!r}",
        )
    )

    # 4. Team (only if expected and decision was escalate)
    expected_team = case.get("expected_team")
    if expected_team is not None and expected_team != "any":
        actual_team = state.escalation.recommended_team if state.escalation else None
        checks.append(
            _check(
                "expected_team",
                actual_team == expected_team,
                f"got {actual_team!r}, expected {expected_team!r}",
            )
        )
    elif expected_team == "any":
        checks.append(
            _check(
                "expected_team",
                state.escalated,
                f"escalated to {state.escalation.recommended_team!r}"
                if state.escalation
                else "did not escalate",
            )
        )

    # 5. Must-include phrases
    reply_lower = final_reply.lower()
    for phrase in case.get("must_include", []):
        checks.append(
            _check(
                f"must_include[{phrase!r}]",
                phrase.lower() in reply_lower,
                "found" if phrase.lower() in reply_lower else "missing",
            )
        )

    # 6. Must-not-include phrases
    for phrase in case.get("must_not_include", []):
        checks.append(
            _check(
                f"must_not_include[{phrase!r}]",
                phrase.lower() not in reply_lower,
                "absent" if phrase.lower() not in reply_lower else "PRESENT",
            )
        )

    return checks


def run_case(
    case: dict,
    console: Console,
    *,
    silent: bool = False,
) -> dict[str, Any]:
    state = ConversationState(user_id=case["user_id"])
    user_rec = lookup_user(case["user_id"])
    if user_rec.success:
        state.user_record = user_rec.data

    tracer = Tracer(
        conversation_id=state.conversation_id,
        console=console,
        render=not silent,
    )

    if not silent:
        console.rule(f"[bold cyan]{case['id']}[/]  user={case['user_id']}")

    # Per-case env overrides (e.g., SIMULATE_FAILURE=search_kb). Restored after.
    env_overrides = case.get("env", {})
    saved_env: dict[str, str | None] = {}
    for key, value in env_overrides.items():
        saved_env[key] = os.environ.get(key)
        os.environ[key] = value

    replies: list[str] = []
    t0 = time.perf_counter()
    error: str | None = None
    try:
        for turn in case["turns"]:
            if not silent:
                console.print(f"[bold green]you ›[/] {turn}")
            reply = run_turn(state, turn, tracer=tracer)
            replies.append(reply)
            if not silent:
                preview = reply[:300] + ("..." if len(reply) > 300 else "")
                console.print(f"[bold magenta]agent ›[/] {preview}\n")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if not silent:
            console.print(f"[red]EXCEPTION:[/] {error}")
    finally:
        for key, prior in saved_env.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
    elapsed = time.perf_counter() - t0

    final_reply = replies[-1] if replies else ""
    checks = _evaluate(case, state, final_reply) if not error else []

    return {
        "case_id": case["id"],
        "category": case.get("category", ""),
        "user_id": case["user_id"],
        "passed": (error is None) and all(c["pass"] for c in checks),
        "error": error,
        "elapsed_s": round(elapsed, 1),
        "tools_called": [r.name for r in state.investigation],
        "tool_count": len(state.investigation),
        "decision": _derive_decision(state, final_reply) if not error else "error",
        "escalation_team": state.escalation.recommended_team if state.escalation else None,
        "handoff_id": state.escalation.handoff_id if state.escalation else None,
        "final_reply": final_reply,
        "checks": checks,
        "conversation_id": state.conversation_id,
    }


def _print_summary(results: list[dict], console: Console) -> None:
    table = Table(
        title="\nEvaluation Summary",
        show_lines=False,
        title_justify="left",
    )
    table.add_column("Case", style="cyan", no_wrap=True)
    table.add_column("Cat")
    table.add_column("Tools", justify="right")
    table.add_column("Decision")
    table.add_column("Pass/Total", justify="right")
    table.add_column("Result", style="bold")

    pass_count = 0
    for r in results:
        n_pass = sum(1 for c in r["checks"] if c["pass"])
        n_total = len(r["checks"])
        if r["passed"]:
            verdict = "[green]PASS[/]"
            pass_count += 1
        elif r["error"]:
            verdict = "[red]ERROR[/]"
        else:
            verdict = "[yellow]FAIL[/]"
        table.add_row(
            r["case_id"],
            r["category"],
            str(r["tool_count"]),
            r["decision"],
            f"{n_pass}/{n_total}",
            verdict,
        )

    console.print(table)
    console.print(
        f"\n[bold]Overall: {pass_count}/{len(results)} cases passed[/]\n"
    )

    # Failure detail
    for r in results:
        if r["passed"] or r["error"]:
            continue
        console.print(f"[yellow]── {r['case_id']} failed checks ──[/]")
        for c in r["checks"]:
            if not c["pass"]:
                console.print(f"  [red]✗ {c['name']}[/]: {c['detail']}")
        console.print()


def main() -> int:
    cases_doc = json.loads(CASES_PATH.read_text())
    cases = cases_doc["cases"]
    console = Console()

    console.print(f"[bold]Running {len(cases)} eval cases...[/]\n")

    results: list[dict] = []
    for case in cases:
        results.append(run_case(case, console))

    _print_summary(results, console)

    # Persist
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"run_{timestamp}.json"
    pass_count = sum(1 for r in results if r["passed"])
    out_path.write_text(
        json.dumps(
            {
                "run_id": timestamp,
                "case_count": len(results),
                "pass_count": pass_count,
                "results": results,
            },
            indent=2,
            default=str,
        )
    )
    console.print(f"[dim]Results written to {out_path.relative_to(ROOT)}[/]")

    return 0 if pass_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
