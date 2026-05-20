# Maintenance Window Calendar

**Article ID:** KB-OPS-001
**Category:** Operations / Change Management
**Last reviewed:** 2026-05-16

## Purpose

This is the rolling log of recent and upcoming planned maintenance windows. Use it to correlate user-reported issues with recent infrastructure changes.

## Recent maintenance windows (most recent first)

### 2026-05-15 (Friday) — Network Firewall Rule Update

- **Window**: 2026-05-15 22:00 UTC — 2026-05-16 02:00 UTC
- **Change ID**: CHG-2026-0515-001 (Jenkins egress) and CHG-2026-0515-002 (Tableau dependency)
- **Performed by**: DevOps / Network Engineering
- **Summary**: Tightened the corporate egress firewall allow-list for outbound traffic from internal CI agents.
- **Known impact**: Jenkins agents may experience timeouts when reaching internal artifact mirrors (Maven, PyPI, npm). Downstream Tableau extracts may show stale data because they depend on Jenkins-run pipelines.
- **Status**: Window completed; some downstream symptoms reported.

### 2026-05-08 (Friday) — Okta Provider Routine Update

- **Window**: 2026-05-08 02:00 UTC — 02:30 UTC
- **Change ID**: CHG-2026-0508-001
- **Performed by**: Identity Access Management
- **Summary**: Routine Okta tenant configuration update; rotated MFA-related signing keys.
- **Known impact**: None.

### 2026-04-28 (Monday) — Snowflake Warehouse Resize

- **Window**: 2026-04-28 06:00 UTC — 07:00 UTC
- **Change ID**: CHG-2026-0428-002
- **Performed by**: Data Platform
- **Summary**: Resized `ANALYTICS_PROD` virtual warehouse from XL to 2XL to handle increased query load.
- **Known impact**: None; transparent change.

### 2026-04-21 (Monday) — VPN Concentrator Patching

- **Window**: 2026-04-21 03:00 UTC — 04:00 UTC
- **Change ID**: CHG-2026-0421-003
- **Performed by**: Network Engineering
- **Summary**: Patched VPN concentrators with vendor security update.
- **Known impact**: 30-second connection drop during failover; users were notified in advance.

## Upcoming maintenance

### 2026-05-22 (Friday) — Jenkins Master Upgrade

- **Window**: 2026-05-22 22:00 UTC — 2026-05-23 01:00 UTC
- **Change ID**: CHG-2026-0522-001
- **Owner**: DevOps
- **Expected impact**: Jenkins UI will be unavailable for 1-2 hours; queued jobs will resume after upgrade.

## How the agent uses this

When a user reports a problem that started recently, cross-reference with this calendar. If their symptom timing aligns with a maintenance window, treat that as a high-prior hypothesis and use the change ID in any escalation handoff.

For Jenkins / Tableau / data pipeline issues specifically, see KB-CICD-001 *Jenkins Job Timeout Runbook* — that article goes into more depth on post-maintenance failure modes.
