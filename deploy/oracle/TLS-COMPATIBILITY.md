# HTTPS compatibility for Windows launchers

On 26 October 2026 the ACR Rally Club launcher 0.2.17 reported
`CERTIFICATE_VERIFY_FAILED: certificate has expired` before a player could
start. The live domain leaf was valid until 13 January 2027 and the server
clock was correct. Its ECDSA chain passed through ISRG Root X2. A Python 3.13
probe on Windows reproduced the exact failure when its isolated trust store
contained the valid ISRG Root X1 and an expired historical X2 cross-sign;
the system-default store connected successfully. This models a plausible
client trust store, not a direct inspection of the affected player's PC.

The Caddy site requests `key_type rsa2048`. A new RSA certificate chains
through the Let's Encrypt RSA hierarchy to X1, so the stale X2 cross-sign
cannot enter this path. Certificate and hostname validation in the launcher
stay enabled. No launcher version or game save is changed.

`python tools/check_public_tls.py --check-legacy-x2` checks the real public
endpoint with both the normal trust store and an isolated X1 plus historical
X2 store, verifying the pinned public CA downloads, hostname, expiration,
RSA-path compatibility and `/healthz` response. The Windows and Linux
GitHub Actions job runs this probe whenever the relevant configuration or
diagnostic changes, including on `rally-club`.

Changing Caddy's key type does not replace a valid existing certificate by
itself. During the incident the existing Caddyfile and certificate directory
were saved **on the Oracle VM only** under
`/opt/acr/tls-compat-20261026/` (root access, mode 0700), the site config
was validated, and only the domain certificate directory was moved aside
before a Caddy restart. ACME account state, app, database and other volumes
were not touched. The bounded rotation automatically restores the previous
certificate and config and restarts Caddy if verified RSA HTTPS is not ready.
Retain the on-VM backup until the affected player confirms the result.

If the public probe fails after a future renewal, inspect the live chain,
Caddy logs and server clock before changing any client trust settings. Do
not disable TLS verification or distribute certificate-store changes to
players as a substitute for fixing the server chain.
