"""Time-block/calendar helpers for v0.9.4."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from ..db import get_db
from ..models import TimeBlock


@dataclass
class TimeGap:
    start: datetime
    end: datetime
    duration_minutes: int

    @property
    def description(self) -> str:
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')} ({self.duration_minutes} min)"


DEFAULT_WORK_START = time(9, 0)
DEFAULT_WORK_END = time(18, 0)
MIN_GAP_MINUTES = 15


def get_time_blocks_for_date(target_date: date) -> list[TimeBlock]:
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM time_blocks
            WHERE start_time >= ? AND start_time < ?
            ORDER BY start_time ASC
            """,
            (start, end),
        ).fetchall()
    return [TimeBlock.from_row(row) for row in rows]


def get_calendar_gaps(
    target_date: date | None = None,
    work_start: time = DEFAULT_WORK_START,
    work_end: time = DEFAULT_WORK_END,
) -> list[TimeGap]:
    day = target_date or date.today()
    blocks = get_time_blocks_for_date(day)
    day_start = datetime.combine(day, work_start)
    day_end = datetime.combine(day, work_end)
    current = day_start
    gaps: list[TimeGap] = []

    sorted_blocks = sorted(blocks, key=lambda b: b.start_time if b.start_time else day_start)
    for block in sorted_blocks:
        start_time = block.start_time
        end_time = block.end_time
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        if not start_time or not end_time:
            continue
        if end_time < current or start_time > day_end:
            continue
        if start_time > current:
            gap_end = min(start_time, day_end)
            minutes = int((gap_end - current).total_seconds() / 60)
            if minutes >= MIN_GAP_MINUTES:
                gaps.append(TimeGap(start=current, end=gap_end, duration_minutes=minutes))
        current = max(current, end_time)

    if current < day_end:
        minutes = int((day_end - current).total_seconds() / 60)
        if minutes >= MIN_GAP_MINUTES:
            gaps.append(TimeGap(start=current, end=day_end, duration_minutes=minutes))

    return gaps
