"""
Habit service - CRUD operations and tracking for habits.
"""
from typing import Optional
from datetime import date, datetime, timedelta
import json
from ..db import get_db
from ..models import Habit, HabitLog
from .base import log_action


def create_habit(
    name: str,
    goal_id: Optional[int] = None,
    frequency: str = "daily",
    target_count: int = 1,
    custom_days: Optional[list[str]] = None,
    time_preference: str = "anytime",
    duration_minutes: Optional[int] = None,
) -> Habit:
    """Create a new habit."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO habits (name, goal_id, frequency, target_count, custom_days, time_preference, duration_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                goal_id,
                frequency,
                target_count,
                json.dumps(custom_days) if custom_days else None,
                time_preference,
                duration_minutes,
            ),
        )
        habit_id = cursor.lastrowid

    log_action("habit_created", "habit", habit_id, {"name": name, "frequency": frequency})
    return get_habit(habit_id)


def get_habit(habit_id: int) -> Optional[Habit]:
    """Get a habit by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
        return Habit.from_row(row)


def get_habit_by_name(name: str) -> Optional[Habit]:
    """Get a habit by name (case-insensitive partial match)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM habits WHERE LOWER(name) LIKE LOWER(?) AND active = 1 ORDER BY created_at DESC LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
        return Habit.from_row(row)


def get_active_habits() -> list[Habit]:
    """Get all active habits."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM habits WHERE active = 1 ORDER BY time_preference, name"
        ).fetchall()
        return [Habit.from_row(row) for row in rows]


def get_habits_due_today() -> list[Habit]:
    """Get habits that should be done today based on frequency."""
    habits = get_active_habits()
    today = date.today()
    today_weekday = today.strftime("%a").lower()[:3]  # mon, tue, etc.
    
    due_today = []
    for habit in habits:
        if habit.frequency == "daily":
            due_today.append(habit)
        elif habit.frequency == "weekly":
            # Weekly habits are due any day, user decides when
            due_today.append(habit)
        elif habit.frequency == "custom" and habit.custom_days:
            if today_weekday in habit.custom_days:
                due_today.append(habit)
    
    return due_today


def update_habit(
    habit_id: int,
    name: Optional[str] = None,
    goal_id: Optional[int] = None,
    frequency: Optional[str] = None,
    target_count: Optional[int] = None,
    custom_days: Optional[list[str]] = None,
    time_preference: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    active: Optional[bool] = None,
) -> Optional[Habit]:
    """Update a habit."""
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if goal_id is not None:
        updates.append("goal_id = ?")
        params.append(goal_id)
    if frequency is not None:
        updates.append("frequency = ?")
        params.append(frequency)
    if target_count is not None:
        updates.append("target_count = ?")
        params.append(target_count)
    if custom_days is not None:
        updates.append("custom_days = ?")
        params.append(json.dumps(custom_days))
    if time_preference is not None:
        updates.append("time_preference = ?")
        params.append(time_preference)
    if duration_minutes is not None:
        updates.append("duration_minutes = ?")
        params.append(duration_minutes)
    if active is not None:
        updates.append("active = ?")
        params.append(int(active))

    if not updates:
        return get_habit(habit_id)

    params.append(habit_id)
    query = f"UPDATE habits SET {', '.join(updates)} WHERE id = ?"

    with get_db() as conn:
        conn.execute(query, params)

    log_action("habit_updated", "habit", habit_id)
    return get_habit(habit_id)


def deactivate_habit(habit_id: int) -> Optional[Habit]:
    """Deactivate a habit."""
    return update_habit(habit_id, active=False)


def delete_habit(habit_id: int) -> bool:
    """Delete a habit and its logs. Returns True if deleted."""
    with get_db() as conn:
        conn.execute("DELETE FROM habit_logs WHERE habit_id = ?", (habit_id,))
        cursor = conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        deleted = cursor.rowcount > 0

    if deleted:
        log_action("habit_deleted", "habit", habit_id)
    return deleted


# Habit logging functions

def log_habit(habit_id: int, notes: Optional[str] = None) -> HabitLog:
    """Log a habit completion."""
    now = datetime.now()
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO habit_logs (habit_id, completed_at, notes) VALUES (?, ?, ?)",
            (habit_id, now.isoformat(), notes),
        )
        log_id = cursor.lastrowid

    log_action("habit_logged", "habit", habit_id, {"log_id": log_id})
    return get_habit_log(log_id)


def get_habit_log(log_id: int) -> Optional[HabitLog]:
    """Get a habit log by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM habit_logs WHERE id = ?", (log_id,)).fetchone()
        return HabitLog.from_row(row)


def get_habit_logs(
    habit_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> list[HabitLog]:
    """Get habit logs with optional date filtering."""
    query = "SELECT * FROM habit_logs WHERE habit_id = ?"
    params = [habit_id]

    if start_date:
        query += " AND DATE(completed_at) >= ?"
        params.append(start_date.isoformat())
    if end_date:
        query += " AND DATE(completed_at) <= ?"
        params.append(end_date.isoformat())

    query += " ORDER BY completed_at DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [HabitLog.from_row(row) for row in rows]


def is_habit_done_today(habit_id: int) -> bool:
    """Check if a habit was logged today."""
    today = date.today()
    logs = get_habit_logs(habit_id, start_date=today, end_date=today)
    return len(logs) > 0


# Stats functions

def get_habit_stats(habit_id: int) -> dict:
    """Get statistics for a habit."""
    habit = get_habit(habit_id)
    if not habit:
        return {}

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # This week's completions
    week_logs = get_habit_logs(habit_id, start_date=week_start, end_date=week_end)
    completions_this_week = len(week_logs)

    # Current streak
    streak = _calculate_streak(habit_id, habit.frequency)

    # Total completions
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as total FROM habit_logs WHERE habit_id = ?",
            (habit_id,),
        ).fetchone()
        total_completions = row["total"] if row else 0

    # Completion rate (last 30 days)
    month_start = today - timedelta(days=30)
    month_logs = get_habit_logs(habit_id, start_date=month_start, end_date=today)
    
    expected_completions = 30 if habit.frequency == "daily" else 4 * habit.target_count
    completion_rate = len(month_logs) / expected_completions if expected_completions > 0 else 0

    return {
        "habit_id": habit_id,
        "name": habit.name,
        "completions_this_week": completions_this_week,
        "target_this_week": habit.target_count if habit.frequency == "weekly" else 7,
        "streak": streak,
        "total_completions": total_completions,
        "completion_rate_30d": round(completion_rate * 100, 1),
        "done_today": is_habit_done_today(habit_id),
    }


def _calculate_streak(habit_id: int, frequency: str) -> int:
    """Calculate the current streak for a habit."""
    if frequency != "daily":
        return 0  # Streaks only meaningful for daily habits
    
    today = date.today()
    streak = 0
    current_date = today

    with get_db() as conn:
        while True:
            row = conn.execute(
                """
                SELECT COUNT(*) as count FROM habit_logs 
                WHERE habit_id = ? AND DATE(completed_at) = ?
                """,
                (habit_id, current_date.isoformat()),
            ).fetchone()

            if row["count"] > 0:
                streak += 1
                current_date -= timedelta(days=1)
            elif current_date == today:
                # Haven't done it today yet, check yesterday
                current_date -= timedelta(days=1)
            else:
                break

    return streak


def get_all_habits_stats() -> list[dict]:
    """Get stats for all active habits."""
    habits = get_active_habits()
    return [get_habit_stats(h.id) for h in habits]
