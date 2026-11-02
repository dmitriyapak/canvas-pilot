Penn Canvas Pilot 2.0
Append/update this section in /home/ubuntu/README.txt BEFORE adding Penn server resources.

Purpose: single-owner Penn Canvas connector for Grok chat, ChatGPT chat, Dot,
Grok Bot and Codex. No separate agent/workflow worker.
Source/checkout: /opt/canvas-pilot-penn (record exact deployed commit).
Compose project: canvas-pilot-penn; config: deploy/penn/compose.yaml.
Existing proxy: caddy:2, managed under /opt/canvas-mcp; preserve Columbia.
Network: penn_proxy, shared only with Caddy. No public application port.
HTTPS hostname and connector URL: fill in on deployment; do not record secret prefix here.
Configuration: deploy/penn/.env, non-secret settings; restrict access regardless.
Encrypted state: deploy/penn/state; includes browser profile, cookies, PennKey
credentials, OAuth grants and recovery incidents. No alert credentials or mail transport.
Master key: deploy/penn/secrets/master_key; never copy into state backups.
Connector owner password: deploy/penn/secrets/owner_password. Never print either file.
Runtime browser profile: container tmpfs /run/penn-browser, erased on stop.
Testing: all real Canvas writes BLOCKED; write tools live-untested.
Operations (from checkout): docker compose --env-file deploy/penn/.env -f deploy/penn/compose.yaml ps
Logs: deploy/penn/state/logs/server.log (bounded, local only) and compose logs --tail 100 penn.
Automatic recovery: restart=always, heartbeat, encrypted state, automatic re-login.
Three consecutive unexpected maintenance failures request a graceful process restart.
No access/body logging.
Restart: same compose command with restart penn. Browser state restores encrypted.
Stop: same compose command with stop penn. Do not use down -v.
Rollback: stop Penn, check out previous reviewed commit, rebuild/start Penn.
Backups: encrypted state only, with separately protected recovery copies of keys.
Removal: stop Penn, remove its Caddy site/network attachment, validate/reload
Caddy, remove only Penn resources after deciding retention. Do not remove Columbia.
Update this section for every server addition or operational change.
Production profile: add -f deploy/penn/compose.production.yaml to the Compose command.
The production override enables registered write tools; testing uses the base file only.
Production verification remains read-only. No scheduled job is activated by this override.
Record the exact deployed PR commit and active profiles here before starting the service.


Pending Panopto addition (NOT DEPLOYED; append to /home/ubuntu/README.txt only
when the corresponding Penn deployment actually occurs):
Three read-only MCP tools list Panopto lectures, read timestamped captions and
read the owner's All Time Percent Completed. Panopto cookies use the existing
Vault encryption; LTI authentication reuses the Canvas session manager. No
playback, heartbeats or viewing-event writes are permitted. See PANOPTO.md for
validation blockers, exact deployment commands and remaining live checks.
Record exact deployed commit and real-course validation results at deployment.
