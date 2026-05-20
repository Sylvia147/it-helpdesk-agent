# demo_2_salesforce_slow

**User:** u_002 (Bob Martinez)
**Expected:** resolve with known incident workaround
**Conversation:** `conv_5377f27f`

## User message

> Salesforce has been loading extremely slowly since this morning. My teammates in the Chicago office are seeing the same thing.

## Tool calls (2)

- ✅ `check_system_status` (0ms)
- ✅ `search_history` (0ms)

## Agent reply

This is a known, active incident — and it matches a pattern seen before (hist_002).

**What's happening:** There's an ongoing Salesforce regional CDN degradation affecting Chicago and the broader Midwest (incident **SF-INC-2026-0515-003**). Salesforce engineering is actively investigating. Page loads are taking 30–60 seconds, and record saves may fail intermittently.

**Workaround options while it's being resolved:**

1. **Corporate VPN (East Coast egress):** Connect to the VPN and select the East Coast routing option. This routes your traffic around the degraded Midwest CDN node and should restore normal Salesforce performance for urgent work.
2. **Salesforce Mobile app:** The mobile app is unaffected and can be used for time-sensitive client work.

**What to expect:** Salesforce ops is investigating with no firm ETA yet. You can track live updates at [status.salesforce.com](https://status.salesforce.com).

Do you need help connecting to the VPN with East Coast routing, or is there anything else I can help with?

## Outcome

- Escalated: **False**
- Elapsed: 10.3s