# Milestone 1 review status

## Implemented locally

- Server-managed OAuth with exact allowlisted callbacks, S256 PKCE, single-use
  codes, expiring tokens, refresh rotation/replay revocation and client grants.
- Streamable HTTP, student-only tool manifest and direct client invocation.
- Authenticated temporary browser viewer, scoped credential capture, encrypted
  complete profile/cookie/PennKey state and separate master-key storage.
- Twelve-minute heartbeat, automatic recovery and durable one-login-attempt
  reservation per incident, including across restarts. No automatic push resends.
- The new Penn server uses local-only logs and requires no mail transport or alert credentials.
  Original package email utilities remain available independently.
- Docker restart=always and supervised recovery from persistent maintenance crashes.
- Server-side read-only daily scans; no separate model worker.
- Write guards below dispatch and at browser/upload boundaries. Testing Compose
  forces read-only mode. Write handlers are live-untested.
- Humanizer engines, skill families and prose handoffs restored in full.
- Original package quiz pacing/focus/strategic misses, event posting, diagnostics,
  scheduled auto-submit and legacy email features restored with their original tests.
- Separate Docker/Caddy deployment files and the required VPS README section.

## Local evidence

- 34 Penn-server offline tests pass: auth, protocol-level MCP calls, encrypted
  storage, recovery/restart reservations, write blocks, mock write encoding,
  confirmation replay, uncertain outcomes, local logging, supervised restart, scheduling and downloads.
- Regression suite excluding the pre-existing uncollectable guard-kernel module:
  453 passed, 1 skipped. The guard-kernel module imports missing
  `scripts/push_public_snapshot.py`, absent from the original commit.
- Codex runtime fixture suite and plugin drift checks pass.
- Docker image builds, including Chromium downloads and native dependencies.
- Chromium smoke test passes as non-root in a read-only container with network
  disabled: synthetic session cookies and the full profile survive encrypted
  checkpoint/restart. No Penn traffic is involved.
- Real server startup/health passes with networking disabled and no mail credentials.
- Python correctness lint and `git diff --check` pass.
- Exact scope restorations are recorded in `RESTORATIONS.md`; restored course,
  artifact, annotation, zyBooks and standalone syntax tests pass.

The legacy automation/onboarding runners fail because CODEX_AUTOMATION.md and
CODEX_ONBOARDING.md are absent. Two advanced-hook session-marker checks also
fail. These same failures were reproduced in an untouched worktree of baseline
commit `6b79d5b`; they are not claimed as passing.

## Pending secure access and live read-only validation

No OVH server changes, Penn requests or real Canvas writes were
performed during local implementation. `/home/ubuntu/README.txt` must be updated
before adding Penn resources to the VPS; the supplied section is a template,
not a claim that the server file has already changed.

| Integration | Current status |
| --- | --- |
| Grok chat | Server endpoint implemented; client setup/compatibility unverified |
| ChatGPT chat | Server endpoint implemented; client setup/compatibility unverified |
| Dot | Server endpoint implemented; client setup/compatibility unverified |
| Grok Bot | Server endpoint implemented; client setup/compatibility unverified |
| Codex | Server endpoint implemented; client setup/compatibility unverified |
| PennKey/Duo | Generic adapter implemented; actual Penn selectors/trust behavior unverified |
| Existing Columbia Caddy | Deployment adapter supplied; actual config/pattern not inspected |

Next: securely provision SSH access, inspect existing Caddy and
Columbia sign-in, deploy to the dedicated sslip.io origin, verify Penn redirects
and identity, exercise read tools and recovery, and configure the five clients.
All real writes must stay blocked throughout this validation. Real Duo behavior,
New Quizzes and student peer-review/rubric endpoint permissions require honest
capability reporting; simulations cannot establish these live capabilities.
