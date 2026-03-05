"""
Feedback Sessions — Butler-driven task disambiguation (v0.9.1).

Generates questions about ambiguous tasks (missing due date, no project, vague names)
and schedules sessions on butler_update_days.
"""
from datetime import datetime, date, time, timedelta
from typing import Optional, List

from ..db import get_db
from ..config import Config
from ..models import FeedbackSession, FeedbackQuestion


# ── Session management ──────────────────────────────────────────────────────

def get_next_session() -> Optional[FeedbackSession]:
    """Get the next upcoming (pending) feedback session."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM feedback_sessions
            WHERE status = 'pending' AND scheduled_for >= datetime('now')
            ORDER BY scheduled_for ASC
            LIMIT 1
        """).fetchone()
        return FeedbackSession.from_row(row) if row else None


def get_session_by_id(session_id: int) -> Optional[FeedbackSession]:
    """Get a feedback session by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM feedback_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return FeedbackSession.from_row(row) if row else None


def ensure_upcoming_session() -> FeedbackSession:
    """
    Ensure there is at least one pending session in the future.

    If no pending session exists, creates one scheduled for the next
    butler_update_day (from config).

    Returns the next upcoming session.
    """
    existing = get_next_session()
    if existing:
        return existing

    # Find the next butler update day
    update_days = Config.get("butler_update_days", ["monday", "wednesday", "friday"])
    update_time = Config.get("butler_update_time", "09:00")

    day_to_num = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    now = datetime.now()
    today_weekday = now.weekday()

    try:
        hour, minute = map(int, update_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 9, 0

    # Find next occurrence of any update day
    best_dt = None
    for day_name in update_days:
        target = day_to_num.get(day_name.lower())
        if target is None:
            continue

        days_ahead = (target - today_weekday) % 7
        candidate_date = now.date() + timedelta(days=days_ahead)
        candidate_dt = datetime.combine(candidate_date, time(hour, minute))

        # If it's today but time has passed, try next week
        if candidate_dt <= now:
            candidate_dt += timedelta(days=7)

        if best_dt is None or candidate_dt < best_dt:
            best_dt = candidate_dt

    if best_dt is None:
        # Fallback: tomorrow at update time
        best_dt = datetime.combine(now.date() + timedelta(days=1), time(hour, minute))

    return create_session(scheduled_for=best_dt, session_type="scheduled")


def create_session(
    scheduled_for: Optional[datetime] = None,
    session_type: str = "scheduled",
) -> FeedbackSession:
    """Create a new feedback session."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO feedback_sessions (session_type, status, scheduled_for)
            VALUES (?, 'pending', ?)
        """, (session_type, scheduled_for.isoformat() if scheduled_for else None))
        session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return get_session_by_id(session_id)


def start_session(session_id: int) -> FeedbackSession:
    """
    Start a feedback session: set status to 'active' and generate questions.

    Questions target ambiguous tasks:
    - Tasks without a due date
    - Tasks without a project
    - Tasks with very short/vague names
    """
    with get_db() as conn:
        conn.execute("""
            UPDATE feedback_sessions
            SET status = 'active', started_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))

    # Generate questions
    questions = _generate_questions(session_id)

    # Update question count
    with get_db() as conn:
        conn.execute("""
            UPDATE feedback_sessions
            SET questions_asked = ?
            WHERE id = ?
        """, (len(questions), session_id))

    return get_session_by_id(session_id)


def complete_session(session_id: int) -> FeedbackSession:
    """Mark a session as completed."""
    with get_db() as conn:
        # Count answered questions
        answered = conn.execute("""
            SELECT COUNT(*) FROM feedback_questions
            WHERE session_id = ? AND status = 'answered'
        """, (session_id,)).fetchone()[0]

        conn.execute("""
            UPDATE feedback_sessions
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                questions_answered = ?
            WHERE id = ?
        """, (answered, session_id))

    # Ensure there's always another session coming
    ensure_upcoming_session()

    return get_session_by_id(session_id)


# ── Question generation ─────────────────────────────────────────────────────

def _generate_questions(session_id: int) -> List[FeedbackQuestion]:
    """
    Generate disambiguation questions for ambiguous tasks.

    Targets:
    1. Tasks without due date: "When should '{name}' be due?"
    2. Tasks without project: "What project does '{name}' belong to?"
    3. Tasks with very short names: "Can you give more detail on '{name}'?"
    """
    from ..services import task_service

    questions = []
    active_tasks = task_service.get_all_tasks(include_done=False)

    max_questions = 10

    for task in active_tasks:
        if len(questions) >= max_questions:
            break

        # No due date
        if task.due_date is None and len(questions) < max_questions:
            q = _create_question(
                session_id=session_id,
                target_type="task",
                target_id=task.id,
                question_text=f"When should \"{task.name}\" be due by?",
            )
            questions.append(q)

        # No project
        if task.project_id is None and len(questions) < max_questions:
            q = _create_question(
                session_id=session_id,
                target_type="task",
                target_id=task.id,
                question_text=f"What project does \"{task.name}\" belong to?",
            )
            questions.append(q)

        # Very short name (likely vague)
        if len(task.name.split()) <= 2 and len(questions) < max_questions:
            q = _create_question(
                session_id=session_id,
                target_type="task",
                target_id=task.id,
                question_text=f"Can you clarify what \"{task.name}\" means? It's quite brief.",
            )
            questions.append(q)

    return questions


