from datetime import datetime, time, timezone
from types import SimpleNamespace

from app.services import dict_to_intervals, ensure_utc, is_within_intervals, schedule_to_dict


def test_ensure_utc_with_naive_datetime():
    dt = datetime(2026, 1, 10, 12, 0, 0)
    result = ensure_utc(dt)
    assert result.tzinfo == timezone.utc
    assert result.hour == 12


def test_ensure_utc_with_aware_datetime():
    dt = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    result = ensure_utc(dt)
    assert result.tzinfo == timezone.utc
    assert result == dt


def test_schedule_to_dict_and_dict_to_intervals_roundtrip():
    weekly_schedule = [
        SimpleNamespace(
            weekday=0,
            intervals=[
                SimpleNamespace(start=time(8, 30), end=time(12, 0)),
                SimpleNamespace(start=time(13, 0), end=time(18, 30)),
            ],
        )
    ]
    schedule_dict = schedule_to_dict(weekly_schedule)
    intervals = dict_to_intervals(schedule_dict, 0)
    assert intervals == [(time(8, 30), time(12, 0)), (time(13, 0), time(18, 30))]


def test_is_within_intervals_returns_true_for_valid_interval():
    starts_at = datetime(2026, 1, 12, 10, 0, 0, tzinfo=timezone.utc)
    ends_at = datetime(2026, 1, 12, 10, 30, 0, tzinfo=timezone.utc)
    intervals = [(time(8, 30), time(12, 0)), (time(13, 0), time(18, 30))]
    assert is_within_intervals(starts_at, ends_at, intervals) is True


def test_is_within_intervals_returns_false_for_outside_hours():
    starts_at = datetime(2026, 1, 12, 7, 30, 0, tzinfo=timezone.utc)
    ends_at = datetime(2026, 1, 12, 8, 0, 0, tzinfo=timezone.utc)
    intervals = [(time(8, 30), time(12, 0))]
    assert is_within_intervals(starts_at, ends_at, intervals) is False


def test_is_within_intervals_returns_false_for_cross_day_visit():
    starts_at = datetime(2026, 1, 12, 23, 50, 0, tzinfo=timezone.utc)
    ends_at = datetime(2026, 1, 13, 0, 10, 0, tzinfo=timezone.utc)
    intervals = [(time(8, 30), time(12, 0))]
    assert is_within_intervals(starts_at, ends_at, intervals) is False
