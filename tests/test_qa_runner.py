"""Tests for the Python scenario runner (qa.py): every scenario, faults and concurrency."""

import time
import unittest

from cockpit import Cockpit
from qa import SCENARIOS, QARunner


def run_to_completion(runner: QARunner, scenario: str, inject_fault: bool = False, timeout: float = 5) -> dict:
    runner.start(scenario, inject_fault)
    deadline = time.time() + timeout
    while runner.report()["status"] == "running":
        if time.time() > deadline:
            raise AssertionError(f"{scenario} did not finish within {timeout}s")
        time.sleep(0.005)
    return runner.report()


class QARunnerTests(unittest.TestCase):
    def setUp(self):
        self.cockpit = Cockpit()
        self.runner = QARunner(self.cockpit, step_delay=0)

    def test_initial_report_is_idle(self):
        report = self.runner.report()
        self.assertEqual(report["status"], "idle")
        self.assertEqual(report["steps"], [])

    def test_every_scenario_passes_on_a_healthy_cockpit(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                report = run_to_completion(self.runner, scenario)
                self.assertEqual(report["status"], "passed", report)
                self.assertTrue(report["steps"])
                self.assertTrue(all(step["status"] == "passed" for step in report["steps"]))
                total = len(report["steps"])
                self.assertEqual(report["summary"], f"{total}/{total} checks passed")
                self.assertIn("finished_at", report)
                self.assertIn("final_state", report)

    def test_injected_fault_is_detected_by_reconnect(self):
        report = run_to_completion(self.runner, "reconnect", inject_fault=True)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["fault_injected"])
        self.assertEqual(report["summary"], "2/3 checks passed")
        failed = [step for step in report["steps"] if step["status"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["event"], "phone_connect")
        self.assertEqual(failed[0]["expected"]["media_playing"], True)
        self.assertEqual(failed[0]["actual"]["media_playing"], False)

    def test_each_run_starts_from_a_clean_cockpit(self):
        self.cockpit.dispatch("speed_set", 120)
        self.cockpit.dispatch("door_set", True)
        report = run_to_completion(self.runner, "reverse_camera")
        self.assertEqual(report["status"], "passed")

    def test_steps_record_expected_and_actual_evidence(self):
        report = run_to_completion(self.runner, "usb_fallback")
        for step in report["steps"]:
            self.assertEqual(set(step), {"label", "event", "expected", "actual", "status", "timestamp"})
            self.assertEqual(step["expected"], step["actual"])

    def test_rejection_steps_capture_the_refusal_message(self):
        report = run_to_completion(self.runner, "door_safety")
        refused = next(step for step in report["steps"] if step["expected"] == {"error": "<raised>"})
        self.assertIn("door", refused["actual"]["error"])

    def test_gear_interlock_scenario_covers_prnd_rules(self):
        report = run_to_completion(self.runner, "gear_interlock")
        self.assertEqual(report["status"], "passed", report)
        refused = [step["label"] for step in report["steps"] if step["expected"] == {"error": "<raised>"}]
        self.assertEqual(refused, ["Park is refused while moving", "Reverse is refused while moving"])
        self.assertEqual(report["final_state"]["gear"], "P")

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown scenario"):
            self.runner.start("self_destruct")
        self.assertEqual(self.runner.report()["status"], "idle")

    def test_only_one_run_at_a_time(self):
        slow = QARunner(Cockpit(), step_delay=0.2)
        slow.start("reconnect")
        try:
            with self.assertRaisesRegex(ValueError, "already running"):
                slow.start("usb_fallback")
        finally:
            while slow.report()["status"] == "running":
                time.sleep(0.02)

    def test_report_is_a_copy(self):
        report = run_to_completion(self.runner, "reverse_camera")
        report["steps"].clear()
        self.assertTrue(self.runner.report()["steps"])

    def test_scenario_catalog_has_titles(self):
        self.assertGreaterEqual(len(SCENARIOS), 5)
        for key, title in SCENARIOS.items():
            self.assertRegex(key, r"^[a-z_]+$")
            self.assertTrue(title.strip())


if __name__ == "__main__":
    unittest.main()
