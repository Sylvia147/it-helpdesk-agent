"""Policy engine — code-level hard rules over data/policies.json.

Not exposed as a tool. The agent loop and the escalate tool both consult this to
enforce the agent-can-vs-cannot boundary independently of the LLM's prompt-level
reasoning. Treating policy as data with a deterministic lookup makes it
independently testable, auditable, and modifiable without retraining or
re-prompting the agent.

Default-deny semantics: an action not in the table returns an `agent_allowed=False`
PolicyDecision routed to IT Service Desk. This guarantees the agent can only act
on whitelisted actions.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from agent.schemas import PolicyDecision


POLICIES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "policies.json"


@lru_cache(maxsize=1)
def _load_policies() -> dict[str, dict]:
    """Load policies.json, stripping underscore-prefixed metadata keys."""
    raw = json.loads(POLICIES_PATH.read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def check_action(action: str) -> PolicyDecision:
    """Look up the policy for an action.

    Returns a deny-by-default PolicyDecision if the action is not in the table,
    routed to IT Service Desk for human review.
    """
    policies = _load_policies()
    record = policies.get(action)

    if record is None:
        return PolicyDecision(
            action=action,
            agent_allowed=False,
            risk_level="high",
            requires=["it_review"],
            escalate_to="IT Service Desk",
            rationale=f"Action '{action}' is not in the policy table; deny by default.",
        )

    return PolicyDecision(
        action=action,
        agent_allowed=record["agent_allowed"],
        risk_level=record["risk_level"],
        requires=list(record.get("requires", [])),
        escalate_to=record.get("escalate_to"),
        rationale=record["rationale"],
    )


def list_actions() -> list[str]:
    """Return the names of all known policy actions. Useful for tests and audits."""
    return sorted(_load_policies().keys())
