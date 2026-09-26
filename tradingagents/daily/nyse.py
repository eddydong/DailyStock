"""NYSE cash-session calendar.

The scheduler fires at 09:00 America/New_York, which is 30 minutes before the
9:30 open. Cloud Scheduler can only say Monday–Friday, so holidays are
skipped here. An early close (the exchange is open, then shuts early) is
still a trading day.
"""

from __future__ import annotations

from datetime import date, timedelta


def is_nyse_session(day: date) -> bool:
    """Whether the NYSE cash session is open on ``day``."""
    if day.weekday() >= 5:
        return False
    return day not in nyse_holidays(day.year)


def nyse_holidays(year: int) -> set[date]:
    """Full-day NYSE closures for ``year``, including weekend observances."""
    closed = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),   # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
        _easter(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),     # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),
    }
    # A Saturday New Year or a Saturday Christmas is observed on the Friday,
    # which can fall in the previous year. Keep only dates in ``year``.
    return {day for day in closed if day.year == year}


def _observed(day: date) -> date:
    """Saturday holidays move to Friday. Sunday holidays move to Monday."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth weekday in a month. Monday is 0. ``n`` is 1-based."""
    first = date(year, month, 1)
    shift = (weekday - first.weekday()) % 7
    return first + timedelta(days=shift + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """The last weekday in a month. Monday is 0."""
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def _easter(year: int) -> date:
    """Easter Sunday, Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)
