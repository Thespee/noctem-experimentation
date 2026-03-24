"""Tests for scheduler/jobs.py — 3-condition gate logic in IdleCoordinator."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from ..scheduler.jobs import IdleCoordinator, COOLDOWN_SECONDS, JobRuntimeStats


class TestGateCheck:
    """The gate should open only when: no queued, no processing, user idle >= cooldown."""

    def _make_coordinator(self, cooldown=10):
        return IdleCoordinator(cooldown_seconds=cooldown)

    @patch("noctem.scheduler.jobs.queue_metrics")
    def test_gate_closed_when_items_queued(self, mock_metrics):
        mock_metrics.return_value = {"queued_count": 3, "processing_count": 0}
        coord = self._make_coordinator(cooldown=0)
        coord._last_user_activity_at = datetime.utcnow() - timedelta(seconds=300)
        gate_open, details = coord._gate_check()
        assert not gate_open
        assert details["queued_count"] == 3

    @patch("noctem.scheduler.jobs.queue_metrics")
    def test_gate_closed_when_items_processing(self, mock_metrics):
        mock_metrics.return_value = {"queued_count": 0, "processing_count": 1}
        coord = self._make_coordinator(cooldown=0)
        coord._last_user_activity_at = datetime.utcnow() - timedelta(seconds=300)
        gate_open, details = coord._gate_check()
        assert not gate_open
        assert details["processing_count"] == 1

    @patch("noctem.scheduler.jobs.queue_metrics")
    def test_gate_closed_when_user_active(self, mock_metrics):
        mock_metrics.return_value = {"queued_count": 0, "processing_count": 0}
        coord = self._make_coordinator(cooldown=120)
        coord._last_user_activity_at = datetime.utcnow()  # just now
        gate_open, details = coord._gate_check()
        assert not gate_open
        assert not details["user_idle"]

    @patch("noctem.scheduler.jobs.queue_metrics")
    def test_gate_open_when_all_conditions_met(self, mock_metrics):
        mock_metrics.return_value = {"queued_count": 0, "processing_count": 0}
        coord = self._make_coordinator(cooldown=10)
        coord._last_user_activity_at = datetime.utcnow() - timedelta(seconds=60)
        gate_open, details = coord._gate_check()
        assert gate_open
        assert details["user_idle"]


class TestJobRuntimeStats:
    def test_record_success(self):
        stats = JobRuntimeStats(name="test")
        stats.record(duration_seconds=1.5, ok=True)
        assert stats.runs == 1
        assert stats.failures == 0
        assert stats.last_error is None
        assert len(stats.durations) == 1

    def test_record_failure(self):
        stats = JobRuntimeStats(name="test")
        stats.record(duration_seconds=0.5, ok=False, error="boom")
        assert stats.runs == 1
        assert stats.failures == 1
        assert stats.last_error == "boom"

    def test_expected_runtime_uses_median(self):
        stats = JobRuntimeStats(name="test")
        for d in [1.0, 2.0, 3.0, 4.0, 5.0]:
            stats.record(duration_seconds=d, ok=True)
        assert stats.expected_runtime_seconds(fallback_seconds=99) == 3.0

    def test_expected_runtime_fallback(self):
        stats = JobRuntimeStats(name="test")
        assert stats.expected_runtime_seconds(fallback_seconds=42) == 42.0


class TestRecordUserActivity:
    def test_record_resets_idle(self):
        coord = IdleCoordinator(cooldown_seconds=10)
        coord._last_user_activity_at = datetime.utcnow() - timedelta(minutes=30)
        coord.record_user_activity(source="test")
        diff = (datetime.utcnow() - coord._last_user_activity_at).total_seconds()
        assert diff < 2
        assert not coord._idle_mode_entered
