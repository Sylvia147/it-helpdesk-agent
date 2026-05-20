# Snowflake Access Policy

**Article ID:** KB-DATA-001
**Category:** Data Platform / Access Governance
**Last reviewed:** 2026-04-30

## Applies to

Employees requesting access to Snowflake databases, warehouses, or schemas.

## Important — agent authorization boundary

**Snowflake production access cannot be granted by the IT support agent.** Per data governance policy DG-001:

| Environment | Agent self-service? | Approvers required |
|---|---|---|
| Production (`PROD_*` databases, `ANALYTICS_PROD`) | ❌ Must escalate | Line manager **AND** dataset data-owner |
| Development (`DEV_*` databases) | ❌ Must escalate | Line manager only |
| Sandbox (`SANDBOX_*`) | Indirect — see below | None for default sandbox; manager for shared sandboxes |

The agent's role is to:

1. Confirm the user is on a team that legitimately needs the requested access.
2. Generate a complete access-request handoff to the **Data Platform Team**.
3. Surface the list of required approvers so the user understands the timeline.

## Why two approvers for production

Production data may include customer PII, financial records, and partner-confidential information. Two-party approval (manager + data owner) is required by:

- Internal data governance policy DG-001
- SOX controls for financial reporting datasets
- Customer DPA agreements for regions with strict data handling requirements

A single approver creates a custodial single-point-of-failure that has been a finding in past audits.

## Identifying the data owner

| Database / domain | Data owner role |
|---|---|
| `ANALYTICS_PROD`, all `PROD_*` general analytics | Director of Data Platform |
| `FINANCE_PROD` | VP of Finance |
| `SALES_PROD` | VP of Sales |
| `HR_PROD`, `PEOPLE_*` | VP of People Operations |

If the user is unsure which database they need, the agent should ask:

- What is the primary use case? (e.g., dashboards, ad hoc analysis, ETL pipeline.)
- What datasets do they need? (Specific tables / schemas, not just the database name.)
- What level of access? (Read, read+write, or warehouse compute only.)

## What the agent CAN do directly

- **Provide the access request URL**: `https://access.acme.com/request/snowflake`.
- **Pre-fill the request fields** in the escalation handoff (user name, manager, team, dataset, justification).
- **Set expectations**: production access requests typically take 1 business day after both approvals are granted.
- **Recommend interim workarounds**: if the user only needs to view aggregated data, point them to existing Tableau dashboards (which are derived from production data but governed separately).

## What the agent should NOT do

- Do not grant access by writing SQL `GRANT` statements (the agent has no DB credentials and would not be authorized even if it did).
- Do not promise a timeline shorter than 1 business day.
- Do not suggest workarounds that bypass governance (e.g., asking a teammate to share their credentials — explicit policy violation).

## Escalation handoff template

```
Requested access: Snowflake [environment] — [database / schema / table]
User: <name, role, team, manager>
Use case: <free-text>
Required approvers:
  - Manager: <name>
  - Data owner: <role / name>
Recommended SLA: 1 business day after both approvals
```

## Related

- KB-DATA-002 *Grafana Access Policy* — read-only observability, self-service
- KB-DATA-003 *Tableau Viewer Access* (out of scope here)
