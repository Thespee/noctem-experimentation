"""Tests for unified execution queue persistence and ordering."""
from noctem.db import get_db

from noctem.services.execution_queue import (
    QUEUE_ITEM_REVIEW_RESUME,
    QUEUE_ITEM_USER_MESSAGE,
    QUEUE_STATUS_COMPLETED,
    QUEUE_STATUS_PROCESSING,
    claim_next_item,
    enqueue_item,
    enqueue_review_resume,
    enqueue_user_message,
    list_queue_items,
    mark_item_completed,
)

def _clear_queue():
    with get_db() as conn:
        conn.execute("DELETE FROM execution_queue")


def test_enqueue_user_message_persists_and_lists():
    _clear_queue()
    queued = enqueue_user_message(
        source="web",
        thread_id="thread-a",
        content="what are my tasks today?",
    )
    assert queued["id"] is not None
    assert queued["item_type"] == QUEUE_ITEM_USER_MESSAGE
    items = list_queue_items(status="queued", limit=20)
    assert any(item["id"] == queued["id"] for item in items)


def test_claim_then_complete_item_updates_status():
    _clear_queue()
    queued = enqueue_item(
        item_type=QUEUE_ITEM_USER_MESSAGE,
        source="web",
        thread_id="thread-b",
        payload={"content": "buy milk tomorrow"},
        idempotency_key="queue-test-claim-complete",
    )
    claimed = claim_next_item("worker-test")
    assert claimed is not None
    assert claimed["id"] == queued["id"]
    assert claimed["status"] == QUEUE_STATUS_PROCESSING

    completed = mark_item_completed(claimed["id"], {"response": "ok"})
    assert completed is not None
    assert completed["status"] == QUEUE_STATUS_COMPLETED
    assert (completed.get("result") or {}).get("response") == "ok"


def test_review_resume_enters_front_of_queue():
    _clear_queue()
    base = enqueue_user_message(
        source="web",
        thread_id="thread-c",
        content="first",
        idempotency_key="queue-order-base",
    )
    _ = base
    review_item = enqueue_review_resume(
        workflow_id=123,
        review_id="review-test-1",
        resolution="yes",
        review_created_at="2026-03-12T00:00:00Z",
    )
    assert review_item["item_type"] == QUEUE_ITEM_REVIEW_RESUME

    claimed = claim_next_item("worker-review")
    assert claimed is not None
    assert claimed["item_type"] == QUEUE_ITEM_REVIEW_RESUME
    assert claimed["id"] == review_item["id"]


def test_idempotency_key_deduplicates_enqueues():
    _clear_queue()
    first = enqueue_item(
        item_type=QUEUE_ITEM_USER_MESSAGE,
        source="web",
        thread_id="thread-d",
        payload={"content": "duplicate test"},
        idempotency_key="same-key-dedupe",
    )
    second = enqueue_item(
        item_type=QUEUE_ITEM_USER_MESSAGE,
        source="web",
        thread_id="thread-d",
        payload={"content": "duplicate test"},
        idempotency_key="same-key-dedupe",
    )
    assert first["id"] == second["id"]
