"""Monkey / fuzz test: thousands of random commands, safety invariants checked after each.

Unit tests prove the rules one example at a time. This test hammers the state machine
with random sequences a scripted test would never think of, and asserts that no
sequence can ever reach an unsafe or inconsistent state. Each run is seeded, so any
failure prints the seed and the exact command history needed to reproduce it.
"""

import random
import unittest

from cockpit import CURVE_NAMES, REVERSE_MAX_KMH, Cockpit, curve_advisory

SEEDS = range(8)
STEPS_PER_SEED = 2500

# (event, value generator). Values include invalid ones on purpose (fuzzing).
EVENTS = [
    ("speed_set", lambda r: r.choice([0, 0, 5, 10, 15, 16, 30, 60, 100, 130, 240, 241, -5])),
    ("gear_set", lambda r: r.choice(["P", "R", "N", "D", "X"])),
    ("reverse_toggle", lambda r: None),
    ("door_toggle", lambda r: None),
    ("ignition_toggle", lambda r: None),
    ("bluetooth_toggle", lambda r: None),
    ("usb_toggle", lambda r: None),
    ("phone_disconnect", lambda r: None),
    ("phone_connect", lambda r: None),
    ("play", lambda r: None),
    ("pause", lambda r: None),
    ("projection_toggle", lambda r: None),
    ("fault_toggle", lambda r: None),
    ("curve_set", lambda r: r.choice([-3, -2, -1, 0, 1, 2, 3])),
    ("call_incoming", lambda r: None),
    ("call_answer", lambda r: None),
    ("call_end", lambda r: None),
    ("call_toggle", lambda r: None),
    ("volume_set", lambda r: r.choice([0, 50, 100, 101])),
]


def without_log(state):
    return {k: v for k, v in state.items() if k != "events"}


def invariant_violations(prev, state):
    """Every rule that must hold in any reachable state. Returns the broken ones."""
    broken = []
    if state["gear"] == "R" and state["speed_kmh"] > REVERSE_MAX_KMH:
        broken.append(f"reversing at {state['speed_kmh']} km/h (max {REVERSE_MAX_KMH})")
    if state["gear"] == "P" and state["speed_kmh"] > 0:
        broken.append("moving while in Park")
    if not state["ignition"] and (state["speed_kmh"] > 0 or state["gear"] != "P"):
        broken.append("moving / out of Park with ignition off")
    if state["media_playing"] and not state["phone_connected"]:
        broken.append("projected media playing without a phone")
    if state["phone_connected"] and not (state["bluetooth"] or state["usb_connected"]):
        broken.append("phone connected with no Bluetooth and no USB")
    if state["phone_connected"] != (state["projection"] != "Disconnected"):
        broken.append("projection status disagrees with phone connection")
    if state["call_state"] != "idle" and state["media_playing"]:
        broken.append("media playing during a phone call (audio focus)")
    if state["call_state"] != "idle" and not state["phone_connected"]:
        broken.append("call in progress without a connected phone")
    if state["rear_camera"] != (state["gear"] == "R"):
        broken.append("rear camera does not follow gear R")
    advisory = curve_advisory(state["road_curve"])
    if state["curve_warning"] != (advisory is not None and state["speed_kmh"] > advisory):
        broken.append("curve warning inconsistent with speed and curve")
    if state["road_curve"] not in CURVE_NAMES:
        broken.append(f"invalid road curve {state['road_curve']}")
    if prev["gear"] != "R" and state["gear"] == "R" and (state["door_open"] or prev["speed_kmh"] > 0):
        broken.append("entered reverse with a door open or while moving")
    if prev["gear"] in {"R", "D"} and state["gear"] in {"R", "D"} and prev["gear"] != state["gear"] and prev["speed_kmh"] > 0:
        broken.append("changed direction while moving")
    return broken


class MonkeyTest(unittest.TestCase):
    def test_random_commands_never_break_safety_invariants(self):
        total_accepted = total_refused = 0
        for seed in SEEDS:
            rng = random.Random(seed)
            cockpit = Cockpit()
            history = []
            state = cockpit.snapshot()
            for step in range(STEPS_PER_SEED):
                event, make_value = rng.choice(EVENTS)
                value = make_value(rng)
                history.append((event, value))
                prev = state
                try:
                    state = cockpit.dispatch(event, value)
                    total_accepted += 1
                except ValueError:
                    total_refused += 1
                    state = cockpit.snapshot()
                    # A refused command must not change anything (ADR 0004).
                    self.assertEqual(without_log(state), without_log(prev),
                                     f"refused {event}={value!r} changed state (seed {seed}, step {step})")
                broken = invariant_violations(prev, state)
                self.assertFalse(broken, f"seed {seed}, step {step}: {broken}\nlast commands: {history[-10:]}")
        # The fuzzing must exercise both paths, or it proves nothing.
        self.assertGreater(total_accepted, 1000)
        self.assertGreater(total_refused, 1000)


if __name__ == "__main__":
    unittest.main()
