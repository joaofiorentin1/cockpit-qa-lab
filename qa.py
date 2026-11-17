"""Python scenario runner with assertions and evidence for the live cockpit."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock, Thread
from time import sleep

from cockpit import Cockpit


# Scenario id -> human-readable title. The web UI and the API both validate against this.
SCENARIOS = {
    "reconnect": "Phone reconnection & media recovery",
    "incoming_call": "Incoming call & media recovery",
    "door_safety": "Door / reverse interlock",
}



class QARunner:
    def __init__(self, cockpit: Cockpit, step_delay: float = 0.75) -> None:
        """step_delay paces the run so a viewer can watch the cockpit change; tests pass 0."""
        self.cockpit = cockpit
        self.step_delay = step_delay
        self._lock = Lock()
        self._report = {"status": "idle", "scenario": None, "steps": [], "summary": None}

    def report(self) -> dict:
        with self._lock:
            return deepcopy(self._report)

    def _update(self, **changes) -> None:
        with self._lock:
            self._report.update(changes)

    def start(self, scenario: str, inject_fault: bool = False) -> dict:
        if scenario not in SCENARIOS:
            raise ValueError("Unknown scenario")
        with self._lock:
            if self._report["status"] == "running":
                raise ValueError("A test is already running")
            self._report = {
                "status": "running",
                "scenario": scenario,
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "steps": [],
                "summary": None,
                "fault_injected": inject_fault,
            }
        Thread(target=self._run, args=(scenario, inject_fault), daemon=True).start()
        return self.report()

    def _step(self, label: str, event: str, expected: dict, value=None) -> bool:
        state = self.cockpit.dispatch(event, value)
        actual = {key: state[key] for key in expected}
        passed = actual == expected
        step = {
            "label": label,
            "event": event,
            "expected": expected,
            "actual": actual,
            "status": "passed" if passed else "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            self._report["steps"].append(step)
        sleep(self.step_delay)
        return passed

    def _step_rejected(self, label: str, event: str, value=None) -> bool:
        """Like _step, but the step passes when dispatch() raises - for asserting that an
        unsafe action (e.g. reverse with a door open) is correctly refused."""
        try:
            self.cockpit.dispatch(event, value)
            passed, actual = False, {"error": None}
        except ValueError as exc:
            passed, actual = True, {"error": str(exc)}
        step = {
            "label": label,
            "event": event,
            "expected": {"error": "<raised>"},
            "actual": actual,
            "status": "passed" if passed else "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            self._report["steps"].append(step)
        sleep(self.step_delay)
        return passed

    def _run(self, scenario: str, inject_fault: bool) -> None:
        try:
            self.cockpit.reset()
            sleep(self.step_delay * 0.6)
            if inject_fault:
                self.cockpit.dispatch("fault_toggle")
            if scenario == "reconnect":
                checks = [
                    self._step("Start projected media", "play", {"media_playing": True}),
                    self._step("Disconnect the phone", "phone_disconnect", {"media_playing": False, "projection": "Disconnected"}),
                    self._step("Reconnect and recover playback", "phone_connect", {"phone_connected": True, "media_playing": True}),
                ]
            elif scenario == "incoming_call":
                checks = [
                    self._step("Start projected media", "play", {"media_playing": True, "call_state": "idle"}),
                    self._step("Incoming call pauses the media", "call_incoming", {"call_state": "ringing", "media_playing": False, "media_interrupted": True}),
                    self._step_rejected("Playback is refused during the call", "play"),
                    self._step("Answer the call", "call_answer", {"call_state": "active", "media_playing": False}),
                    self._step("Hang up; media resumes by itself", "call_end", {"call_state": "idle", "media_playing": True}),
                ]
            elif scenario == "door_safety":
                checks = [
                    self._step("Open the driver door", "door_toggle", {"door_open": True}),
                    self._step_rejected("Reverse is refused while the door is open", "reverse_toggle"),
                    self._step("Close the door", "door_toggle", {"door_open": False}),
                    self._step("Reverse now accepted", "reverse_toggle", {"gear": "R", "door_open": False}),
                ]
            passed = sum(checks)
            self._update(
                status="passed" if all(checks) else "failed",
                finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                summary=f"{passed}/{len(checks)} checks passed",
                final_state=self.cockpit.snapshot(),
            )
        except Exception as exc:
            self._update(status="error", summary=str(exc), final_state=self.cockpit.snapshot())
