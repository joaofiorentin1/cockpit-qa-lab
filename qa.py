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
    "usb_fallback": "USB connectivity fallback",
    "reverse_camera": "Reverse gear & rear camera",
    "door_safety": "Door / reverse interlock",
    "gear_interlock": "Gear selector interlock",
    "curve_warning": "Curve speed warning",
    "bt_endurance": "Bluetooth reconnection endurance",
}

# Reconnection cycles in the endurance scenario (industry practice: repeated reconnects,
# measuring the recovery rate; this bench requires 100%).
ENDURANCE_CYCLES = 50


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

    def _endurance(self, label: str, cycles: int) -> bool:
        """Disconnect/reconnect the phone `cycles` times while media plays; every cycle
        must bring playback back. Records one step with the recovery count as evidence."""
        recovered = 0
        for _ in range(cycles):
            self.cockpit.dispatch("phone_disconnect")
            state = self.cockpit.dispatch("phone_connect")
            if state["media_playing"]:
                recovered += 1
            else:  # a real head unit user would press play again; keep the next cycle meaningful
                self.cockpit.dispatch("play")
            sleep(self.step_delay * 0.04)
        expected, actual = {"recovered": cycles}, {"recovered": recovered}
        step = {
            "label": label,
            "event": "phone_disconnect/phone_connect",
            "expected": expected,
            "actual": actual,
            "status": "passed" if actual == expected else "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            self._report["steps"].append(step)
        sleep(self.step_delay)
        return actual == expected

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
            elif scenario == "usb_fallback":
                checks = [
                    self._step("Connect USB", "usb_toggle", {"usb_connected": True}),
                    self._step("Turn off Bluetooth; USB keeps projection", "bluetooth_toggle", {"phone_connected": True, "projection": "Android Auto"}),
                    self._step("Remove USB; projection disconnects", "usb_toggle", {"phone_connected": False, "projection": "Disconnected"}),
                ]
            elif scenario == "reverse_camera":
                checks = [
                    self._step("Select reverse; rear camera turns on", "reverse_toggle", {"gear": "R", "rear_camera": True}),
                    self._step("Reverse at 8 km/h", "speed_set", {"gear": "R", "speed_kmh": 8, "rear_camera": True}, 8),
                    self._step_rejected("Reverse above 15 km/h is refused", "speed_set", 25),
                    self._step("Stop", "speed_set", {"gear": "R", "speed_kmh": 0}, 0),
                    self._step("Return to park; camera turns off", "reverse_toggle", {"gear": "P", "rear_camera": False}),
                ]
            elif scenario == "gear_interlock":
                checks = [
                    self._step("Engage Drive", "gear_set", {"gear": "D"}, "D"),
                    self._step("Accelerate to 60 km/h", "speed_set", {"speed_kmh": 60, "gear": "D"}, 60),
                    self._step_rejected("Park is refused while moving", "gear_set", "P"),
                    self._step_rejected("Reverse is refused while moving", "gear_set", "R"),
                    self._step("Shift to Neutral while coasting", "gear_set", {"gear": "N", "speed_kmh": 60}, "N"),
                    self._step("Speed change keeps Neutral", "speed_set", {"gear": "N", "speed_kmh": 20}, 20),
                    self._step("Roll to a stop in Neutral", "speed_set", {"gear": "N", "speed_kmh": 0}, 0),
                    self._step("Park once stopped", "gear_set", {"gear": "P"}, "P"),
                ]
            elif scenario == "door_safety":
                checks = [
                    self._step("Open the driver door", "door_toggle", {"door_open": True}),
                    self._step_rejected("Reverse is refused while the door is open", "reverse_toggle"),
                    self._step("Close the door", "door_toggle", {"door_open": False}),
                    self._step("Reverse now accepted", "reverse_toggle", {"gear": "R", "door_open": False}),
                ]
            elif scenario == "curve_warning":
                checks = [
                    self._step("Drive at 100 km/h on a straight", "speed_set", {"speed_kmh": 100, "curve_warning": False}, 100),
                    self._step("Gentle right curve: 100 is within 110", "curve_set", {"road_curve": 1, "curve_warning": False}, 1),
                    self._step("Sharp right curve: warning on", "curve_set", {"road_curve": 2, "curve_advisory_kmh": 60, "curve_warning": True}, 2),
                    self._step("Slow to 55 km/h: warning clears", "speed_set", {"speed_kmh": 55, "curve_warning": False}, 55),
                    self._step("Back to the straight", "curve_set", {"road_curve": 0, "curve_advisory_kmh": None}, 0),
                ]
            elif scenario == "bt_endurance":
                checks = [
                    self._step("Start projected media", "play", {"media_playing": True}),
                    self._endurance(f"{ENDURANCE_CYCLES} reconnect cycles: media resumes every time", ENDURANCE_CYCLES),
                    self._step("Phone and media still up after the run", "pause", {"phone_connected": True, "projection": "Android Auto"}),
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
