# demo_5_jenkins_tableau

**User:** u_005 (Emma Schwartz)
**Expected:** escalate to DevOps (multi-system pipeline)
**Conversation:** `conv_964bc169`

## User message

> Since the IT maintenance window last Friday, our team's automated data pipeline has been failing. Jenkins jobs time out and downstream Tableau reports are stale.

## Tool calls (5)

- ✅ `lookup_user` (0ms)
- ✅ `check_system_status` (0ms)
- ✅ `check_system_status` (0ms)
- ✅ `search_history` (0ms)
- ✅ `escalate` (1ms)

## Agent reply

**Escalation filed — ESC-20260518-005, routed to DevOps, urgency: high.**

DevOps has the full context: the suspected firewall allowlist gap from CHG-2026-0515-001, the matching historical case (hist_003), and the downstream Tableau impact. They should not need anything further from you to start working it.

Based on hist_003, once they restore the egress allowlist entry you can expect:
- Jenkins pipeline reruns to complete within ~30 minutes
- Tableau extracts to refresh within ~2 hours after that

I'd suggest re-running a Jenkins job manually once DevOps confirms the fix, rather than waiting for the next scheduled run. Let me know if anything else comes up.

## Outcome

- Escalated: **True** → DevOps (ESC-20260518-005)
- Elapsed: 26.7s