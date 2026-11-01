"""Unit tests for app/deadline.py (Phase 2 Q7.4: validate the calculator before the API).

Oracles are independent of the module under test:
  * the holiday list is recomputed here from the statutory rules (5 U.S.C. 6103 and the
    Saturday->Friday / Sunday->Monday observance rule), not imported;
  * deadlines are counted by a deliberately naive day-by-day loop over that list;
  * the AC-09/AC-10 dates are typed in from the pod's acceptance criteria.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import deadline

ET = ZoneInfo("America/New_York")


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def statutory_holidays(year: int) -> set[date]:
    mon, thu = 0, 3
    return {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, mon, 3),  # Birthday of Martin Luther King, Jr.
        _nth_weekday(year, 2, mon, 3),  # Washington's Birthday
        _last_weekday(year, 5, mon),  # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, mon, 1),  # Labor Day
        _nth_weekday(year, 10, mon, 2),  # Columbus Day
        _observed(date(year, 11, 11)),
        _nth_weekday(year, 11, thu, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),
    }


EXPECTED_HOLIDAYS = set().union(*(statutory_holidays(y) for y in range(2023, 2028))) | {
    _observed(date(2028, 1, 1))  # Sat Jan 1, 2028 -> Fri Dec 31, 2027
}


def test_frozen_holiday_list_matches_statute() -> None:
    assert set(deadline.FEDERAL_HOLIDAYS) == EXPECTED_HOLIDAYS


def _naive_deadline(day0: date) -> date:
    d, counted = day0, 0
    while counted < 4:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in EXPECTED_HOLIDAYS:
            counted += 1
    return d


@pytest.mark.parametrize(
    "determined,expected",
    [
        ("2025-09-29T10:00:00-04:00", date(2025, 10, 3)),  # AC-09
        ("2025-10-10T10:00:00-04:00", date(2025, 10, 17)),  # AC-10 Columbus Day
        ("2025-11-25T10:00:00-05:00", date(2025, 12, 2)),  # AC-10 Thanksgiving
        ("2025-12-30T10:00:00-05:00", date(2026, 1, 6)),  # AC-10 New Year's Day
        ("2025-10-04T10:00:00-04:00", date(2025, 10, 9)),  # AC-10 Saturday
        ("2026-09-22T15:00:00-04:00", date(2026, 9, 28)),  # section 5.2 example
    ],
)
def test_acceptance_deadlines(determined: str, expected: date) -> None:
    assert deadline.filing_deadline(datetime.fromisoformat(determined)) == expected


def test_every_determination_day_matches_naive_count() -> None:
    """Exhaustive cross-check over every calendar day 2023-01-01 .. 2027-12-20 (Q9.1 risk 1)."""
    day = deadline.FIRST_SUPPORTED
    while day <= deadline.LAST_SUPPORTED:
        noon = datetime(day.year, day.month, day.day, 12, tzinfo=ET)
        got = deadline.filing_deadline(noon)
        assert got == _naive_deadline(day), day
        assert got.weekday() < 5 and got not in EXPECTED_HOLIDAYS
        day += timedelta(days=1)


@pytest.mark.parametrize(
    "utc,et_date",
    [
        (datetime(2025, 9, 30, 3, 59, tzinfo=UTC), date(2025, 9, 29)),  # EDT, UTC-4
        (datetime(2025, 9, 30, 4, 0, tzinfo=UTC), date(2025, 9, 30)),
        (datetime(2025, 11, 4, 4, 59, tzinfo=UTC), date(2025, 11, 3)),  # EST, UTC-5
        (datetime(2025, 11, 4, 5, 0, tzinfo=UTC), date(2025, 11, 4)),
        (datetime(2025, 3, 9, 6, 59, tzinfo=UTC), date(2025, 3, 9)),  # DST starts 2025-03-09 02:00 ET
        (datetime(2025, 11, 2, 5, 30, tzinfo=UTC), date(2025, 11, 2)),  # repeated 01:30 hour on DST end
    ],
)
def test_eastern_date_across_dst(utc: datetime, et_date: date) -> None:
    assert deadline.eastern_date(utc) == et_date


def test_outside_calendar_rejected() -> None:
    with pytest.raises(deadline.OutsideCalendar):
        deadline.filing_deadline(datetime(2022, 12, 30, 12, tzinfo=ET))
    with pytest.raises(deadline.OutsideCalendar):
        deadline.filing_deadline(datetime(2027, 12, 21, 12, tzinfo=ET))


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValueError):
        deadline.eastern_date(datetime(2025, 9, 29, 12))


@pytest.mark.parametrize(
    "as_of,expected",
    [
        (datetime(2025, 9, 29, 12, tzinfo=ET), ("PENDING", 4)),
        (datetime(2025, 10, 3, 23, 59, tzinfo=ET), ("PENDING", 0)),
        (datetime(2025, 10, 4, 0, 30, tzinfo=ET), ("OVERDUE", 1)),  # Saturday: ISSUE-19 minimum of 1
        (datetime(2025, 10, 6, 12, tzinfo=ET), ("OVERDUE", 1)),  # AC-11
        (datetime(2025, 10, 14, 12, tzinfo=ET), ("OVERDUE", 6)),  # skips Columbus Day
    ],
)
def test_deadline_status(as_of: datetime, expected: tuple[str, int]) -> None:
    assert deadline.deadline_status(date(2025, 10, 3), as_of) == expected


def test_not_applicable_without_deadline() -> None:
    assert deadline.deadline_status(None, datetime(2025, 10, 6, tzinfo=UTC)) == ("NOT_APPLICABLE", 0)


@pytest.mark.parametrize(
    "filed,late",
    [(date(2025, 10, 3), 0), (date(2025, 10, 2), 0), (date(2025, 10, 6), 1), (date(2025, 10, 5), 1)],
)
def test_days_late(filed: date, late: int) -> None:
    assert deadline.days_late(date(2025, 10, 3), filed) == late
