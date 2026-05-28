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
    """Result of the lightweight scope check.

    scope guard 的判断结果。frozen=True 表示创建后不可修改，适合这种
    简单的“判断结果值对象”。
    """

    out_of_scope: bool
    category: str | None = None
    reason: str | None = None


# Conservative regex rules for obvious non-IT requests.
# 这里故意只写“高置信度”的非 IT 正则，避免把模糊但可能是工作 IT
#     的问题误拦截掉。模糊问题应该进入 LLM，让 agent 追问澄清。
# VPN/network terms are intentionally not in the personal-device keyword list:
# phrases like "my own VPN" can still be company IT problems and should reach the LLM.
# VPN/network 相关词故意不放进个人设备关键词列表；比如 "my own VPN"
# 仍可能是公司 IT 问题，应该交给 LLM 判断。
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
    """Return out-of-scope only for clear, high-confidence non-IT requests.

    这是一个轻量前置过滤器，不负责完整意图识别；只拦明显的 HR、
    Finance、Legal、个人设备/家庭设备问题。
    """
    normalized = text.strip()
    if not normalized:
        # Empty input is not treated as out of scope; main.py ignores it anyway.
        # 空输入不算越界，main.py 会直接跳过。
        return ScopeDecision(out_of_scope=False)

    for category, reason, pattern in _PATTERNS:
        if pattern.search(normalized):
            # First matching rule wins; categories are only for trace/tests.
            # 命中任一规则就返回越界；category 主要给测试和解释用。
            return ScopeDecision(
                out_of_scope=True,
                category=category,
                reason=reason,
            )

    return ScopeDecision(out_of_scope=False)


def out_of_scope_reply(decision: ScopeDecision) -> str:
    """Consistent user-facing fallback for clear non-IT requests.

    统一的用户回复：说明 agent 的 IT 范围，并邀请用户重新描述
    公司设备/账号/内部服务相关的问题。
    """
    reason = decision.reason or "this looks outside company IT support"
    return (
        f"I can help with company IT systems, accounts, devices, network access, "
        f"and approved workplace tools. This request looks outside that scope: "
        f"{reason}.\n\n"
        "I don't want to give unreliable instructions. If this is affecting a "
        "company-managed device, account, or internal service, tell me which one "
        "and I'll help from there."
    )
