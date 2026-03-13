"""Queue runtime integration tests for queued chat execution."""

from datetime import date, timedelta
from uuid import uuid4
from noctem.config import Config

from noctem.db import get_db
from noctem.agent.execution_queue_runtime import (
    process_chat_message_via_queue,
    process_execution_queue,
)
from noctem.services.async_delivery import list_delivery_publications, publish_queue_result
from noctem.services import task_service
from noctem.services.conversation_grounding import update_conversation_state
from noctem.services.execution_queue import enqueue_scheduled_job, list_queue_items


def _clear_queue():
    with get_db() as conn:
        conn.execute("DELETE FROM execution_queue")
        conn.execute("DELETE FROM delivery_publications")
        conn.execute("DELETE FROM object_versions WHERE object_id LIKE 'conversation_state:%'")
        conn.execute("DELETE FROM object_refs WHERE object_id LIKE 'conversation_state:%'")
        conn.execute("DELETE FROM objects WHERE object_type = 'conversation_state'")
        conn.execute("DELETE FROM object_events WHERE operation LIKE 'conversation_state.%'")


def test_process_chat_message_via_queue_returns_processed_result():
    _clear_queue()
    marker = f"queue-runtime-{uuid4().hex[:8]}"
    result = process_chat_message_via_queue(
        f"buy {marker} tomorrow",
        source="web",
        thread_id=f"thread-{uuid4().hex[:8]}",
    )
    assert result.get("queue_item_id") is not None
    assert result.get("status") in {"completed", "interrupted"}
    items = list_queue_items(status="all", limit=20)
    queued_item = next(item for item in items if item["id"] == result["queue_item_id"])
    assert queued_item["status"] in {"completed", "review_blocked", "queued"}


def test_queue_runtime_persists_latest_model_progress(monkeypatch):
    _clear_queue()

    def _fake_process_chat_message(
        message: str,
        *,
        source: str = "web",
        thread_id: str | None = None,
        progress_callback=None,
    ):
        if callable(progress_callback):
            progress_callback({"stage": "started", "elapsed_seconds": 0.0})
            progress_callback({"stage": "heartbeat", "elapsed_seconds": 1.2})
            progress_callback({"stage": "completed", "elapsed_seconds": 2.4})
        return {"response": "ok", "status": "completed", "mode": "model"}

    monkeypatch.setattr(
        "noctem.agent.execution_queue_runtime._process_chat_message_direct",
        _fake_process_chat_message,
    )

    result = process_chat_message_via_queue(
        "hello progress",
        source="web",
        thread_id=f"thread-{uuid4().hex[:8]}",
    )
    assert result.get("status") == "completed"
    assert result.get("model_progress", {}).get("stage") == "completed"

    items = list_queue_items(status="all", limit=30)
    queued_item = next(item for item in items if item["id"] == result["queue_item_id"])
    assert queued_item["status"] == "completed"
    assert queued_item.get("result", {}).get("model_progress", {}).get("stage") == "completed"


def test_state_first_resolution_maps_those_tasks_to_overdue_scope():
    _clear_queue()
    marker = f"overdue-state-{uuid4().hex[:8]}"
    overdue = task_service.create_task(marker, due_date=date.today() - timedelta(days=2))
    thread_id = f"thread-{uuid4().hex[:8]}"
    update_conversation_state(
        thread_id=thread_id,
        source="web",
        updates={"last_scope_ref": "overdue", "last_task_ids": [overdue.id]},
        summary="Seed overdue scope",
    )

    result = process_chat_message_via_queue(
        "what are those tasks?",
        source="web",
        thread_id=thread_id,
    )
    assert result.get("queue_item_id") is not None
    assert result.get("status") == "completed"
    assert "overdue task" in str(result.get("response") or "").lower()


def test_scheduled_job_queue_item_executes_via_runtime():
    _clear_queue()
    queued = enqueue_scheduled_job(
        job_name="context_doc_refresh",
        payload={"max_items": 1},
        idempotency_key=f"sched-context-refresh-{uuid4().hex[:8]}",
    )
    results = process_execution_queue(
        worker_id="scheduler-test-worker",
        max_items=10,
        stop_on_item_id=int(queued["id"]),
    )
    matching = [item for item in results if int(item.get("queue_item_id") or -1) == int(queued["id"])]
    assert matching
    assert matching[0].get("status") == "completed"
    assert matching[0].get("job_name") == "context_doc_refresh"
    assert isinstance(matching[0].get("deliveries"), list)
    assert any(
        d.get("channel") == "web"
        and d.get("status") == "skipped"
        and (d.get("payload") or {}).get("reason") == "scheduled_job_hidden_from_chat_channels"
        for d in matching[0].get("deliveries") or []
    )
    assert any(
        d.get("channel") == "telegram"
        and d.get("status") == "skipped"
        and (d.get("payload") or {}).get("reason") == "scheduled_job_hidden_from_chat_channels"
        for d in matching[0].get("deliveries") or []
    )

    items = list_queue_items(status="all", limit=20)
    stored = next(item for item in items if int(item["id"]) == int(queued["id"]))
    assert stored["status"] == "completed"

    delivery_rows = list_delivery_publications(queue_item_id=int(queued["id"]), limit=20)
    assert delivery_rows
    assert any(
        row["channel"] == "web"
        and row["status"] == "skipped"
        and (row.get("payload") or {}).get("reason") == "scheduled_job_hidden_from_chat_channels"
        for row in delivery_rows
    )
    assert any(
        row["channel"] == "telegram"
        and row["status"] == "skipped"
        and (row.get("payload") or {}).get("reason") == "scheduled_job_hidden_from_chat_channels"
        for row in delivery_rows
    )


def test_publish_queue_result_for_telegram_user_message_uses_async_send(monkeypatch):
    _clear_queue()
    prior_token = Config.get("telegram_bot_token", "")
    prior_chat_id = Config.get("telegram_chat_id", "")
    try:
        Config.set("telegram_bot_token", "test-token")
        Config.set("telegram_chat_id", "123456")
        Config.clear_cache()

        sent = {"count": 0}

        class _FakeResponse:
            ok = True
            status_code = 200
            text = "ok"

            @staticmethod
            def json():
                return {"ok": True}

        def _fake_post(url, json=None, timeout=None):
            sent["count"] += 1
            assert "sendMessage" in str(url)
            assert str((json or {}).get("chat_id")) == "123456"
            return _FakeResponse()

        monkeypatch.setattr("noctem.services.async_delivery.requests.post", _fake_post)

        deliveries = publish_queue_result(
            {"id": 99991, "item_type": "user_message", "source": "telegram", "thread_id": "thread-telegram"},
            {"status": "completed", "response": "done", "mode": "model"},
        )

        assert sent["count"] >= 1
        assert any(
            row.get("channel") == "telegram" and row.get("status") == "delivered"
            for row in deliveries
            if isinstance(row, dict)
        )
    finally:
        Config.set("telegram_bot_token", prior_token)
        Config.set("telegram_chat_id", prior_chat_id)
        Config.clear_cache()
