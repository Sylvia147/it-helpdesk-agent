# demo_3_vpn_disconnect

**User:** u_003 (Carol Wang)
**Expected:** resolve with VPN troubleshooting steps (MTU)
**Conversation:** `conv_3a68e6b6`

## User message

> My VPN keeps disconnecting every 10-15 minutes. I'm working remotely and can't access internal tools.

## Tool calls (3)

- ✅ `check_system_status` (1ms)
- ✅ `search_kb` (7ms)
- ✅ `search_history` (3ms)

## Agent reply

Good news: the VPN service itself is fully operational — no active incidents or recent changes. This points to a local/ISP-side issue, and the pattern you're describing is a strong match for a known fix.

**Most likely cause: MTU mismatch** (hist_001, KB-NET-001)

Past tickets show this exact symptom — disconnects every 10-15 minutes on residential internet — is almost always caused by an MTU mismatch. Your ISP's connection has a lower effective MTU than the VPN tunnel's default (1500), so large packets get fragmented or dropped, forcing the VPN to renegotiate until it eventually times out.

The fix that's resolved this in every prior case: **lower the VPN client's MTU to 1300**.

Here's how to do it in Cisco AnyConnect:

1. Disconnect from the VPN if currently connected.
2. Open **AnyConnect** → click the **gear icon** (Preferences).
3. Go to the **Advanced** tab.
4. Find **MTU** (or "Packet Size") and change the value to **1300**.
5. Save, then reconnect to the VPN.

After reconnecting, stay connected for ~15 minutes to confirm the drops have stopped.

A secondary thing worth trying if the MTU change doesn't fully resolve it:

- **Flush your DNS cache**: open Terminal and run `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`
- Then reconnect and test.

Are you currently connected or fully dropped? And is this on home WiFi or wired ethernet? That'll help narrow things down if the MTU fix doesn't hold.

## Outcome

- Escalated: **False**
- Elapsed: 16.6s