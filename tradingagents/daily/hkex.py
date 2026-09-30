"""HKEX cash-session calendar.

The Hong Kong job fires at 08:15 Asia/Hong_Kong. Five names take about 40
minutes, so that start finishes before the 09:30 open. Cloud Scheduler can
only say Monday–Friday, so full-day
closures are skipped here. A half day (the morning session still opens at
09:30) is a trading day.

The 2026 dates are the securities-market holiday schedule in HKEX circular
CT/075/25. Lunar holidays move every year, so a later year needs that year's
circular added to ``_PUBLISHED`` before the job can skip them.
"""

from __future__ import annotations

from datetime import date

# Full-day closures. Half days are omitted on purpose.
_PUBLISHED: dict[int, set[date]] = {
    2026: {
        date(2026, 1, 1),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 4, 3),
        date(2026, 4, 6),
        date(2026, 4, 7),
        date(2026, 5, 1),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 1),
        date(2026, 10, 1),
        date(2026, 10, 19),
        date(2026, 12, 25),
    },
}


def is_hkex_session(day: date) -> bool:
    """Whether the HKEX cash session opens on ``day``."""
    if day.weekday() >= 5:
        return False
    published = _PUBLISHED.get(day.year)
    if published is None:
        return True
    return day not in published
