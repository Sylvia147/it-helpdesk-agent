"""Lightweight scope guard for clearly non-IT requests.

This is deliberately small and conservative. Ambiguous workplace problems still
go to the agent so it can ask a clarifying question; only obvious non-company-IT
requests get a deterministic fallback before any tool or LLM call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeDecision:
    """Result of the lightweight scope check."""

    out_of_scope: bool
    category: str | None = None
    reason: str | None = None


_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "personal_device",
        "personal/home equipment is outside enterprise IT support",
        re.compile(
            r"(?=.*\b(personal|home|my own)\b)(?=.*\b(fax|printer|router|modem|tv|gaming|xbox|playstation)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "hr",
        "HR policy questions are outside IT support",
        re.compile(
            r"\b(payroll|benefits|pto|vacation policy|performance review|offer letter|compensation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "finance",
        "Finance and expense questions are outside IT support",
        re.compile(
            r"\b(expense report|reimbursement|invoice|purchase order|tax form|w-2|1099)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "legal",
        "Legal questions are outside IT support",
        re.compile(
            r"\b(contract review|nda|legal advice|lawsuit|terms of service|data processing agreement)\b",
            re.IGNORECASE,
        ),
    ),
)


def classify_scope(text: str) -> ScopeDecision:
    """Return out-of-scope only for clear, high-confidence non-IT requests."""
    normalized = text.strip()
    if not normalized:
        return ScopeDecision(out_of_scope=False)

    for category, reason, pattern in _PATTERNS:
        if pattern.search(normalized):
            return ScopeDecision(
                out_of_scope=True,
                category=category,
                reason=reason,
            )

    return ScopeDecision(out_of_scope=False)


def out_of_scope_reply(decision: ScopeDecision) -> str:
    """Consistent user-facing fallback for clear non-IT requests."""
    reason = decision.reason or "this looks outside company IT support"
    return (
        f"I can help with company IT systems, accounts, devices, network access, "
        f"and approved workplace tools. This request looks outside that scope: "
        f"{reason}.\n\n"
        "I don't want to give unreliable instructions. If this is affecting a "
        "company-managed device, account, or internal service, tell me which one "
        "and I'll help from there."
    )
