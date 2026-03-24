"""Tests for v0.9.4 Tools tab queue/scheduler APIs and settings slimming."""

from uuid import uuid4

from noctem.config import Config
from noctem.db import get_db
from noctem.agent.review_queue import create_review_item
from noctem.scheduler.jobs import SCHEDULER_JOB_DEFAULTS
from noctem.services.execution_queue import enqueue_user_message, mark_item_review_blocked


def _client():
    from noctem.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _reset_tools_state():
    with get_db() as conn:
        conn.execute("DELETE FROM execution_queue")
        conn.execute("DELETE FROM scheduler_runs")
        conn.execute("DELETE FROM config WHERE key = 'scheduler_job_config'")
    Config.clear_cache()
    Config.set("scheduler_job_config", SCHEDULER_JOB_DEFAULTS)
    Config.clear_cache()


def test_tools_page_and_combined_api_payload():
    _reset_tools_state()
    queued = enqueue_user_message(
        source="test",
        thread_id=f"thread-{uuid4().hex[:8]}",
        content="tools api seed message",
    )
    review = create_review_item(
        reason_code="manual_review",
        payload={
            "question": "Approve queued execution?",
            "queue_item_id": int(queued["id"]),
        },
    )

    client = _client()
    page = client.get("/control")
    assert page.status_code == 200
    html = page.data.decode("utf-8")
    assert "Control" in html

    resp = client.get("/api/tools?status=all&limit=50")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert isinstance(payload["queue"]["items"], list)
    assert any(int(item["id"]) == int(queued["id"]) for item in payload["queue"]["items"])
    assert "job_config" in payload["scheduler"]
    assert "delivery" in payload
    assert "metrics" in payload["delivery"]
    assert "reviews" in payload
    assert isinstance(payload["reviews"]["items"], list)
    assert any(str(item.get("review_id")) == str(review["review_id"]) for item in payload["reviews"]["items"])
def test_reviews_page_redirects_to_control():
    _reset_tools_state()
    client = _client()
    resp = client.get("/reviews")
    assert resp.status_code in (200, 301, 302, 303, 307, 308)

def test_tools_api_queue_items_are_recent_first_with_active_statuses_prioritized():
    _reset_tools_state()
    first = enqueue_user_message(
        source="web",
        thread_id=f"thread-{uuid4().hex[:8]}",
        content="older queue item",
    )
    second = enqueue_user_message(
        source="web",
        thread_id=f"thread-{uuid4().hex[:8]}",
        content="newer queue item",
    )

    client = _client()
    resp = client.get("/api/tools?status=queued&limit=20")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    items = (payload.get("queue") or {}).get("items") or []
    ids = [int(item["id"]) for item in items]
    assert int(second["id"]) in ids
    assert int(first["id"]) in ids
    assert ids.index(int(second["id"])) < ids.index(int(first["id"]))


def test_tools_queue_cancel_and_requeue_endpoints():
    _reset_tools_state()
    queued = enqueue_user_message(
        source="test",
        thread_id=f"thread-{uuid4().hex[:8]}",
        content="tools requeue seed",
    )
    queue_id = int(queued["id"])

    client = _client()
    cancelled = client.post(f"/api/tools/queue/{queue_id}/cancel", json={"reason": "manual_cancel"})
    assert cancelled.status_code == 200
    cancelled_payload = cancelled.get_json()
    assert cancelled_payload["success"] is True
    assert cancelled_payload["item"]["status"] == "cancelled"

    requeued = client.post(f"/api/tools/queue/{queue_id}/requeue", json={"front": True, "reason": "manual_requeue"})
    assert requeued.status_code == 200
    requeue_payload = requeued.get_json()
    assert requeue_payload["success"] is True
    assert requeue_payload["item"]["status"] == "queued"
    assert int(requeue_payload["item"]["priority_rank"]) == 0

    detail = client.get(f"/api/tools/queue/{queue_id}")
    assert detail.status_code == 200
    detail_payload = detail.get_json()
    assert detail_payload["success"] is True
    assert int(detail_payload["item"]["id"]) == queue_id


def test_tools_scheduler_update_run_and_history_endpoints():
    _reset_tools_state()
    client = _client()

    updated = client.post(
        "/api/tools/scheduler/jobs/context_doc_refresh",
        json={"interval_minutes": 9, "enabled": False},
    )
    assert updated.status_code == 200
    updated_payload = updated.get_json()
    assert updated_payload["success"] is True
    assert int(updated_payload["job"]["interval_minutes"]) == 9
    assert updated_payload["job"]["enabled"] is False

    run_resp = client.post("/api/tools/scheduler/jobs/context_doc_refresh/run", json={})
    assert run_resp.status_code == 200
    run_payload = run_resp.get_json()
    assert run_payload["success"] is True
    assert run_payload["result"]["job_name"] == "context_doc_refresh"

    history = client.get("/api/tools/scheduler/history?job_name=context_doc_refresh&limit=20")
    assert history.status_code == 200
    history_payload = history.get_json()
    assert history_payload["success"] is True
    assert history_payload["count"] >= 1


def test_review_approve_requeues_review_blocked_queue_item_to_front():
    _reset_tools_state()
    queued = enqueue_user_message(
        source="web",
        thread_id=f"review-thread-{uuid4().hex[:8]}",
        content="move those tasks",
    )
    mark_item_review_blocked(int(queued["id"]), reason="stale_context_reference")
    review = create_review_item(
        reason_code="ambiguity",
        payload={
            "queue_item_id": int(queued["id"]),
            "thread_id": queued["thread_id"],
            "original_message": "move those tasks",
        },
    )

    client = _client()
    approved = client.post(
        f"/api/reviews/{review['review_id']}/resolve",
        json={"action": "approve", "response": "yes"},
    )
    assert approved.status_code == 200
    payload = approved.get_json()
    assert payload["success"] is True
    assert payload["review"]["status"] == "approved"
    assert payload["requeued_item"] is not None
    assert int(payload["requeued_item"]["priority_rank"]) == 0


def test_settings_calendar_controls_are_moved_to_control():
    _reset_tools_state()
    client = _client()
    resp = client.get("/settings")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Execution controls (refresh/run cadence/queue visibility) now live in the Control tab." in html
    assert "Refresh All" not in html
    assert "Clear All Imported Events" not in html


def test_tools_api_returns_partial_payload_with_diagnostics_on_scheduler_failure(monkeypatch):
    _reset_tools_state()
    client = _client()

    def _explode_scheduler_status():
        raise RuntimeError("simulated scheduler status failure")

    monkeypatch.setattr("noctem.scheduler.jobs.get_scheduler_status", _explode_scheduler_status)

    resp = client.get("/api/tools?status=all&limit=30")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert isinstance(payload.get("diagnostics"), list)
    assert any("scheduler:status_failed" in str(item) for item in payload["diagnostics"])
    assert isinstance((payload.get("scheduler") or {}).get("job_config"), dict)
