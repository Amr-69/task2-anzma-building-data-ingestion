import pytest

from assistant.services import AssistantError, resolve_scenario, resolve_time_range


def test_default_window_matches_day3_end_exclusive():
    w = resolve_time_range("baseline", 24)
    assert w["end_exclusive"] == "2026-11-02T00:55:01Z"
    assert w["start"] == "2026-11-01T00:55:01Z"
    assert w["hours"] == 24
    assert w["anchored_to"] == "dataset end"
    assert w["coverage"] == "complete"


def test_shorter_windows_share_the_same_end():
    w6 = resolve_time_range("baseline", 6)
    assert w6["end_exclusive"] == "2026-11-02T00:55:01Z"
    assert w6["start"] == "2026-11-01T18:55:01Z"
    assert resolve_time_range("baseline", 1)["start"] == "2026-11-01T23:55:01Z"


def test_scenario_database_is_resolved():
    w = resolve_time_range("S1", 24)
    assert w["scenario"] == "S1"
    assert w["end_exclusive"].endswith("Z")


@pytest.mark.parametrize("bad", [0, 5, 48, -1, "6", 6.0, None, True])
def test_invalid_hours_rejected(bad):
    with pytest.raises(AssistantError) as err:
        resolve_time_range("baseline", bad)
    assert err.value.status_code == 422
    assert err.value.code == "invalid_time_range"


def test_unknown_scenario_rejected():
    with pytest.raises(AssistantError) as err:
        resolve_scenario("S9")
    assert err.value.status_code == 400