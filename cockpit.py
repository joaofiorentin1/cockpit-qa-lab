"""Deterministic infotainment and vehicle-signal simulator.

No claim is made that these signals came from a BMW or real CAN hardware.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock, Thread
from time import sleep

# (target_speed_kmh, hold_seconds) - a short loop of straights and curves for the
# autopilot demo. Plateaus only: the HMI visualization is responsible for easing
# between them, so this stays a simple, readable script rather than a physics sim.
AUTOPILOT_PATTERN = [
    (60, 4),   # accelerate onto the straight
    (95, 5),   # cruise
    (45, 3),   # slow for a curve
    (90, 5),   # back up to cruise
    (30, 3),   # sharp curve
    (70, 4),   # cruise
    (0, 2),    # roll to a stop
]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


REVERSE_MAX_KMH = 15


class Cockpit:
    def __init__(self) -> None:
        self._lock = RLock()
        self._autopilot_generation = 0
        self._event_seq = 0  # never reset, so clients can tell new events from old ones
        self.reset()

    def reset(self) -> dict:
        with self._lock:
            self._autopilot_generation += 1  # stops any autopilot loop still running
            self._state = {
                "vehicle": "BMW M4 · simulated",
                "ignition": True,
                "speed_kmh": 0,
                "gear": "P",
                "door_open": False,
                "bluetooth": True,
                "phone_connected": True,
                "usb_connected": False,
                "projection": "Android Auto",
                "media_playing": False,
                "media_interrupted": False,
                "track": "Midnight Drive",
                "artist": "Cockpit QA Radio",
                "volume": 68,
                "fault": None,
                "autopilot": False,
                "call_state": "idle",  # idle | ringing | active
                "events": [],
            }
            self._log("SYSTEM", "Cockpit initialized")
            return self.snapshot()

    def _log(self, source: str, message: str) -> None:
        self._event_seq += 1
        self._state["events"].insert(0, {"id": self._event_seq, "time": _timestamp(), "source": source, "message": message})
        self._state["events"] = self._state["events"][:60]

    def snapshot(self) -> dict:
        with self._lock:
            snap = deepcopy(self._state)
            # Derived signal: the head unit shows the rear-view camera whenever R is engaged.
            snap["rear_camera"] = snap["gear"] == "R"
            return snap

    def dispatch(self, event: str, value=None) -> dict:
        with self._lock:
            s = self._state
            if event == "reset":
                return self.reset()
            if event == "play":
                if not s["phone_connected"]:
                    raise ValueError("Cannot play projected media without a connected phone")
                if s["call_state"] != "idle":
                    raise ValueError("Media is muted while a call is in progress")
                s["media_playing"] = True
                s["media_interrupted"] = False
                self._log("MEDIA", "Playback started")
            elif event == "pause":
                s["media_playing"] = False
                s["media_interrupted"] = False
                self._log("MEDIA", "Playback paused")
            elif event == "phone_disconnect":
                if s["phone_connected"]:
                    # A call already paused the media; keep that so it can still recover.
                    s["media_interrupted"] = s["media_playing"] or (s["call_state"] != "idle" and s["media_interrupted"])
                s["call_state"] = "idle"  # losing the phone drops the call
                s["phone_connected"] = False
                s["media_playing"] = False
                s["projection"] = "Disconnected"
                self._log("CONNECTIVITY", "Phone disconnected; projection unavailable")
            elif event == "phone_connect":
                if not s["bluetooth"] and not s["usb_connected"]:
                    raise ValueError("Enable Bluetooth or connect USB before pairing")
                s["phone_connected"] = True
                s["projection"] = "Android Auto"
                if s["media_interrupted"] and s["fault"] != "resume_failure":
                    s["media_playing"] = True
                    s["media_interrupted"] = False
                    self._log("MEDIA", "Playback recovered after reconnection")
                elif s["media_interrupted"]:
                    self._log("FAULT", "Injected fault: playback failed to recover")
                self._log("CONNECTIVITY", "Phone connected; projection available")
            elif event == "call_toggle":
                # One manual button: ring, then answer, then hang up.
                step = {"idle": "call_incoming", "ringing": "call_answer", "active": "call_end"}[s["call_state"]]
                return self.dispatch(step)
            elif event == "call_incoming":
                if not s["phone_connected"]:
                    raise ValueError("Connect the phone before receiving calls")
                if s["call_state"] != "idle":
                    raise ValueError("A call is already in progress")
                s["call_state"] = "ringing"
                if s["media_playing"]:
                    # The call takes audio focus: media pauses but must be able to recover.
                    s["media_playing"] = False
                    s["media_interrupted"] = True
                self._log("CALL", "Incoming call; media paused to give audio focus to the call")
            elif event == "call_answer":
                if s["call_state"] != "ringing":
                    raise ValueError("No incoming call to answer")
                s["call_state"] = "active"
                self._log("CALL", "Call answered")
            elif event == "call_end":
                if s["call_state"] == "idle":
                    raise ValueError("No call to end")
                s["call_state"] = "idle"
                self._log("CALL", "Call ended")
                if s["media_interrupted"] and s["fault"] != "resume_failure":
                    s["media_playing"] = True
                    s["media_interrupted"] = False
                    self._log("MEDIA", "Playback recovered after the call")
                elif s["media_interrupted"]:
                    self._log("FAULT", "Injected fault: playback failed to recover after the call")
            elif event == "bluetooth_toggle":
                s["bluetooth"] = not s["bluetooth"]
                self._log("BLUETOOTH", f"Bluetooth {'enabled' if s['bluetooth'] else 'disabled'}")
                if not s["bluetooth"] and not s["usb_connected"] and s["phone_connected"]:
                    self.dispatch("phone_disconnect")
            elif event == "usb_toggle":
                s["usb_connected"] = not s["usb_connected"]
                self._log("USB", f"USB {'connected' if s['usb_connected'] else 'disconnected'}")
                if not s["usb_connected"] and not s["bluetooth"] and s["phone_connected"]:
                    self.dispatch("phone_disconnect")
            elif event == "ignition_toggle":
                s["ignition"] = not s["ignition"]
                if not s["ignition"]:
                    s["speed_kmh"] = 0
                    s["gear"] = "P"
                    s["media_playing"] = False
                self._log("VEHICLE", f"Ignition {'on' if s['ignition'] else 'off'}")
            elif event == "door_toggle":
                s["door_open"] = not s["door_open"]
                self._log("CAN SIM", f"Driver door {'open' if s['door_open'] else 'closed'}")
            elif event == "door_set":
                if not isinstance(value, bool):
                    raise ValueError("Door signal must be boolean")
                s["door_open"] = value
                self._log("CAN", f"Driver door {'open' if value else 'closed'}")
            elif event == "reverse_toggle":
                if not s["ignition"]:
                    raise ValueError("Ignition must be on")
                target = "P" if s["gear"] == "R" else "R"
                if s["speed_kmh"] > 0:
                    raise ValueError(f"Stop the vehicle before selecting {target}")
                if target == "R" and s["door_open"]:
                    raise ValueError("Cannot engage reverse while a door is open")
                s["gear"] = target
                self._log("CAN SIM", f"Gear changed to {s['gear']}")
            elif event == "gear_set":
                if value not in {"P", "R", "N", "D"}:
                    raise ValueError("Gear signal must be P, R, N or D")
                if value != "P" and not s["ignition"]:
                    raise ValueError("Ignition must be on")
                if value in {"P", "R"} and s["speed_kmh"] > 0:
                    raise ValueError(f"Stop the vehicle before selecting {value}")
                if value == "R" and s["door_open"]:
                    raise ValueError("Cannot engage reverse while a door is open")
                if value == "D" and s["gear"] == "R" and s["speed_kmh"] > 0:
                    raise ValueError("Stop the vehicle before changing direction")
                s["gear"] = value
                self._log("CAN", f"Gear changed to {value}")
            elif event == "speed_set":
                speed = int(value)
                if not 0 <= speed <= 240:
                    raise ValueError("Speed must be between 0 and 240 km/h")
                if not s["ignition"] and speed:
                    raise ValueError("Ignition must be on")
                if s["gear"] == "R" and speed > REVERSE_MAX_KMH:
                    raise ValueError(f"Reverse speed is limited to {REVERSE_MAX_KMH} km/h")
                s["speed_kmh"] = speed
                # Neutral and Reverse are kept (coasting, or manoeuvring backwards);
                # otherwise speed drives D/P.
                if s["gear"] not in {"N", "R"}:
                    s["gear"] = "D" if speed else "P"
                self._log("CAN SIM", f"Vehicle speed signal: {speed} km/h")
            elif event == "fault_toggle":
                s["fault"] = None if s["fault"] else "resume_failure"
                self._log("FAULT", f"Recovery fault {'disabled' if not s['fault'] else 'enabled'}")
            elif event == "volume_set":
                volume = int(value)
                if not 0 <= volume <= 100:
                    raise ValueError("Volume must be between 0 and 100")
                s["volume"] = volume
                self._log("MEDIA", f"Volume set to {volume}")
            elif event == "projection_toggle":
                if not s["phone_connected"]:
                    raise ValueError("Connect the phone before switching projection mode")
                s["projection"] = "Apple CarPlay" if s["projection"] == "Android Auto" else "Android Auto"
                self._log("CONNECTIVITY", f"Projection switched to {s['projection']}")
            elif event == "autopilot_toggle":
                if not s["ignition"]:
                    raise ValueError("Ignition must be on")
                s["autopilot"] = not s["autopilot"]
                self._autopilot_generation += 1
                generation = self._autopilot_generation
                if s["autopilot"]:
                    Thread(target=self._autopilot_loop, args=(generation,), daemon=True).start()
                    self._log("AUTOPILOT", "Autopilot engaged: cycling accelerate/cruise/corner speeds")
                else:
                    self._log("AUTOPILOT", "Autopilot disengaged")
            else:
                raise ValueError(f"Unknown event: {event}")
            return self.snapshot()

    def _autopilot_loop(self, generation: int) -> None:
        """Background driving pattern. Exits as soon as a newer generation starts
        (autopilot toggled off, or the cockpit was reset) - never fights a QA scenario."""
        while True:
            for target_speed, hold_seconds in AUTOPILOT_PATTERN:
                with self._lock:
                    if self._autopilot_generation != generation:
                        return
                try:
                    self.dispatch("speed_set", target_speed)
                except ValueError:
                    return
                sleep(hold_seconds)
