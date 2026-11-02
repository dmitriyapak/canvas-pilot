# Panopto read-only tools (draft, not deployed)

Adds list_panopto_lectures(course|folder), get_panopto_transcript(session_id),
and get_panopto_progress(course?). Course arguments are numeric Canvas IDs;
folder/session arguments are Panopto UUIDs. Call listing with a course first to
establish a recoverable LTI launch for folder-only/transcript/progress calls.

The tools reuse the Penn SessionManager and Canvas browser cookie jar, submit
LTI forms using HTTP without executing a player, and save Panopto cookies in a
separate encrypted Vault record. Expired API/caption access retries LTI once.
The personal dashboard uses an isolated browser with only analytics resources
and read service methods allowed. Media, viewer pages, viewing-event writes and
heartbeats are blocked. All results carry untrusted=true. Missing completion
percentages remain null; view counts are never converted to completion.

Validation so far: 15 new offline tests pass. The existing 16 async security
tests pass with a temporary asyncio pytest adapter (pytest-asyncio is absent).
Python compilation passes. The complete suite has NOT passed: restored-feature
collection requires a courses.yaml or SECRETS.md absent from the supplied
checkout; synchronous security tests using TestClient hung and were interrupted.
Installed runtime versions differ from requirements-server.txt.

Required before production: verify Canvas course-navigation LTI discovery,
folder ID extraction, GetSessions response fields/pagination, GenerateSRT
caption access, the owner's User Dashboard identity, All Time selection,
See All table selectors, analytics request allowlist, and pagination against
one real Penn course. These are implementation assumptions, not live-verified
Penn contracts. Do not claim the task's acceptance criteria have been met.
If the live course exposes lecture-only LTI links, add verified module/page
launch discovery before release. Dashboard authentication expiry during a read
currently fails closed; a new call re-launches LTI.

Deployment blocked: this task environment has no SSH credential and no TCP
network grant for ubuntu@135.148.166.236:22. Its Git proxy is unreachable, so
source was read and the draft committed with the connected GitHub API.
No VPS files, services, or Columbia resources have been changed.

When access is available, update /home/ubuntu/README.txt with the exact commit
and validation state, then from /opt/canvas-pilot-penn/deploy/penn run:

    docker compose -p canvas-pilot-penn -f compose.yaml -f compose.production.yaml build penn
    docker compose -p canvas-pilot-penn -f compose.yaml -f compose.production.yaml up -d --no-deps --no-build penn

Check all three tools with a real course using read-only calls and verify that
no viewing events were emitted. Record tool results and deployed commit here.
