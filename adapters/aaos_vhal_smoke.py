"""End-to-end assertion against a real Android Automotive VHAL property."""

from android_bridge import inject_speed, read_speed_mps


def main():
    try:
        inject_speed(72)
        actual = read_speed_mps()
        if abs(actual - 20.0) > 0.1:
            raise AssertionError(f"Expected 20.0 m/s (72 km/h), got {actual} m/s")
        print(f"PASS: AAOS VHAL read back {actual:.1f} m/s after injecting 72 km/h")
    finally:
        inject_speed(0)


if __name__ == "__main__":
    main()
