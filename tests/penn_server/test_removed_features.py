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
    assert not list((root / "src").glob("humanizer_*.py"))
    for relative in (".agents/skills", ".claude/skills"):
        assert not list((root / relative).glob("canvas-humanizer*"))


def test_quiz_client_exposes_no_fabricated_events():
    root = Path(__file__).resolve().parents[2]
    assert "def post_quiz_events(" not in (root / "src/canvas_client.py").read_text()