def _create_question(
    session_id: int,
    target_type: str,
    target_id: int,
    question_text: str,
) -> FeedbackQuestion:
    """Create a feedback question in the database."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO feedback_questions
                (session_id, target_type, target_id, question_text, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (session_id, target_type, target_id, question_text))
        question_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return get_question_by_id(question_id)


# ── Question answering ──────────────────────────────────────────────────────

def get_question_by_id(question_id: int) -> Optional[FeedbackQuestion]:
    """Get a question by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM feedback_questions WHERE id = ?", (question_id,)
        ).fetchone()
        return FeedbackQuestion.from_row(row) if row else None


def get_session_questions(session_id: int) -> List[FeedbackQuestion]:
    """Get all questions for a session."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM feedback_questions
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,)).fetchall()
        return [FeedbackQuestion.from_row(row) for row in rows]


def get_pending_questions(session_id: int) -> List[FeedbackQuestion]:
    """Get unanswered questions for a session."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM feedback_questions
            WHERE session_id = ? AND status = 'pending'
            ORDER BY id ASC
        """, (session_id,)).fetchall()
        return [FeedbackQuestion.from_row(row) for row in rows]


def answer_question(question_id: int, answer: str) -> FeedbackQuestion:
    """Record an answer for a question."""
    with get_db() as conn:
        conn.execute("""
            UPDATE feedback_questions
            SET answer_text = ?, status = 'answered'
            WHERE id = ?
        """, (answer, question_id))

    return get_question_by_id(question_id)


def skip_question(question_id: int) -> FeedbackQuestion:
    """Skip a question."""
    with get_db() as conn:
        conn.execute("""
            UPDATE feedback_questions
            SET status = 'skipped'
            WHERE id = ?
        """, (question_id,))

    return get_question_by_id(question_id)


# ── Status for Butler widget ────────────────────────────────────────────────

def get_session_status() -> dict:
    """
    Get feedback session status for the Butler widget.

    Returns dict with:
    - next_session: datetime or None
    - next_session_id: int or None
    - total_pending: int (pending questions across active sessions)
    - sessions_completed_this_week: int
    """
    next_session = get_next_session()

    with get_db() as conn:
        # Pending questions across active sessions
        pending_count = conn.execute("""
            SELECT COUNT(*) FROM feedback_questions fq
            JOIN feedback_sessions fs ON fq.session_id = fs.id
            WHERE fs.status = 'active' AND fq.status = 'pending'
        """).fetchone()[0]

        # Sessions completed this week
        completed = conn.execute("""
            SELECT COUNT(*) FROM feedback_sessions
            WHERE status = 'completed'
              AND completed_at >= date('now', 'weekday 0', '-7 days')
        """).fetchone()[0]

    return {
        "next_session": next_session.scheduled_for.isoformat() if next_session and next_session.scheduled_for else None,
        "next_session_id": next_session.id if next_session else None,
        "total_pending_questions": pending_count,
        "sessions_completed_this_week": completed,
    }


# ── CLI interactive session ─────────────────────────────────────────────────

def start_interactive_session(log=None) -> bool:
    """
    Start an interactive feedback session from the CLI.

    Creates or activates a session, then walks through each question.
    """
    # Get or create a session
    session = get_next_session()
    if session:
        session = start_session(session.id)
    else:
        session = create_session(session_type="user_initiated")
        session = start_session(session.id)

    questions = get_pending_questions(session.id)

    if not questions:
        print("\n✅ No ambiguous items to review right now!")
        complete_session(session.id)
        if log:
            log.set_result(True, {"questions": 0})
        return True

    print(f"\n📋 Feedback Session ({len(questions)} questions)\n")
    print("Answer each question, or type 'skip' to skip, 'done' to end early.\n")

    answered = 0
    for i, q in enumerate(questions, 1):
        print(f"  [{i}/{len(questions)}] {q.question_text}")

        try:
            response = input("  → ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Session paused.")
            break

        if response.lower() == "done":
            break
        elif response.lower() == "skip":
            skip_question(q.id)
            print("  (skipped)")
        elif response:
            answer_question(q.id, response)
            answered += 1
            print("  ✓ Noted")
        print()

    complete_session(session.id)
    print(f"\n✓ Session complete. Answered {answered}/{len(questions)} questions.")

    if log:
        log.set_result(True, {"answered": answered, "total": len(questions)})

    return True
