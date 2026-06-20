"""
Shared timezone helper — the whole pipeline works in IST (Asia/Kolkata).

India has no DST, so a fixed +5:30 offset is exact and needs no tz database,
which means 'today' / 'now' are identical on a local Windows machine and on
Vercel's UTC servers. Use today_ist() / now_ist() instead of date.today() /
datetime.now() anywhere a date or timestamp is derived from the clock.

Created 19-Jun-2026 IST.
"""
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    """Current timezone-aware datetime in IST."""
    return datetime.now(IST)


def today_ist():
    """Current calendar date in IST."""
    return now_ist().date()