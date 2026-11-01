"""The Penn server must preserve every original package feature."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_original_quiz_and_scheduled_submission_features_are_present():
    for relative in (
        "src/quiz_pacing.py",
        "src/quiz_focus_events.py",
        "src/quiz_strategic_miss.py",
        "scripts/cron_template_autonomous_submit_pending.py",
        "scripts/cron_template_email_pending_reminder.py",
        "src/gws_email.py",
    ):
        assert (ROOT / relative).is_file()
    assert "def post_quiz_events(" in (ROOT / "src/canvas_client.py").read_text()


def test_humanizer_engines_skills_and_integrations_are_restored():
    for name in (
        "humanizer_apply_winners.py",
        "humanizer_score.py",
        "humanizer_select.py",
    ):
        assert (ROOT / "src" / name).is_file()
    for directory in (".agents/skills", ".claude/skills"):
        for skill in (
            "canvas-humanizer",
            "canvas-humanizer-loop",
            "canvas-humanizer-surgical",
        ):
            assert (ROOT / directory / skill / "SKILL.md").is_file()
        for skill in ("canvas-essay", "canvas-generic"):
            assert (
                "canvas-humanizer"
                in (ROOT / directory / skill / "SKILL.md").read_text()
            )
