# VPN Disconnect Runbook

**Article ID:** KB-NET-001
**Category:** Network / VPN
**Last reviewed:** 2026-05-05

## Applies to

Employees using the corporate VPN (Cisco AnyConnect) who experience repeated disconnects, slow throughput while on VPN, or partial connectivity (connected but cannot reach internal resources).

## Step-by-step diagnosis

Before starting, confirm the VPN service itself is operational. If there is an active VPN incident, communicate that and stop here.

### 1. Identify the disconnect pattern

Ask the user:

- **Does it disconnect at a regular interval** (e.g., every 10-15 minutes)? → likely **MTU mismatch** — go to Section 2.
- **Does it disconnect randomly under load** (large file transfers, video calls)? → likely **MTU or upstream throughput** — go to Section 2.
- **Does it connect but cannot reach internal hosts**? → likely **split-tunnel routing** — go to Section 3.
- **Does it not connect at all**? → likely **client config / credential / cert** — go to Section 4.

### 2. MTU mismatch (most common for residential ISP users)

Symptoms: regular disconnects every ~10 minutes, especially on residential cable / DSL / fiber that uses PPPoE.

Steps:

1. Open the AnyConnect client → **Preferences** → **Advanced** → **Connection**.
2. Find the **MTU** field.
3. Lower it from the default **1500** to **1300**.
4. Disconnect and reconnect.
5. Test for 30 minutes.

If symptoms resolve, the issue was MTU. If not, escalate.

### 3. Split-tunnel routing

Symptoms: VPN reports connected, but specific internal hostnames (Jira, internal Grafana, internal artifact mirrors) fail to resolve or connect.

Steps:

1. Run `nslookup <internal-hostname>` and check whether it resolves to a private IP.
2. Run `traceroute <internal-hostname>` and check whether the first hop goes through the VPN gateway.
3. If the route is not going through VPN, the user's split-tunnel config is missing the relevant subnet.
4. Recommend the user disconnect and reconnect VPN to fetch the latest config; the routing table is refreshed each session.

If the latest config still doesn't include the subnet, escalate to Network Engineering — the central VPN config needs an update.

### 4. Client cannot connect at all

Steps:

1. Confirm the user is reaching the VPN endpoint (try `ping vpn.acme.com`).
2. Confirm credentials work via Okta (sign in to `sso.acme.com`).
3. Reinstall the AnyConnect client from the company portal.
4. If the cert is expired (visible in client diagnostics), trigger cert renewal via MDM.

### 5. Slow throughput while on VPN

Common causes:

- Home Wi-Fi congestion → recommend switching to wired or moving closer to AP.
- ISP issues → run `speedtest.net` outside VPN to compare.
- Backhaul saturation at the VPN concentrator → escalate to Network Engineering with timestamp; they can check load metrics.

## Escalate If

Escalate to **Network Engineering** if:

- All troubleshooting steps in Sections 2-4 have been tried without resolution.
- Multiple users in the same office or region report the same symptoms (likely infrastructure issue).
- Diagnostic logs show repeated tunnel renegotiation with no obvious cause.
- VPN concentrator metrics need to be inspected (only Network Eng has access).

## Related historical cases

- VPN MTU mismatch (residential cable): see resolution history `hist_001`.
- VPN connected but Jira unreachable (split-tunnel routing): `hist_006`.
- DNS intermittent failure on VPN: `hist_020`.
