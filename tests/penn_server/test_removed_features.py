"""Requested removals must not silently return in future merges."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_removed_helpers_and_scheduled_submit_are_absent():
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "src/quiz_pacing.py",
        "src/quiz_focus_events.py",
        "src/quiz_strategic_miss.py",
        "scripts/cron_template_autonomous_submit_pending.py",
    ):
        assert not (root / relative).exists()


def test_quiz_client_exposes_no_fabricated_events():
    root = Path(__file__).resolve().parents[2]
    assert "def post_quiz_events(" not in (root / "src/canvas_client.py").read_text()


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
