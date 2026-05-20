# demo_1_okta_locked

**User:** u_001 (Alice Chen)
**Expected:** escalate to IAM (account locked)
**Conversation:** `conv_59985634`

## User message

> I can't log into Okta. I reset my password but it still doesn't work. I need access urgently for a client meeting in 30 minutes.

## Tool calls (4)

- ✅ `lookup_user` (0ms)
- ✅ `check_system_status` (1ms)
- ✅ `search_history` (3ms)
- ✅ `escalate` (1ms)

## Agent reply

The escalation is in — here's the summary:

- **Handoff ID:** ESC-20260518-006
- **Routed to:** Identity Access Management
- **Urgency:** High
- **What IAM will do:** Verify your identity and unlock your Okta account. They have the full context and won't need you to repeat anything.

IAM will contact you directly (likely via your mobile or an alternate channel since Okta is inaccessible). If you don't hear back within 10 minutes given your meeting timeline, you can also call the IT emergency line directly and reference handoff ID **ESC-20260518-006**.

## Outcome

- Escalated: **True** → Identity Access Management (ESC-20260518-006)
- Elapsed: 19.1s