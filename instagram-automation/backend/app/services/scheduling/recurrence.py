"""Pure, timezone-aware recurrence calculations ("post every 4th day").

"Every 4th day" is ambiguous, so two modes are supported:

* ROLLING  - every N days counted from the start date, across month boundaries.
             start 2026-10-01, N=4 -> Oct 1, 5, 9, 13, 17, 21, 25, 29, Nov 2, ...
* MONTHLY  - day-of-month N, 2N, 3N ... in every month, restarting each month.
             N=4 -> 4th, 8th, 12th, 16th, 20th, 24th, 28th of every month.

Slot times are local wall-clock times in the schedule's timezone (default
Asia/Kolkata) and are returned as timezone-aware UTC datetimes.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.enums import ScheduleMode


@dataclass(frozen=True)
class RecurrenceRule:
    start_date: date
    interval_days: int
    post_time: time
    tz: str = "Asia/Kolkata"
    mode: str = ScheduleMode.ROLLING
    end_date: date | None = None

    def __post_init__(self) -> None:
        if self.interval_days < 1:
            raise ValueError("interval_days must be at least 1")
        if self.mode == ScheduleMode.MONTHLY and self.interval_days > 28:
            raise ValueError("monthly mode needs interval_days <= 28 so every month has at least one slot")
        validate_timezone(self.tz)


def validate_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def local_to_utc(day: date, at: time, tz: str) -> datetime:
    return datetime.combine(day, at, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def _dates(rule: RecurrenceRule, from_day: date) -> Iterator[date]:
    """Yield slot dates >= from_day (and >= start_date) in ascending order, forever or until end_date."""
    first = max(from_day, rule.start_date)
    if rule.mode == ScheduleMode.ROLLING:
        offset = (first - rule.start_date).days
        k = -(-offset // rule.interval_days)  # ceil division
        current = rule.start_date + timedelta(days=k * rule.interval_days)
        while rule.end_date is None or current <= rule.end_date:
            yield current
            current += timedelta(days=rule.interval_days)
        return
    # MONTHLY
    year, month = first.year, first.month
    while True:
        last_day = calendar.monthrange(year, month)[1]
        for dom in range(rule.interval_days, last_day + 1, rule.interval_days):
            d = date(year, month, dom)
            if d < first:
                continue
            if rule.end_date is not None and d > rule.end_date:
                return
            yield d
        month += 1
        if month > 12:
            month, year = 1, year + 1
        if rule.end_date is not None and date(year, month, 1) > rule.end_date:
            return


def occurrences_between(rule: RecurrenceRule, start: datetime, end: datetime) -> list[datetime]:
    """All slot datetimes (UTC) with start <= slot <= end."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")
    tz = ZoneInfo(rule.tz)
    # Widen by one day on each side to be safe around timezone offsets.
    from_day = start.astimezone(tz).date() - timedelta(days=1)
    result: list[datetime] = []
    for d in _dates(rule, from_day):
        slot = local_to_utc(d, rule.post_time, rule.tz)
        if slot > end:
            break
        if slot >= start:
            result.append(slot)
    return result


def next_occurrences(rule: RecurrenceRule, after: datetime, count: int = 5) -> list[datetime]:
    """The next `count` slots strictly after `after`."""
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")
    tz = ZoneInfo(rule.tz)
    from_day = after.astimezone(tz).date() - timedelta(days=1)
    result: list[datetime] = []
    for d in _dates(rule, from_day):
        slot = local_to_utc(d, rule.post_time, rule.tz)
        if slot > after:
            result.append(slot)
            if len(result) >= count:
                break
    return result


def occurrence_index(rule: RecurrenceRule, slot_utc: datetime) -> int:
    """0-based sequence number of a slot, used to rotate topics/categories deterministically."""
    local_day = slot_utc.astimezone(ZoneInfo(rule.tz)).date()
    if rule.mode == ScheduleMode.ROLLING:
        return (local_day - rule.start_date).days // rule.interval_days
    per_month = 28 // rule.interval_days  # stable count (every month has >= 28 days)
    months = (local_day.year - rule.start_date.year) * 12 + (local_day.month - rule.start_date.month)
    return months * per_month + (local_day.day // rule.interval_days) - 1
