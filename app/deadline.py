"""Deadline module (REQ-09, REQ-10, REQ-11) - Phase 2 Q7.2 Decision 1.

All business-day arithmetic lives here so every operation uses one rule set:

* Calendar dates are taken in US Eastern Time (America/New_York), not UTC (Phase 2 Q3.3).
* A business day is any Monday-Friday that is not a federal holiday on the shared list below.
* The determination date is day 0; the deadline is the 4th business day after it
  (Form 8-K General Instruction B.1; Phase 2 AC-09/AC-10 preamble). A determination on a
  weekend or holiday is still day 0, so counting starts at the next business day.

The holiday list is the U.S. federal holiday schedule (5 U.S.C. 6103, as published by OPM),
with Saturday holidays observed on the preceding Friday and Sunday holidays on the following
Monday. Inauguration Day is excluded (it applies only in the Washington, DC area). The pod has
not published a shared list file, so this list is frozen here and mirrored in
fixtures/holidays.json for other teams (docs/spec-issues.md ISSUE-17).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
BUSINESS_DAYS_TO_FILE = 4

FEDERAL_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(d)
    for d in (
        # 2023
        "2023-01-02", "2023-01-16", "2023-02-20", "2023-05-29", "2023-06-19", "2023-07-04",
        "2023-09-04", "2023-10-09", "2023-11-10", "2023-11-23", "2023-12-25",
        # 2024
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-05-27", "2024-06-19", "2024-07-04",
        "2024-09-02", "2024-10-14", "2024-11-11", "2024-11-28", "2024-12-25",
        # 2025
        "2025-01-01", "2025-01-20", "2025-02-17", "2025-05-26", "2025-06-19", "2025-07-04",
        "2025-09-01", "2025-10-13", "2025-11-11", "2025-11-27", "2025-12-25",
        # 2026
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19", "2026-07-03",
        "2026-09-07", "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25",
        # 2027
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18", "2027-07-05",
        "2027-09-06", "2027-10-11", "2027-11-11", "2027-11-25", "2027-12-24",
        # 2028 New Year's Day (Saturday Jan 1, 2028 is observed Friday Dec 31, 2027)
        "2027-12-31",
    )
)  # fmt: skip

# Determinations must fall inside the calendar with room for the deadline to land in it.
FIRST_SUPPORTED = date(2023, 1, 1)
LAST_SUPPORTED = date(2027, 12, 20)


class OutsideCalendar(ValueError):
    """The date is outside the years covered by the frozen holiday list."""


def eastern_date(moment: datetime) -> date:
    """Calendar date of an aware timestamp in US Eastern Time (DST handled by zoneinfo)."""
    if moment.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return moment.astimezone(EASTERN).date()


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in FEDERAL_HOLIDAYS


def _check_supported(day: date) -> None:
    if not FIRST_SUPPORTED <= day <= LAST_SUPPORTED:
        raise OutsideCalendar(
            f"{day.isoformat()} is outside the supported holiday calendar "
            f"({FIRST_SUPPORTED.isoformat()} to {LAST_SUPPORTED.isoformat()})"
        )


def add_business_days(start: date, n: int) -> date:
    """The n-th business day after `start` (start itself is day 0)."""
    day = start
    counted = 0
    while counted < n:
        day += timedelta(days=1)
        if is_business_day(day):
            counted += 1
    return day


def filing_deadline(determined_at: datetime) -> date:
    """REQ-09: 4th business day after the Eastern Time determination date."""
    day0 = eastern_date(determined_at)
    _check_supported(day0)
    return add_business_days(day0, BUSINESS_DAYS_TO_FILE)


def business_days_between(after: date, through: date) -> int:
    """Business days d with after < d <= through (0 if through <= after)."""
    count = 0
    day = after
    while day < through:
        day += timedelta(days=1)
        if is_business_day(day):
            count += 1
    return count


def days_late(deadline: date, day: date) -> int:
    """Business days late for an action on `day` after `deadline`; at least 1 once past it.

    An action on a weekend or holiday right after the deadline is still late, but no business
    day has elapsed; it counts as 1 because the earliest it could take effect is the next
    business day (docs/spec-issues.md ISSUE-19).
    """
    if day <= deadline:
        return 0
    return max(1, business_days_between(deadline, day))


def deadline_status(deadline: date | None, as_of: datetime) -> tuple[str, int]:
    """REQ-10: (status, businessDays) for a pending material decision at `as_of`.

    PENDING: business days left after the as_of date up to and including the deadline
             (0 on the deadline date itself).
    OVERDUE: business days late (see days_late).
    """
    if deadline is None:
        return "NOT_APPLICABLE", 0
    today = eastern_date(as_of)
    if today <= deadline:
        return "PENDING", business_days_between(today, deadline)
    return "OVERDUE", days_late(deadline, today)
