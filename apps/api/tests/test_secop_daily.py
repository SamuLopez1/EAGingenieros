from datetime import UTC, datetime, timedelta

import pytest

from app.secop.daily import DailyWindow, plan_daily_window


@pytest.mark.parametrize(
    ("as_of", "expected_end"),
    [
        ("2026-11-05T10:59:59.999999Z", "2026-11-04T11:00:00Z"),
        ("2026-11-05T11:00:00Z", "2026-11-05T11:00:00Z"),
        ("2026-11-05T06:00:01-05:00", "2026-11-05T11:00:00Z"),
        ("2026-12-01T01:00:00Z", "2026-11-30T11:00:00Z"),
    ],
)
def test_window_uses_the_last_bogota_cutover(as_of: str, expected_end: str) -> None:
    plan = plan_daily_window(datetime.fromisoformat(as_of))
    end = datetime.fromisoformat(expected_end)
    assert plan.end.astimezone(UTC) == end
    assert plan.start.astimezone(UTC) == end - timedelta(days=7)
    assert plan.next_run.astimezone(UTC) == end + timedelta(days=1)
    assert plan.end.isoformat().endswith("T06:00:00-05:00")


def test_overlapping_runs_and_stable_retry_window() -> None:
    first = plan_daily_window(datetime.fromisoformat("2026-11-05T11:00:00Z"))
    retry = plan_daily_window(datetime.fromisoformat("2026-11-05T23:59:00Z"))
    following = plan_daily_window(first.next_run)
    assert retry == first
    assert first.end - following.start == timedelta(days=6)


def test_rejects_an_unzoned_clock() -> None:
    with pytest.raises(ValueError, match="zona u offset"):
        plan_daily_window(datetime(2026, 11, 5, 6))


def test_rejects_unzoned_or_inverted_window_bounds() -> None:
    plan = plan_daily_window(datetime(2026, 11, 5, 11, tzinfo=UTC))
    with pytest.raises(ValueError, match="zona u offset"):
        DailyWindow(plan.start.replace(tzinfo=None), plan.end, plan.next_run)
    with pytest.raises(ValueError, match="anterior"):
        DailyWindow(plan.end, plan.start, plan.next_run)
