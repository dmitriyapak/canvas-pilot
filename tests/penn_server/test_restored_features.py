"""Protect original workflows and the additive local-summary template."""

from pathlib import Path
from scripts.cron_base import CronInstance
from scripts.cron_registry import discover_templates

ROOT = Path(__file__).resolve().parents[2]


def test_legacy_workflows_keep_their_independent_implementation():
    for name, sections in {
        "canvas-generic": ("Stage 6", "Stage 8", "pipeline_design.md"),
        "canvas-essay": ("derived_vector", "figure-captions-cited", "load-samples"),
        "canvas-inside": ("§7a", "§10b", "learning_log.json"),
        "canvas-cron": ("change_schedule", "Error-recovery cheatsheet", "G1-G5"),
    }.items():
        text = (ROOT / ".claude/skills" / name / "SKILL.md").read_text()
        assert all(section in text for section in sections), name
        assert len(text.splitlines()) > 100, name


def test_original_templates_and_additive_local_summary_are_available():
    templates = discover_templates()
    assert "pending_reminder" in templates
    assert templates["pending_reminder"].spec.kind == "local"
    assert {
        "email_pending_reminder",
        "autonomous_submit_pending",
        "scan_pending",
    } <= templates.keys()
    old = dict(
        template="email_pending_reminder",
        course_id="123",
        schedule={},
        params={},
        recipient="unused@example.invalid",
    )
    assert (
        CronInstance.from_yaml_dict("legacy", old).template == "email_pending_reminder"
    )
