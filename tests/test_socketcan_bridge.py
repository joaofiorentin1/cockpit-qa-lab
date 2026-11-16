import unittest

from adapters.socketcan_bridge import FRAME, decode


class SocketCANBridgeTests(unittest.TestCase):
    def frame(self, can_id, data):
        return FRAME.pack(can_id, len(data), data.ljust(8, b"\0"))

    def test_speed_gear_and_door_frames(self):
        self.assertEqual(decode(self.frame(0x100, (850).to_bytes(2, "little"))), ("speed_set", 85))
        self.assertEqual(decode(self.frame(0x101, b"\x01")), ("gear_set", "R"))
        self.assertEqual(decode(self.frame(0x102, b"\x00")), ("door_set", False))

    def test_unknown_frame_is_ignored(self):
        self.assertIsNone(decode(self.frame(0x7FF, b"\x00")))


if __name__ == "__main__":
    unittest.main()
