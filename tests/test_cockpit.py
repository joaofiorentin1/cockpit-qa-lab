"""Unit tests for the deterministic cockpit state machine (cockpit.py)."""

import time
import unittest
from unittest import mock

import cockpit as cockpit_module
from cockpit import Cockpit


class CockpitTests(unittest.TestCase):
    def setUp(self):
        self.cockpit = Cockpit()

    # ---------- media & connectivity ----------

    def test_playback_recovers_after_reconnection(self):
        self.cockpit.dispatch("play")
        disconnected = self.cockpit.dispatch("phone_disconnect")
        self.assertFalse(disconnected["media_playing"])
        self.assertTrue(disconnected["media_interrupted"])
        recovered = self.cockpit.dispatch("phone_connect")
        self.assertTrue(recovered["media_playing"])
        self.assertEqual(recovered["projection"], "Android Auto")

    def test_injected_fault_is_observable(self):
        self.cockpit.dispatch("fault_toggle")
        self.cockpit.dispatch("play")
        self.cockpit.dispatch("phone_disconnect")
        state = self.cockpit.dispatch("phone_connect")
        self.assertFalse(state["media_playing"])
        self.assertTrue(state["media_interrupted"])
        self.assertIn("failed to recover", state["events"][1]["message"])

    def test_usb_retains_connection_when_bluetooth_is_disabled(self):
        self.cockpit.dispatch("usb_toggle")
        connected = self.cockpit.dispatch("bluetooth_toggle")
        self.assertTrue(connected["phone_connected"])
        disconnected = self.cockpit.dispatch("usb_toggle")
        self.assertFalse(disconnected["phone_connected"])

    def test_disabling_bluetooth_without_usb_drops_the_phone(self):
        state = self.cockpit.dispatch("bluetooth_toggle")
        self.assertFalse(state["bluetooth"])
        self.assertFalse(state["phone_connected"])
        self.assertEqual(state["projection"], "Disconnected")

    def test_pairing_requires_a_transport(self):
        self.cockpit.dispatch("bluetooth_toggle")  # phone drops, no USB either
        with self.assertRaisesRegex(ValueError, "Bluetooth or connect USB"):
            self.cockpit.dispatch("phone_connect")

    def test_play_requires_a_connected_phone(self):
        self.cockpit.dispatch("phone_disconnect")
        with self.assertRaisesRegex(ValueError, "connected phone"):
            self.cockpit.dispatch("play")

    def test_pause_clears_playback_and_interruption(self):
        self.cockpit.dispatch("play")
        state = self.cockpit.dispatch("pause")
        self.assertFalse(state["media_playing"])
        self.assertFalse(state["media_interrupted"])

    def test_disconnecting_while_paused_is_not_an_interruption(self):
        state = self.cockpit.dispatch("phone_disconnect")
        self.assertFalse(state["media_interrupted"])

    def test_projection_toggles_between_android_auto_and_carplay(self):
        self.assertEqual(self.cockpit.dispatch("projection_toggle")["projection"], "Apple CarPlay")
        self.assertEqual(self.cockpit.dispatch("projection_toggle")["projection"], "Android Auto")

    def test_projection_toggle_requires_a_phone(self):
        self.cockpit.dispatch("phone_disconnect")
        with self.assertRaises(ValueError):
            self.cockpit.dispatch("projection_toggle")

    def test_volume_bounds(self):
        self.assertEqual(self.cockpit.dispatch("volume_set", 0)["volume"], 0)
        self.assertEqual(self.cockpit.dispatch("volume_set", 100)["volume"], 100)
        for bad in (-1, 101):
            with self.assertRaises(ValueError):
                self.cockpit.dispatch("volume_set", bad)

    # ---------- vehicle signals ----------

    def test_reverse_is_refused_while_door_is_open(self):
        self.cockpit.dispatch("door_toggle")
        with self.assertRaises(ValueError):
            self.cockpit.dispatch("reverse_toggle")
        self.cockpit.dispatch("door_toggle")
        self.assertEqual(self.cockpit.dispatch("reverse_toggle")["gear"], "R")

    def test_vehicle_signals_and_invalid_speed(self):
        self.assertEqual(self.cockpit.dispatch("reverse_toggle")["gear"], "R")
        self.assertEqual(self.cockpit.dispatch("door_toggle")["door_open"], True)
        self.assertEqual(self.cockpit.dispatch("reverse_toggle")["gear"], "P")  # R keeps speed capped, so leave it first
        self.assertEqual(self.cockpit.dispatch("speed_set", 80)["speed_kmh"], 80)
        with self.assertRaises(ValueError):
            self.cockpit.dispatch("speed_set", 250)

    def test_speed_boundaries_and_gear_follow(self):
        self.assertEqual(self.cockpit.dispatch("speed_set", 240)["gear"], "D")
        self.assertEqual(self.cockpit.dispatch("speed_set", 0)["gear"], "P")
        with self.assertRaises(ValueError):
            self.cockpit.dispatch("speed_set", -1)

    def test_door_set_requires_boolean(self):
        self.assertTrue(self.cockpit.dispatch("door_set", True)["door_open"])
        for bad in ("true", 1, None):
            with self.assertRaises(ValueError):
                self.cockpit.dispatch("door_set", bad)

    def test_ignition_off_parks_and_stops_media(self):
        self.cockpit.dispatch("play")
        self.cockpit.dispatch("speed_set", 50)
        state = self.cockpit.dispatch("ignition_toggle")
        self.assertFalse(state["ignition"])
        self.assertEqual((state["speed_kmh"], state["gear"]), (0, "P"))
        self.assertFalse(state["media_playing"])

    def test_ignition_off_blocks_driving(self):
        self.cockpit.dispatch("ignition_toggle")
        for event, value in (("speed_set", 10), ("gear_set", "D"), ("reverse_toggle", None), ("autopilot_toggle", None)):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, "Ignition"):
                self.cockpit.dispatch(event, value)
        self.assertEqual(self.cockpit.dispatch("speed_set", 0)["speed_kmh"], 0)  # 0 is always allowed

    # ---------- gear selector (P/R/N/D) ----------

    def test_gear_selector_prnd(self):
        self.assertEqual(self.cockpit.dispatch("gear_set", "D")["gear"], "D")
        self.assertEqual(self.cockpit.dispatch("gear_set", "N")["gear"], "N")
        self.assertEqual(self.cockpit.dispatch("gear_set", "R")["gear"], "R")
        self.assertEqual(self.cockpit.dispatch("gear_set", "P")["gear"], "P")
        with self.assertRaises(ValueError):
            self.cockpit.dispatch("gear_set", "X")

    def test_curve_warning_follows_speed_and_curve(self):
        self.cockpit.dispatch("speed_set", 100)
        self.assertFalse(self.cockpit.dispatch("curve_set", 1)["curve_warning"])   # 100 <= 110
        state = self.cockpit.dispatch("curve_set", -2)
        self.assertEqual((state["curve_warning"], state["curve_advisory_kmh"]), (True, 60))
        self.assertIn("reduce to 60", state["events"][0]["message"])
        state = self.cockpit.dispatch("speed_set", 60)                               # at the limit is fine
        self.assertFalse(state["curve_warning"])
        self.assertIn("cleared", state["events"][0]["message"])
        self.assertIsNone(self.cockpit.dispatch("curve_set", 0)["curve_advisory_kmh"])

    def test_invalid_curve_is_refused(self):
        for bad in (3, -3, "left"):
            with self.subTest(curve=bad), self.assertRaises(ValueError):
                self.cockpit.dispatch("curve_set", bad)
        self.assertEqual(self.cockpit.snapshot()["road_curve"], 0)

    def test_autopilot_route_sets_curves(self):
        with mock.patch.object(cockpit_module, "AUTOPILOT_PATTERN", [(105, 0.05, 2)]):
            self.cockpit.dispatch("autopilot_toggle")
            deadline = time.time() + 2
            while not self.cockpit.snapshot()["curve_warning"] and time.time() < deadline:
                time.sleep(0.01)
            self.cockpit.dispatch("autopilot_toggle")
        self.assertEqual(self.cockpit.snapshot()["road_curve"], 2)

    def test_reverse_drives_backwards_up_to_the_limit(self):
        self.cockpit.dispatch("reverse_toggle")
        state = self.cockpit.dispatch("speed_set", 15)
        self.assertEqual((state["gear"], state["speed_kmh"], state["rear_camera"]), ("R", 15, True))
        with self.assertRaisesRegex(ValueError, "limited to 15"):
            self.cockpit.dispatch("speed_set", 16)
        self.assertEqual(self.cockpit.snapshot()["speed_kmh"], 15)
        self.assertEqual(self.cockpit.dispatch("speed_set", 0)["gear"], "R")  # stopping keeps R

    def test_no_direction_or_park_change_while_reversing(self):
        self.cockpit.dispatch("reverse_toggle")
        self.cockpit.dispatch("speed_set", 8)
        for event, value in (("gear_set", "D"), ("gear_set", "P"), ("reverse_toggle", None)):
            with self.subTest(event=event, value=value), self.assertRaisesRegex(ValueError, "Stop the vehicle"):
                self.cockpit.dispatch(event, value)
        self.assertEqual(self.cockpit.dispatch("gear_set", "N")["gear"], "N")  # coasting is allowed

    def test_rear_camera_follows_reverse_gear(self):
        self.assertFalse(self.cockpit.snapshot()["rear_camera"])
        self.assertTrue(self.cockpit.dispatch("gear_set", "R")["rear_camera"])
        self.assertFalse(self.cockpit.dispatch("gear_set", "P")["rear_camera"])

    def test_park_and_reverse_refused_while_moving(self):
        self.cockpit.dispatch("speed_set", 50)
        for gear in ("P", "R"):
            with self.assertRaises(ValueError):
                self.cockpit.dispatch("gear_set", gear)
        coasting = self.cockpit.dispatch("gear_set", "N")
        self.assertEqual(coasting["gear"], "N")
        self.assertEqual(self.cockpit.dispatch("speed_set", 30)["gear"], "N")

    def test_neutral_is_kept_when_stopping(self):
        self.cockpit.dispatch("gear_set", "N")
        self.assertEqual(self.cockpit.dispatch("speed_set", 0)["gear"], "N")

    def test_reverse_gear_set_refused_with_open_door(self):
        self.cockpit.dispatch("door_set", True)
        with self.assertRaisesRegex(ValueError, "door"):
            self.cockpit.dispatch("gear_set", "R")

    def test_refused_command_leaves_state_untouched(self):
        self.cockpit.dispatch("speed_set", 70)
        before = self.cockpit.snapshot()
        with self.assertRaises(ValueError):
            self.cockpit.dispatch("gear_set", "P")
        self.assertEqual(self.cockpit.snapshot(), before)

    # ---------- event log ----------

    def test_unknown_event_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown event"):
            self.cockpit.dispatch("warp_drive")

    def test_events_are_newest_first_with_increasing_ids(self):
        self.cockpit.dispatch("door_toggle")
        self.cockpit.dispatch("door_toggle")
        ids = [e["id"] for e in self.cockpit.snapshot()["events"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(len(set(ids)), len(ids))

    def test_event_ids_keep_increasing_across_reset(self):
        last = self.cockpit.dispatch("door_toggle")["events"][0]["id"]
        first_after = self.cockpit.reset()["events"][0]["id"]
        self.assertGreater(first_after, last)

    def test_event_log_is_capped(self):
        for _ in range(100):
            self.cockpit.dispatch("door_toggle")
        self.assertEqual(len(self.cockpit.snapshot()["events"]), 60)

    def test_snapshot_is_a_copy(self):
        snap = self.cockpit.snapshot()
        snap["speed_kmh"] = 999
        snap["events"].clear()
        self.assertEqual(self.cockpit.snapshot()["speed_kmh"], 0)
        self.assertTrue(self.cockpit.snapshot()["events"])

    def test_reset_restores_defaults(self):
        self.cockpit.dispatch("speed_set", 90)
        self.cockpit.dispatch("fault_toggle")
        state = self.cockpit.dispatch("reset")
        self.assertEqual((state["speed_kmh"], state["gear"], state["fault"]), (0, "P", None))
        self.assertEqual(len(state["events"]), 1)

    # ---------- autopilot ----------

    def test_autopilot_drives_and_stops_on_toggle(self):
        with mock.patch.object(cockpit_module, "AUTOPILOT_PATTERN", [(42, 0.02)]):
            self.assertTrue(self.cockpit.dispatch("autopilot_toggle")["autopilot"])
            deadline = time.time() + 2
            while self.cockpit.snapshot()["speed_kmh"] != 42 and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(self.cockpit.snapshot()["speed_kmh"], 42)
            self.assertFalse(self.cockpit.dispatch("autopilot_toggle")["autopilot"])

    def test_reset_stops_autopilot(self):
        with mock.patch.object(cockpit_module, "AUTOPILOT_PATTERN", [(30, 0.02)]):
            self.cockpit.dispatch("autopilot_toggle")
            self.cockpit.reset()
            time.sleep(0.1)
            self.assertFalse(self.cockpit.snapshot()["autopilot"])
            self.assertEqual(self.cockpit.snapshot()["speed_kmh"], 0)


if __name__ == "__main__":
    unittest.main()
