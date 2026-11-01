# Penn deployment and sign-off

Maximum automation, least friction/involvement, maximum integration and access
within the owner's actual Penn permissions. All five clients call tools directly;
there is no model/agent worker. This deployment keeps real Canvas writes blocked.

## Secure provisioning

Use key-only SSH as `ubuntu` on the approved Ubuntu 26.04 OVH VPS. Access and
secrets must be handed over through the secure environment setup, never chat.
Before adding resources, append/update `SERVER_README.txt` in
`/home/ubuntu/README.txt`, including the actual checkout and deployed revision.

Inspect `/opt/canvas-mcp` Compose/Caddy mounts, current health and networks first.
Never replace its configuration or change Columbia credentials. Check available
resources (4 vCore/8 GB/75 GB). Use `/opt/canvas-pilot-penn` for the fork checkout.

1. Build with `docker compose --env-file deploy/penn/.env -f deploy/penn/compose.yaml build`.
   In the Codex managed environment, supply its combined CA using the Docker
   BuildKit `proxy_ca` secret. Never disable TLS verification. VPS builds use
   normal public CA trust. Ubuntu host and Debian container base are independent.
2. Create `deploy/penn/state` and `deploy/penn/secrets`, mode 0700, owned by UID
   10001 (the container user). Copy `env.example` to `.env` and fill in the dedicated
   sslip.io HTTPS origin, random prefix, Gmail sender/recipient and verified exact callback/login hosts.
3. Provision through a private interactive SSH terminal using
   `python -m src.penn_server.provision init --key-file <key-path> --owner-file <owner-path>`.
   The command refuses to overwrite secrets. Run with server dependencies available.
   Secrets must be readable by UID 10001 only. Never put passwords in shell arguments.
4. Provision Gmail with `python -m src.penn_server.provision gmail --key-file <key-path>
   --state-dir <state-path>`. Hidden input is encrypted immediately. Optionally
   provision PennKey the same way with the `pennkey` action; otherwise capture it
   during initial server-browser login. This does not eliminate Penn-required MFA.
5. Create `penn_proxy`; persistently attach the existing Caddy service to it in its
   Compose configuration. Add only the new site from `Caddyfile.example`, validate
   Caddy's configuration, then reload. Caddy reaches `penn:8000`; publish no port.
6. Start Penn using the Compose command with `up -d`. Verify Columbia still works.
   The dedicated origin exposes OAuth discovery, not Canvas data. No secret URL
   alone authenticates MCP or the browser viewer.
7. Open `<origin><prefix>/login` if automatic initial recovery cannot complete.
   Sign in with the connector owner password and interact with the temporary
   server browser. Select Duo browser trust. No cookies are copied to local chat.
8. Connect each of Grok chat, ChatGPT chat, Dot, Grok Bot and Codex using
   `<origin><prefix>/mcp`. Register only exact callbacks that each supported client
   actually supplies. Use the server's OAuth sign-in and independent grants.
   Client UI/import support and available subscription features must be verified;
   an MCP server alone cannot install itself into these products.

## Recovery and security

A read-only daily scan/reminder runs after 09:00 America/New_York within the
server maintenance loop; clients can also invoke `scan_canvas` directly. It
never launches a model worker or submits coursework.

Heartbeat probes `/users/self` every 12 minutes, retries one 401, queues email and
recovers automatically. Restore full browser/SSO/Duo state before falling back to
stored PennKey credentials. A durable reservation precedes login navigation,
because Duo may initiate a push automatically. One recovery navigation is allowed
per incident; no resend/retry button is clicked. A crash after reservation can
require manual recovery rather than risk a second push. Manual actions remain
visible and controlled by the owner. Browser trust is Penn-controlled; expiry or
policy resets may require Duo sooner than 60 days.

Profile files are decrypted on tmpfs only. Closed-profile checkpoints and session
cookies are encrypted atomically; the key is mounted separately. Browser version
and profile identity remain stable. No HAR, video, disk screenshots, access logs,
request bodies or passwords are logged. Browser images exist transiently in the
HTTPS viewer, which expires after ten minutes or successful login.

The master key protects offline state, not a compromised running host. Preserve
keys separately from encrypted backups. Never run two replicas over one volume.

## Validation and honest sign-off

Offline tests use simulated browser/Canvas/SMTP responses. Real-course checks
must be reads only, with `PENN_TESTING_READ_ONLY=true` retained in Compose. Do not
start quizzes, submit assignments, send messages, mark read/done, post reviews,
or modify calendar/planner state. Do not enable writes to test write handlers.

Live write tools are UNTESTED, even after simulation tests pass. Record live
read/session/login/viewer tests and every client integration separately. No staff
or other-student gradebook tools are registered. New Quizzes and anonymous
REST-inaccessible discussions need explicit capability reporting, not fallback
claims. Verify actual Penn login hosts and Duo flow before acceptance.

No server has been changed merely by adding these deployment files to the repo.
