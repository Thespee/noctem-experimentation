"""Scanner hierarchy for Cor Unum ingestion classes."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..db import get_db

logger = logging.getLogger(__name__)

def _with_locked_db_retry(write_fn, source_key: str, op_label: str) -> None:
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            write_fn()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == attempts:
                logger.error("Failed to %s for %s: %s", op_label, source_key, exc)
                return
            time.sleep(0.25 * attempt)
        except Exception as exc:
            logger.error("Failed to %s for %s: %s", op_label, source_key, exc)
            return


def record_run(summary: dict, started_at: datetime) -> None:
    """Write a cu_ingestion_runs record."""
    def _write():
        with get_db() as conn:
            conn.execute(
                """INSERT INTO cu_ingestion_runs
                   (source_key, started_at, finished_at, status,
                    events_ingested, artists_added, venues_added,
                    duplicates_skipped, error_message, raw_summary_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    summary["source_key"],
                    started_at.isoformat(),
                    datetime.utcnow().isoformat(),
                    summary["status"],
                    summary.get("events_ingested", 0),
                    summary.get("artists_added", 0),
                    summary.get("venues_added", 0),
                    summary.get("duplicates_skipped", 0),
                    summary.get("error_message"),
                    json.dumps(summary),
                ),
            )

    _with_locked_db_retry(_write, str(summary.get("source_key")), "record ingestion run")


def update_source_status(source_key: str, status: str, error: str | None) -> None:
    """Update cu_source_registry with latest run status."""
    def _write():
        with get_db() as conn:
            conn.execute(
                """UPDATE cu_source_registry
                   SET last_run_at = ?, last_status = ?, last_error = ?,
                       needs_fixing = ?
                   WHERE source_key = ?""",
                (
                    datetime.utcnow().isoformat(),
                    status,
                    error,
                    1 if status == "error" else 0,
                    source_key,
                ),
            )

    _with_locked_db_retry(_write, source_key, "update source status")


class BaseIngestionScanner(ABC):
    """Shared scanner base for events, fingerprint, and internal janitors."""

    source_key: str
    scanner_class: str
    report_type: str

    def execute(self) -> dict[str, Any]:
        """Execute scanner with standardized run reporting and error handling."""
        started_at = datetime.utcnow()
        summary = self.make_summary(started_at)
        try:
            summary.update(self.perform())
            summary["status"] = "error" if summary.get("error_message") else "success"
        except Exception as exc:
            summary["status"] = "error"
            summary["error_message"] = str(exc)[:1000]
        record_run(summary, started_at)
        update_source_status(
            self.source_key,
            summary["status"],
            summary.get("error_message"),
        )
        return summary

    def make_summary(self, started_at: datetime) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "scanner_class": self.scanner_class,
            "report_type": self.report_type,
            "started_at": started_at.isoformat(),
            "status": "running",
            "events_ingested": 0,
            "artists_added": 0,
            "venues_added": 0,
            "duplicates_skipped": 0,
            "error_message": None,
        }

    @abstractmethod
    def perform(self) -> dict[str, Any]:
        """Run scanner logic and return summary field updates."""

