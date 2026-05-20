# Grafana Access Policy

**Article ID:** KB-DATA-002
**Category:** Data Platform / Access Governance
**Last reviewed:** 2026-04-30

## Applies to

Employees requesting access to internal Grafana dashboards (`grafana.acme.com`).

## Quick summary

Internal Grafana access is **read-only by default** and **self-service** via Okta groups, provided the user is on a team that the relevant dashboards belong to.

| Access level | Self-service? | Process |
|---|---|---|
| Read-only (view dashboards only) | ✅ | Self-service via access portal |
| Editor (create/modify dashboards) | ❌ | Requires manager approval; escalate |
| Admin (manage data sources) | ❌ | Restricted to platform team only |

## Self-service read-only access

The agent can directly walk the user through this:

1. Go to `https://access.acme.com/request/grafana`.
2. Select **Grafana — Read Only**.
3. The form auto-detects team membership from the HR system. If the user is on a team that already has Grafana access, they will be added to the Okta group `grafana-readers` automatically within 15 minutes.
4. If team membership is not yet provisioned (e.g., new hire on their first day), the agent should confirm the user's team via `lookup_user` and note in the escalation handoff that team membership needs to land first.

## Editor and admin access — escalate

For editor or admin requests, escalate to the **Data Platform Team** with:

- User identity and team
- Justification (which dashboards they need to edit; why view-only is insufficient)
- Manager name (manager approval is required)

## Common questions

**Q: Why does Grafana not require data owner approval like Snowflake?**

A: Grafana dashboards display **aggregated metrics**, not raw rows. The data is governed at the source (e.g., Snowflake). Read-only Grafana access exposes only what the dashboard authors have intentionally surfaced.

**Q: Can I get access to a specific dashboard without team-wide access?**

A: Grafana folder permissions are managed per team, not per dashboard. If a user needs visibility into one dashboard owned by a team they are not on, the recommended path is for the dashboard owner to either (a) republish a public-readable copy in the cross-functional folder, or (b) the user requests team-affiliated access through their manager.

## What the agent CAN do directly

- Verify team membership via `lookup_user`.
- Provide the self-service URL.
- Set expectations: 15-minute provisioning after access portal submission.
- Confirm whether the dashboards the user is asking about are within their team's scope.

## Escalate If

- Editor or admin access requests.
- Cases where the user is requesting access on behalf of someone else.
- Cases where team membership in HR system is incorrect (HR data fix needed first).

## Related

- KB-DATA-001 *Snowflake Access Policy*
- Resolution history `hist_009` — typical Grafana read-only request flow
