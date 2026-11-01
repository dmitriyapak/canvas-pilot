---
name: canvas-cron
description: Use when managing Canvas Pilot schedules: install, inspect, pause, change, delete, or safely test scheduled scans and runs. Scheduled automation is read-only; scheduled auto-submit is removed.
allowed-tools: Bash, PowerShell, Read, AskUserQuestion
---

# canvas-cron — Codex-native schedule control

This skill is the user-facing control plane for `scripts/canvas_cron.py` and
the discovered `scripts/cron_template_*.py` templates. Never ask the user to
edit `_private/cron_instances.yaml` or Task Scheduler directly.

Course names, IDs and instance names are private runtime values.
Do not copy them into this skill, tracked documentation, examples, or public
output.

## 0. Read-only preflight

Run from the repository root:

```powershell
python scripts/canvas_cron.py list-courses
python scripts/canvas_cron.py list-templates
python scripts/canvas_cron.py list
```

These commands inspect configuration and Task Scheduler state; they do not
create or change a schedule. If framework imports fail, stop and report the
exact missing file or module. If no courses exist, route to `canvas-setup`.

Memoize the discovered courses, template specs, and installed instances. Build
all user-facing choices from those live results.

## 1. Interpret the requested operation

Map the user's wording to one operation:

| Intent | CLI path |
|---|---|
| create/install a schedule | continue through this workflow |
| inspect/list/status | `status [name]` |
| pause/disable | `disable <name>` |
| resume/enable | `enable <name>` |
| remove/delete | `delete <name>` |
| change schedule | delete and recreate in v1 after confirming the change |
| test without effects | `fire <name> --dry-run` |

For a non-create operation, resolve the instance from the live `list` output.
If more than one matches, ask one concise question with those live choices.
Deleting an instance removes its registered task and archives local ledger/log
state; obtain confirmation because that is a destructive schedule change.

## 2. Choose scope and template from live data

For installation, ask for the course/scope and template using only preflight
results. Template kinds have different authority:

- `scan`: starts a fresh Codex session that runs `canvas-scan` and stops at the
  approval boundary. It has no Canvas mutation receipt.
- `local`: reads Canvas and records a due-item summary in the local log.

Scheduled assignment/quiz submission is removed. Never install a schedule that
mutates Canvas. The scan template may use `all` to build the daily snapshot.
For the Penn server, use its built-in read-only daily scan schedule;
clients invoke tools directly and no separate Codex worker is deployed.

## 3. Choose schedule and parameters

Collect:

1. cadence (`days_interval`, positive integer);
2. local Pacific time (`HH:MM`, 24-hour format);
3. start date (`YYYY-MM-DD`);
4. every parameter in the selected template's live `param_schema`;
5. a safe instance name matching `^[A-Za-z0-9_]+$`.

Show the complete proposed instance before creating it: template, private
course/scope label, schedule, parameters and whether it
can mutate Canvas.

## 4. Read-only schedule boundary

Do not issue mutation authority to schedules. Existing scheduled-submit instances
must remain disabled; their implementation has been removed.

## 5. Create and register, disabled first

Run:

```powershell
python scripts/canvas_cron.py create <instance> --template <template> --course <course_id> --days <N> --time <HH:MM> --start <YYYY-MM-DD> --param key=value
```

Success requires both:

- YAML and task XML rendered;
- Task Scheduler registration succeeded and the task is disabled.

If any gate fails, stop. Do not enable or force-fire the task.

## 6. Side-effect-free dry run

Run:

```powershell
python scripts/canvas_cron.py fire <instance> --dry-run
```

Dry run may read configuration, signed authority, local state, and Canvas
classification data. It must not start Codex, send email, upload/submit work,
answer a quiz, acquire a persistent lock, or call Task Scheduler mutation
commands. `--dry-run` and `--os-trigger` are mutually exclusive.

## 7. Optional OS-chain proof and enable

An OS-trigger test is a real scan/reminder trigger. It records results locally and must
never mutate Canvas. Run only within the approved schedule scope:

```powershell
python scripts/canvas_cron.py fire <instance> --os-trigger
```

Accept only Task Scheduler success/running results documented by the CLI. On
failure, the CLI re-disables the task and returns non-zero. If no immediate
test is authorized, leave the task disabled and ask before enabling it.

Enable only after all applicable gates pass:

```powershell
python scripts/canvas_cron.py enable <instance>
```

Report the returned task state and
next run time.

## Runtime guarantees to verify

- Fresh agent work launches through `src.codex_runner.run_codex`.
- `scan_pending` invokes only `canvas-scan` and stops before execution.
- Missing authority, Canvas auth/probe failure, Codex non-zero/timeout, and
  post-action verification failure all return non-zero.
- A successful process code does not claim assignment correctness; it only
  means the authorized action and readback verification completed.

## Hard rules

- Never put real course/account/recipient data in tracked files or examples.
- Never store durable receipts outside `_private/` or expose their content.
- Never let cron self-authorize or widen receipt actions/targets.
- Never give the scan template mutation authority.
- Never call Task Scheduler mutation commands during dry run.
- Never force-fire outside an explicitly authorized install/test operation.
- Never continue past a failed gate.
- Never submit coursework from a schedule.
