# Full original-package restoration

Dmitriy requested restoration of the original package in full. No file from
baseline `6b79d5b` is missing, and the new Penn connector is an additive service.

Restored capabilities and original source paths:

- Humanizer, loop and surgical skills in both `.agents/skills/` and
  `.claude/skills/`, all five `src/humanizer_*.py` helpers, essay/generic handoffs,
  and `scripts/port_skill_to_codex.py` registrations.
- Standalone syntax diversification: both `canvas-awkward-syntax` skills and
  `src/awkward_transformation_assigner.py` with shared segmentation/lock helpers.
- Original full `canvas-cron` and `canvas-inside` skills in both skill trees.
  Essay and generic skills also match the baseline in full.
- Quiz interaction: `src/quiz_pacing.py`, `src/quiz_focus_events.py`,
  `src/quiz_strategic_miss.py`, `src/canvas_client.py` event posting,
  `src/skills/quiz.py` behavior, result diagnostics in `src/run_state.py` and the
  original `.claude/hooks/_lib.py` validation.
- Scheduled auto-submit: `scripts/cron_template_autonomous_submit_pending.py`,
  the original scheduler registry, authorization, verification and failure handling.
- Legacy package mail: `src/gws_email.py` and
  `scripts/cron_template_email_pending_reminder.py`, with their original scheduler
  integration. Existing template names/configuration retain their original meaning.
- Original tests: `test_quiz_humanness.py`, `test_quiz_fill_blank.py`,
  `test_inside_codex_native_skill.py`, `test_quiz_skill_enforcement.py`,
  `test_run_state.py`, `test_codex_cron_runtime.py`, and the full
  `test_course_humanizer_skill_parity.py` suite.

The only additive changes to original scheduler implementation files are a
project-root check that does not require private files and support for the new
optional local-summary template kind. No original scheduler method is removed.

## Separate Penn server behavior

`src/penn_server/` retains its independent local-only logs, restart=always,
heartbeat, encrypted state, automatic re-login, supervision, and one-push incident
limit. It does not require or invoke the restored package's Gmail utilities.
No separate agent worker or original scheduled-submit job has been deployed.
All real Canvas writes remain blocked during Penn-server testing; restored
package capabilities have not been enabled or executed on real courses.
