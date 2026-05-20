# Salesforce Slow Loading

**Article ID:** KB-SAAS-001
**Category:** SaaS / Sales Tools
**Last reviewed:** 2026-04-12

## Applies to

Employees experiencing slow page loads, slow record saves, or intermittent failures in Salesforce.

## Step-by-step diagnosis

### 1. Always check Salesforce status first

Run `check_system_status("salesforce")`. Salesforce is heavily affected by upstream regional incidents that have nothing to do with our internal infrastructure. If a known incident is in progress in the user's region, **communicate that and skip the rest** — there is no client-side fix.

External reference: `https://trust.salesforce.com`

### 2. Confirm regional impact

If a status incident is reported for a specific region (e.g., Midwest CDN degradation affecting Chicago users), check the user's location via `lookup_user`. If it matches the affected region, this is the same issue.

Recommended user-facing message:

> Salesforce is currently experiencing degraded performance in [region] due to a known issue on their side (incident [ID]). They are investigating. As a workaround, you can [workaround from incident record]. I'll have the agent check back if you need an update later.

### 3. Common workarounds for regional latency

- **Use the Salesforce Mobile app** — it routes through different infrastructure and is often unaffected.
- **Connect via VPN with East Coast egress** — can bypass affected regional CDN nodes (works for Midwest CDN issues specifically).
- **Wait for offline data sync** — for users who only need read access to recently viewed records, the desktop app's offline cache may serve them.

### 4. Single-user slowness (no regional incident)

If status is operational and only one user is affected, the issue is local. Check:

- **Browser**: Salesforce officially supports the latest 2 versions of Chrome / Safari / Firefox / Edge. Older versions may misbehave.
- **Browser extensions**: Ask the user to try a private window with extensions disabled. Some ad blockers or privacy extensions break Salesforce's Lightning runtime.
- **Network**: Run a `speedtest` and `traceroute trust.salesforce.com`.
- **Custom dashboards**: Heavy custom Lightning components can slow specific pages. Compare to a standard list view to confirm.

### 5. Salesforce-side configuration issues

If a specific report or dashboard is slow but other Salesforce pages are fast:

- The query may be unoptimized (missing indexed filters, large date ranges).
- Recommend the user contact their Salesforce admin (Sales Operations) for query tuning.
- This is not an IT issue per se; it is a Salesforce admin concern.

## Escalate If

Escalate to **IT Service Desk** if:

- Multiple users in different regions report the same issue and Salesforce status shows operational (possible our-side issue).
- A user has a P0 customer-facing meeting and standard workarounds do not work — IT Service Desk has Salesforce premier support contact.
- The user reports data integrity issues (records missing, duplicates) — this needs a Salesforce admin not the IT agent.

## Related historical cases

- Salesforce Chicago regional CDN degradation: `hist_002`
- Salesforce scheduled report not sending (ownership issue): `hist_023`
