"""Reusable temporal-window helpers."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Dict, List, Tuple


def month_periods(start_date: str, end_date_inclusive: str) -> List[Dict[str, str]]:
    """Return calendar-month periods intersecting an inclusive date window."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date_inclusive)
    if end < start:
        raise ValueError("end_date_inclusive must be >= start_date")

    cursor = start.replace(day=1)
    out: List[Dict[str, str]] = []
    while cursor <= end:
        last_day = monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        actual_start = max(start, cursor)
        actual_end = min(end, month_end)
        if actual_start <= actual_end:
            out.append({
                "label": actual_start.strftime("%Y-%m"),
                "start": actual_start.isoformat(),
                "end": (actual_end + timedelta(days=1)).isoformat(),
                "end_inclusive": actual_end.isoformat(),
            })
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return out


def annual_periods(start_year: int, end_year: int) -> List[Dict[str, str]]:
    if end_year < start_year:
        raise ValueError("end_year must be >= start_year")
    return [
        {"label": str(year), "start": f"{year}-01-01", "end": f"{year + 1}-01-01"}
        for year in range(start_year, end_year + 1)
    ]
