"""Tests for conversation grounding object state and audit history."""

from noctem.db import get_db
from noctem.services.conversation_grounding import (
    get_conversation_state,
    record_grounding_read,
    update_conversation_state,
)


def _clear_grounding_tables():
    with get_db() as conn:
        conn.execute(
            "DELETE FROM object_versions WHERE object_id LIKE 'conversation_state:%'"
        )
        conn.execute(
            "DELETE FROM object_refs WHERE object_id LIKE 'conversation_state:%'"
        )
        conn.execute(
            "DELETE FROM object_context_docs WHERE object_id LIKE 'conversation_state:%'"
        )
        conn.execute(
            "DELETE FROM objects WHERE object_type = 'conversation_state'"
        )
        conn.execute(
            "DELETE FROM object_events WHERE operation LIKE 'conversation_state.%'"
        )


def test_update_conversation_state_creates_version_and_diff():
    _clear_grounding_tables()
    state = update_conversation_state(
        thread_id="ground-thread-1",
        source="web",
        updates={
            "last_scope_ref": "today",
            "last_task_ids": [1, 2, 3],
            "date_anchors": {"last_wednesday": "2026-03-11"},
        },
        summary="Set initial grounding",
        reason="unit_test",
    )
    assert state["last_scope_ref"] == "today"
    assert state["last_task_ids"] == [1, 2, 3]
    assert state["date_anchors"]["last_wednesday"] == "2026-03-11"

    loaded = get_conversation_state("ground-thread-1")
    assert loaded["last_scope_ref"] == "today"
    assert loaded["last_task_ids"] == [1, 2, 3]
    assert loaded["source"] == "web"
    assert loaded["updated_at"] is not None

    with get_db() as conn:
        versions = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM object_versions
            WHERE object_id = 'conversation_state:ground-thread-1'
            """
        ).fetchone()["count"]
        assert int(versions) == 1
        event_row = conn.execute(
            """
            SELECT details_json
            FROM object_events
            WHERE operation = 'conversation_state.update'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    assert event_row is not None
    assert "before_snapshot" in str(event_row["details_json"])
    assert "after_snapshot" in str(event_row["details_json"])
    assert "diff" in str(event_row["details_json"])


def test_record_grounding_read_persists_read_event():
    _clear_grounding_tables()
    update_conversation_state(
        thread_id="ground-thread-2",
        source="web",
        updates={"last_scope_ref": "overdue", "last_task_ids": [9]},
    )
    event_id = record_grounding_read(
        thread_id="ground-thread-2",
        source="web",
        message_text="what are those tasks?",
        resolved={"scope_ref": "overdue"},
    )
    assert event_id.startswith("audit-")

    with get_db() as conn:
        row = conn.execute(
            """
            SELECT details_json
            FROM object_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
    assert row is not None
    payload = str(row["details_json"])
    assert "Grounding state consulted" not in payload
    assert "what are those tasks?" in payload
    assert "scope_ref" in payload
