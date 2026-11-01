# Restoration audit for PR #1

The first build removed more than the requested humanizer, quiz tricks and
scheduled auto-submit. This revision restores the following non-excluded code,
workflows and regression coverage. The server still has all 71 connector tools.

## Exact restorations

- `src/awkward_transformation_assigner.py`: the independent role-aware syntax
  transformation solver, balancing, banned-phrase checks, structural validation
  and assignment-report generation.
- `.agents/skills/canvas-awkward-syntax/SKILL.md` and
  `.claude/skills/canvas-awkward-syntax/SKILL.md`: the complete standalone syntax
  diversification workflows, including locking, role inference, bounded rewrite,
  verification and local artifact output.
- `src/humanizer_segmentation.py` and `src/humanizer_segment_extract.py`: shared
  sentence/paragraph segmentation and protected-span extraction required by that
  standalone workflow. These utility filenames are historical; restoring them
  supports the restored humanizer and standalone syntax workflows.
- `scripts/port_skill_to_codex.py`: standalone syntax-skill conversion registration.
- `.claude/skills/canvas-essay/SKILL.md`: the independent legacy essay workflow,
  including persona derivation, sample anchoring, specification parsing, drafting,
  figures/citations, quality audits, calibration stages and export. The humanizer stage is now restored too.
- `.claude/skills/canvas-generic/SKILL.md`: the independent legacy investigation,
  pipeline design, prose/PDF/annotation/code/form/mixed modes, generation,
  independent verification, iteration, learning and export workflow. Its humanizer handoff is restored too.
- `.claude/skills/canvas-inside/SKILL.md`: the independent legacy quiz workflow,
  including classification, four-layer reading discovery, study notes, all answer
  shapes, independent arbitration, completion/readback, feedback-based retakes,
  learning audits, overlay handling and first-run calibration. Pacing, synthetic
  events, intentional misses and fake-interaction diagnostics stay removed.
- `.claude/skills/canvas-cron/SKILL.md`: the independent legacy scheduler builder,
  course/template discovery, cadence/parameter selection, install gates, disabled
  registration, dry runs, OS-chain proof, enable/disable, schedule changes and
  error recovery. Scheduled submissions stay removed; mail is removed by the
  latest instruction, with local summaries retained.
- `tests/test_course_humanizer_skill_parity.py`: previously deleted course and
  standalone-syntax coverage: native skill contracts, stable directories,
  canonical result states, submission boundaries, shared helper APIs, local
  prose/document artifacts, PDF annotation verification, zyBooks graded-column
  parsing, sentence locks and syntax-solver fixtures. All original humanizer skill/helper/scoring assertions are restored too.

## Newly requested mail removal

The server notifier/outbox, SMTP delivery, alert configuration and Gmail
provisioning are removed. The pre-existing `src/gws_email.py` transport is also
removed. The legacy email-reminder template becomes `pending_reminder`, retaining
its read-only due-item classification and deduplication as a local summary.
Existing private reminder instances migrate to that local template when read;
legacy recipient fields are accepted for compatibility but never used.

No existing Penn authentication state is cleared. Only the previous server's
retired alert records are discarded on startup. Failures are logged locally;
Docker restart=always, browser restoration, heartbeat, automatic re-login and
bounded maintenance supervision provide recovery. The one-push-per-incident
limit and real-Canvas-write testing block remain enforced.

## Humanizer restoration requested subsequently

Restored the complete `canvas-humanizer`, `canvas-humanizer-loop`, and
`canvas-humanizer-surgical` skills in both `.agents/skills/` and `.claude/skills/`,
plus `src/humanizer_apply_winners.py`, `src/humanizer_score.py`, and
`src/humanizer_select.py`. Restored the original essay/generic humanizer handoffs
in both skill trees, the converter registrations, and the complete original
`tests/test_course_humanizer_skill_parity.py` suite. These paths now match the
original repository. Quiz-interaction tricks, scheduled auto-submit and email
alerts remain excluded.
