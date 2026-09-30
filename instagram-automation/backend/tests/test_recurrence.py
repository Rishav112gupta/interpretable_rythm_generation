from datetime import UTC, date, datetime, time

import pytest

from app.models import ScheduleMode
from app.services.scheduling.recurrence import RecurrenceRule, next_occurrences, occurrence_index, occurrences_between

IST = "Asia/Kolkata"


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_every_4_days_rolling_from_start_date():
    rule = RecurrenceRule(date(2026, 10, 1), 4, time(18, 0), IST)
    slots = next_occurrences(rule, utc(2026, 9, 1), 9)
    local_days = [s.astimezone(__import__("zoneinfo").ZoneInfo(IST)).date() for s in slots]
    assert local_days == [date(2026, 10, d) for d in (1, 5, 9, 13, 17, 21, 25, 29)] + [date(2026, 11, 2)]


def test_slot_time_is_timezone_aware_and_converted_to_utc():
    rule = RecurrenceRule(date(2026, 10, 1), 4, time(18, 0), IST)
    first = next_occurrences(rule, utc(2026, 9, 1), 1)[0]
    # 18:00 IST == 12:30 UTC
    assert first == utc(2026, 10, 1, 12, 30)
    assert first.tzinfo is not None


def test_next_occurrences_strictly_after_given_time():
    rule = RecurrenceRule(date(2026, 10, 1), 4, time(18, 0), IST)
    after = utc(2026, 10, 1, 12, 30)  # exactly the first slot
    assert next_occurrences(rule, after, 1)[0] == utc(2026, 10, 5, 12, 30)


def test_monthly_mode_restarts_each_month():
    rule = RecurrenceRule(date(2026, 1, 1), 4, time(9, 0), IST, mode=ScheduleMode.MONTHLY)
    slots = occurrences_between(rule, utc(2026, 2, 1), utc(2026, 3, 9))
    days = [(s.month, s.day) for s in slots]
    assert days == [(2, 4), (2, 8), (2, 12), (2, 16), (2, 20), (2, 24), (2, 28), (3, 4), (3, 8)]


def test_end_date_stops_recurrence():
    rule = RecurrenceRule(date(2026, 10, 1), 4, time(10, 0), IST, end_date=date(2026, 10, 10))
    assert len(next_occurrences(rule, utc(2026, 9, 1), 10)) == 3  # Oct 1, 5, 9


def test_dst_timezone_keeps_local_wall_clock_time():
    rule = RecurrenceRule(date(2026, 10, 30), 4, time(9, 0), "America/New_York")
    slots = next_occurrences(rule, utc(2026, 10, 1), 2)
    # Before DST ends (Nov 1): UTC-4; after: UTC-5.
    assert slots[0] == utc(2026, 10, 30, 13, 0)
    assert slots[1] == utc(2026, 11, 3, 14, 0)


def test_occurrence_index_rotates_topics():
    rule = RecurrenceRule(date(2026, 10, 1), 4, time(18, 0), IST)
    slots = next_occurrences(rule, utc(2026, 9, 1), 3)
    assert [occurrence_index(rule, s) for s in slots] == [0, 1, 2]


@pytest.mark.parametrize("kwargs", [{"interval_days": 0}, {"tz": "Mars/Base"}, {"interval_days": 30, "mode": ScheduleMode.MONTHLY}])
def test_invalid_rules_rejected(kwargs):
    base = {"start_date": date(2026, 10, 1), "interval_days": 4, "post_time": time(9, 0), "tz": IST}
    base.update(kwargs)
    with pytest.raises(ValueError):
        RecurrenceRule(**base)


def test_naive_datetimes_rejected():
    rule = RecurrenceRule(date(2026, 10, 1), 4, time(9, 0), IST)
    with pytest.raises(ValueError):
        next_occurrences(rule, datetime(2026, 10, 1), 1)
