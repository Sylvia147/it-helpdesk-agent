# Okta Account Lockout

**Article ID:** KB-IDM-002
**Category:** Identity / SSO / Security
**Last reviewed:** 2026-05-01

## Applies to

Employees whose Okta account has been **locked** by the lockout policy, or who see a "Your account has been locked" message on the sign-in page.

## Important — agent authorization boundary

**Account unlocks are NOT permitted by the IT support agent.** Per policy SEC-IAM-003, all account unlocks must be performed by the Identity Access Management (IAM) team after verifying user identity. This applies regardless of urgency.

If the agent confirms via `lookup_user` or admin tooling that an account is locked, the correct action is **escalate**, with full context:

- Which user
- Lockout reason (if visible — e.g., "5 failed attempts on YYYY-MM-DD HH:MM")
- Urgency (e.g., user has imminent client meeting)
- Any indication of suspicious activity (failed attempts from unfamiliar IPs, etc.)

## Why we do not allow agent self-service unlocks

A locked account has two possible interpretations:

1. **Benign** — the user mistyped their password too many times. Easy to unlock.
2. **Malicious** — an attacker is performing credential stuffing against this account. Auto-unlocking would re-arm the attack.

A human IAM analyst is required to distinguish (1) from (2) by reviewing failed-attempt source IPs, geolocation, and recent travel signals.

## What the agent CAN do

- Confirm the lockout to the user and reduce their anxiety: *"Yes, I can see your account is locked. I'm escalating now and IAM will reach out within minutes."*
- Communicate **expected ETA** based on priority. Standard SLA for IAM unlock requests after handoff:
  - **High priority** (urgent business impact): typically resolved within 15-30 minutes during business hours.
  - **Normal priority**: typically within 2 hours during business hours.
- Suggest **interim workarounds** if possible: e.g., using an already-signed-in session on another device, using mobile apps with cached tokens.
- Provide a clear summary to the IAM handoff so the user does not have to repeat themselves.

## Escalation summary template

When escalating, include:

```
User: <name, role, location, priority>
Issue: Okta account locked
Lockout reason: <e.g., "5 failed login attempts at 2026-05-16 09:12 UTC">
Business impact: <urgency context>
Suspicious indicators: <if any>
Recommended next action: <e.g., "IAM verify identity and unlock; contact via Slack DM">
```

## Related

- KB-IDM-001 *Okta Login Troubleshooting* — for non-locked sign-in issues
- KB-SEC-002 *Reporting Suspicious Login Activity* (out of scope of agent)
