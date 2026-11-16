"""Safety interlocks written in native pytest style: fixtures, parametrize, pytest.raises."""

import pytest


def drive(cockpit, speed, gear=None):
    cockpit.dispatch("speed_set", speed)
    if gear:
        cockpit.dispatch("gear_set", gear)


@pytest.mark.parametrize("gear", ["P", "R"])
def test_park_and_reverse_refused_while_moving(cockpit, gear):
    drive(cockpit, 40)
    with pytest.raises(ValueError, match="Stop the vehicle"):
        cockpit.dispatch("gear_set", gear)


def test_reverse_refused_with_driver_door_open(cockpit):
    cockpit.dispatch("door_set", True)
    with pytest.raises(ValueError, match="door is open"):
        cockpit.dispatch("gear_set", "R")


@pytest.mark.parametrize("speed, accepted", [(15, True), (16, False)])
def test_reverse_speed_limit_is_15_kmh(cockpit, speed, accepted):
    cockpit.dispatch("gear_set", "R")
    if accepted:
        assert cockpit.dispatch("speed_set", speed)["speed_kmh"] == speed
    else:
        with pytest.raises(ValueError, match="limited to 15"):
            cockpit.dispatch("speed_set", speed)


def test_driving_with_ignition_off_is_refused(cockpit):
    cockpit.dispatch("ignition_toggle")
    with pytest.raises(ValueError, match="Ignition must be on"):
        cockpit.dispatch("speed_set", 30)


def test_neutral_while_moving_is_allowed(cockpit):
    drive(cockpit, 50)
    assert cockpit.dispatch("gear_set", "N")["gear"] == "N"


def test_refused_command_over_http_returns_400(api):
    api("/api/events", {"event": "reset"})
    api("/api/events", {"event": "door_set", "value": True})
    from urllib.error import HTTPError

    with pytest.raises(HTTPError) as err:
        api("/api/events", {"event": "gear_set", "value": "R"})
    assert err.value.code == 400
