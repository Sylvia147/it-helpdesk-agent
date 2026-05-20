# Jenkins Job Timeout Runbook

**Article ID:** KB-CICD-001
**Category:** CI/CD / Build Infrastructure
**Last reviewed:** 2026-05-01

## Applies to

Engineers and data engineers whose Jenkins jobs are timing out, hanging, or failing with network-related errors.

## Step-by-step diagnosis

### 1. Check for recent maintenance windows

Always check `check_system_status("jenkins")` first and look at the `recent_changes` field. Maintenance-window changes — especially firewall, network, or cert rotations — are the **most common cause of post-Friday Jenkins failures**.

If a recent change is listed and the symptoms started after that change, this is very likely a **post-change incident**. Skip ahead to Section 4.

### 2. Inspect job logs for the failure mode

Common failure modes and what they typically mean:

| Log signature | Likely cause |
|---|---|
| `Connection timed out` to `nexus.acme.com` or `pypi-mirror.acme.com` | Egress firewall change blocked artifact mirror |
| `SSLHandshakeException` to internal hosts | Cert rotation not propagated to agents |
| `Build step failed: 137` | Out-of-memory kill (OOMKilled) on the agent |
| Job hangs with no log output | Agent itself is unresponsive — look at agent VM metrics |

### 3. Check agent health

Run `check_system_status("jenkins")` and look at agent counts. Compare to baseline. If agent count is below normal, escalate to DevOps — agents are likely failing to register.

### 4. Post-maintenance pattern (high signal)

If all of the following are true:

- A maintenance window happened in the past 72 hours.
- Jobs that previously succeeded are now timing out.
- Multiple unrelated jobs are affected.
- Errors involve network egress or artifact fetch.

Then the maintenance window almost certainly broke something. **Escalate to DevOps with the following context:**

- Maintenance window change ID
- Which jobs are failing and the common error signature
- Which downstream services are affected (e.g., Tableau dashboards stale because their data refresh comes from these jobs)

This is a high-confidence escalation, not a wait-and-see. Do not have the user wait for the next maintenance review meeting; firewall rule restorations are typically same-day fixes.

### 5. Single-job, non-network failures

If a single job is failing and the failure is in build logic (test failures, compile errors), this is **not an IT issue**. Direct the user to their team's on-call engineer or build owner.

## Multi-system patterns to recognize

When Jenkins issues co-occur with stale data in downstream systems (Tableau dashboards not refreshing, dbt models not running, scheduled reports stale), the agent should treat this as a **data pipeline incident**, not as separate issues. The pipeline view:

```
Jenkins jobs → Snowflake / S3 staging → dbt / Spark → Tableau extracts
```

A break anywhere upstream causes staleness everywhere downstream. Diagnosing only the downstream symptom (stale Tableau) without checking upstream (Jenkins) wastes time.

## Escalate If

Escalate to **DevOps / Data Platform** if:

- Symptoms align with a recent maintenance window.
- Multiple unrelated jobs are failing with network errors.
- Agent fleet is unhealthy.
- Downstream stale data confirms a pipeline-level outage.
- The build owner has confirmed it is not a code issue.

The handoff should include:

- Affected jobs and the common log signature
- Maintenance change ID (if relevant)
- Downstream impact (what teams are blocked, which dashboards are stale)
- Estimated business impact (e.g., "morning exec dashboards will be empty if not fixed by 8am")

## Related historical cases

- Maintenance-window firewall rule blocked artifact mirrors: `hist_003`
- Tableau blank charts after schema change: `hist_021`
