"""Tests for v0.9.4 scheduler producer mode and persisted scheduler telemetry."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from noctem.config import Config
from noctem.db import get_db
from noctem.scheduler.jobs import (
    IdleCoordinator,
    SCHEDULER_JOB_DEFAULTS,
    get_job_run_history,
    get_scheduler_status,
    run_job_now,
    update_job_config,
)
from noctem.services.execution_queue import (
    QUEUE_ITEM_SCHEDULED_JOB,
    enqueue_user_message,
    list_queue_items,
    mark_item_retryable_failure,
)


def _reset_scheduler_state():
    with get_db() as conn:
        conn.execute("DELETE FROM scheduler_runs")
        conn.execute("DELETE FROM execution_queue")
        conn.execute("DELETE FROM config WHERE key = 'scheduler_job_config'")
    Config.clear_cache()


def test_update_job_config_persists_and_status_reflects_changes():
    _reset_scheduler_state()
    Config.set("scheduler_job_config", SCHEDULER_JOB_DEFAULTS)
    Config.clear_cache()

    updated = update_job_config("context_doc_refresh", interval_minutes=12, enabled=False)
    assert updated["interval_minutes"] == 12
    assert updated["enabled"] is False

    persisted = Config.get("scheduler_job_config", {})
    assert persisted["context_doc_refresh"]["interval_minutes"] == 12
    assert persisted["context_doc_refresh"]["enabled"] is False

    status = get_scheduler_status()
    assert status["job_config"]["context_doc_refresh"]["interval_minutes"] == 12
    assert status["job_config"]["context_doc_refresh"]["enabled"] is False


def test_run_job_now_persists_run_and_enqueues_retry_scan():
    _reset_scheduler_state()
    Config.set("scheduler_job_config", SCHEDULER_JOB_DEFAULTS)
    Config.clear_cache()

    queued = enqueue_user_message(
        source="test",
        thread_id=f"thread-{uuid4().hex[:8]}",
        content="retry me later",
        idempotency_key=f"retry-seed-{uuid4().hex[:8]}",
    )
    mark_item_retryable_failure(int(queued["id"]), error="network_offline")

    result = run_job_now("queue_retry_scan")
    assert result["ok"] is True
    assert (result.get("summary") or {}).get("status") == "enqueued"

    queued_items = list_queue_items(status="queued", limit=50)
    scheduled = [
        item
        for item in queued_items
        if item["item_type"] == QUEUE_ITEM_SCHEDULED_JOB
        and isinstance(item.get("payload"), dict)
        and str(item["payload"].get("job_name")) == "queue_retry_scan"
    ]
    assert scheduled

    history = get_job_run_history(job_name="queue_retry_scan", limit=10)
    assert history
    assert history[0]["job_name"] == "queue_retry_scan"
    assert history[0]["ok"] is True


def test_idle_tick_fires_when_gate_conditions_met():
    """v0.9.4.1: 3-condition gate requires no queued/processing items + user idle."""
    _reset_scheduler_state()
    Config.set("scheduler_job_config", SCHEDULER_JOB_DEFAULTS)
    Config.clear_cache()

    for job_name in ("voice_transcription", "context_doc_refresh", "ics_refresh", "queue_retry_scan"):
        update_job_config(job_name, enabled=False)

    coordinator = IdleCoordinator(cooldown_seconds=1, safety_margin=timedelta(seconds=0))
    coordinator._last_user_activity_at = datetime.utcnow() - timedelta(minutes=20)

    # Gate should open: no queued items, no processing, user idle
    gate_open, gate_details = coordinator._gate_check()
    assert gate_open is True, f"Gate should be open when queue is empty and user idle: {gate_details}"
    assert gate_details["queued_count"] == 0
    assert gate_details["processing_count"] == 0
    assert gate_details["user_idle"] is True


def test_idle_tick_blocked_when_queue_has_items():
    """v0.9.4.1: gate blocks when there are queued items (even retryable ones)."""
    _reset_scheduler_state()
    Config.set("scheduler_job_config", SCHEDULER_JOB_DEFAULTS)
    Config.clear_cache()

    queued = enqueue_user_message(
        source="test",
        thread_id=f"idle-thread-{uuid4().hex[:8]}",
        content="pending retry",
        idempotency_key=f"idle-retry-seed-{uuid4().hex[:8]}",
    )
    mark_item_retryable_failure(int(queued["id"]), error="temporary_outage")

    coordinator = IdleCoordinator(cooldown_seconds=1, safety_margin=timedelta(seconds=0))
    coordinator._last_user_activity_at = datetime.utcnow() - timedelta(minutes=20)

    gate_open, gate_details = coordinator._gate_check()
    assert gate_open is False, f"Gate should be closed when queued items exist: {gate_details}"
    assert gate_details["queued_count"] > 0
