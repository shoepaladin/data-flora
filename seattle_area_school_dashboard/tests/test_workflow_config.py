"""Guardrail: the deploy workflow must only run on push or manual dispatch.

A cron schedule was accidentally left enabled once already (it silently fires
weekly regardless of what any feature branch does, since GitHub Actions only
honors the schedule trigger defined in the default branch's workflow file).
This test fails loudly if a schedule/cron trigger is reintroduced.
"""

from pathlib import Path
import unittest

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "build-and-deploy.yml"
)


class WorkflowScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.content = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"expected workflow file at {WORKFLOW_PATH}")

    def test_no_cron_schedule_trigger(self) -> None:
        self.assertNotIn("cron", self.content)
        self.assertNotIn("schedule:", self.content)

    def test_push_and_manual_dispatch_still_enabled(self) -> None:
        self.assertIn('branches: ["main"]', self.content)
        self.assertIn("workflow_dispatch:", self.content)

    def test_data_refresh_steps_are_manual_only(self) -> None:
        self.assertNotIn("event_name == 'schedule'", self.content)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.content)


if __name__ == "__main__":
    unittest.main()
