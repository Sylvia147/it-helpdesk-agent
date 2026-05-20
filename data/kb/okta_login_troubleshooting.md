# Okta Login Troubleshooting

**Article ID:** KB-IDM-001
**Category:** Identity / SSO
**Last reviewed:** 2026-04-30

## Applies to

Employees who cannot sign in to Okta or applications that use Okta as their SSO provider (Salesforce, Slack, Gmail, GitHub, Snowflake, Tableau, etc.).

## Symptoms covered by this article

- "Invalid username or password" after entering correct credentials
- Login page hangs or returns generic error
- MFA code accepted but redirect fails
- Just got a new device and can't get past MFA

## NOT covered by this article — see linked articles

- **Account is shown as locked** → see KB-IDM-002 *Okta Account Lockout*
- **MFA device lost or replaced** → escalate to Identity Access Management; agents are not authorized to reset MFA

## Step-by-step diagnosis

### 1. Confirm Okta itself is healthy

Check the system status before troubleshooting the user side. If Okta shows a global outage, communicate the status and skip the rest.

### 2. Try a clean browser session

Most "invalid credentials" errors that aren't actually invalid credentials are caused by stale browser state.

1. Open a private / incognito window.
2. Go to `https://sso.acme.com`.
3. Sign in with full corporate email + password.

If sign-in succeeds in private mode, instruct user to clear cookies for `sso.acme.com` and `*.okta.com` in their normal browser.

### 3. Reset password via self-service

If the user genuinely forgot their password:

1. Go to `https://sso.acme.com/reset`.
2. Enter corporate email.
3. Follow the email link (check spam if not received within 2 minutes).
4. Set a new password meeting the policy: ≥ 14 characters, mix of upper, lower, digit, symbol; cannot match last 5 passwords.

### 4. MFA timing issues

If MFA code is "rejected" repeatedly:
- Confirm the user's phone clock is set to network time (a phone with a drifted clock will produce wrong TOTP codes).
- Use the most recent code in the authenticator app, not an older one.
- If the user's number-matching push notification is timing out, ask them to enable notifications for the Okta Verify app.

## Escalate If

Escalate to **Identity Access Management** if:

- Okta admin console shows the account as **locked** (not "wrong password" — explicitly locked).
- User has lost access to their MFA device and password reset link is also tied to that device.
- User reports they did NOT initiate any of the failed attempts (possible credential-stuffing — security incident).
- Self-service reset link does not arrive within 10 minutes despite spam check.

## Common pitfalls

- A locked account shows the same "invalid credentials" message to the end user as a wrong password. Always check Okta admin console (or via `lookup_user`) before sending the user through password reset loops.
- Single-app failures (e.g., can sign into Okta but Salesforce SSO redirect fails) are usually app-specific, not Okta-side. Try other Okta-connected apps to triangulate.
