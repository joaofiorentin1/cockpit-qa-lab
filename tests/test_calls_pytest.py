"""Incoming-call behaviour and its QA scenario, in native pytest style."""

import time

import pytest

from cockpit import Cockpit
from qa import SCENARIOS, QARunner


def run_scenario(scenario, inject_fault=False, timeout=5):
    runner = QARunner(Cockpit(), step_delay=0)
    runner.start(scenario, inject_fault)
    deadline = time.time() + timeout
    while runner.report()["status"] == "running":
        assert time.time() < deadline, f"{scenario} did not finish"
        time.sleep(0.01)
    return runner.report()


def test_call_pauses_media_and_hangup_resumes_it(cockpit):
    cockpit.dispatch("play")
    ringing = cockpit.dispatch("call_incoming")
    assert (ringing["call_state"], ringing["media_playing"], ringing["media_interrupted"]) == ("ringing", False, True)
    assert cockpit.dispatch("call_answer")["call_state"] == "active"
    ended = cockpit.dispatch("call_end")
    assert (ended["call_state"], ended["media_playing"], ended["media_interrupted"]) == ("idle", True, False)


def test_call_without_media_does_not_start_playback(cockpit):
    cockpit.dispatch("call_incoming")
    assert cockpit.dispatch("call_end")["media_playing"] is False


def test_play_is_refused_during_a_call(cockpit):
    cockpit.dispatch("call_incoming")
    with pytest.raises(ValueError, match="muted"):
        cockpit.dispatch("play")


@pytest.mark.parametrize("event, message", [
    ("call_answer", "No incoming call"),
    ("call_end", "No call to end"),
])
def test_call_events_are_refused_without_a_call(cockpit, event, message):
    with pytest.raises(ValueError, match=message):
        cockpit.dispatch(event)


def test_incoming_call_needs_a_connected_phone(cockpit):
    cockpit.dispatch("phone_disconnect")
    with pytest.raises(ValueError, match="Connect the phone"):
        cockpit.dispatch("call_incoming")


def test_second_call_is_refused(cockpit):
    cockpit.dispatch("call_incoming")
    with pytest.raises(ValueError, match="already in progress"):
        cockpit.dispatch("call_incoming")


def test_losing_the_phone_drops_the_call_but_media_can_still_recover(cockpit):
    cockpit.dispatch("play")
    cockpit.dispatch("call_incoming")
    dropped = cockpit.dispatch("phone_disconnect")
    assert dropped["call_state"] == "idle"
    assert dropped["media_interrupted"] is True
    assert cockpit.dispatch("phone_connect")["media_playing"] is True


def test_call_toggle_cycles_ring_answer_hangup(cockpit):
    assert [cockpit.dispatch("call_toggle")["call_state"] for _ in range(3)] == ["ringing", "active", "idle"]


def test_injected_fault_blocks_recovery_after_the_call(cockpit):
    cockpit.dispatch("fault_toggle")
    cockpit.dispatch("play")
    cockpit.dispatch("call_incoming")
    state = cockpit.dispatch("call_end")
    assert state["media_playing"] is False
    assert state["media_interrupted"] is True
    assert "failed to recover after the call" in state["events"][0]["message"]


def test_incoming_call_scenario_passes_when_healthy():
    report = run_scenario("incoming_call")
    assert report["status"] == "passed"
    assert report["summary"] == "5/5 checks passed"


def test_incoming_call_scenario_detects_the_injected_defect():
    report = run_scenario("incoming_call", inject_fault=True)
    assert report["status"] == "failed"
    assert report["summary"] == "4/5 checks passed"
    assert report["steps"][-1]["label"] == "Hang up; media resumes by itself"
    assert report["steps"][-1]["status"] == "failed"


def test_scenario_is_in_the_catalog():
    assert SCENARIOS["incoming_call"] == "Incoming call & media recovery"
