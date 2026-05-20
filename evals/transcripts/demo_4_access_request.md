# demo_4_access_request

**User:** u_004 (David Kim)
**Expected:** self-serve Grafana, escalate Snowflake prod to Data Platform
**Conversation:** `conv_13d947d9`

## User message

> I just joined the Data Engineering team and need access to the Snowflake production database and internal Grafana dashboards.

## Tool calls (6)

- ✅ `lookup_user` (0ms)
- ✅ `check_system_status` (0ms)
- ✅ `check_system_status` (0ms)
- ✅ `search_kb` (0ms)
- ✅ `search_kb` (0ms)
- ✅ `escalate` (1ms)

## Agent reply

The Snowflake request has been handed off to the **Data Platform team** (handoff ID: **ESC-20260518-004**). They'll coordinate approval with your manager and the data-owner. You can expect to hear back via email — no need to re-explain anything, the full context is included.

**Summary of next steps for you:**

| Request | Action |
|---|---|
| Snowflake production access | Handled — Data Platform team will reach out for approvals |
| Grafana read-only access | Self-service now via `grafana.acme.com` → Okta sign-in → Access Portal |

Let me know if you run into any issues with the Grafana self-service flow.

## Outcome

- Escalated: **True** → Data Platform (ESC-20260518-004)
- Elapsed: 21.6s