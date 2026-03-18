"""Tests for services/async_delivery.py — publish_review_notification."""
import pytest
from unittest.mock import patch

from ..services.async_delivery import publish_review_notification


class TestPublishReviewNotification:
    def test_empty_review_returns_empty(self):
        assert publish_review_notification({}) == []
        assert publish_review_notification(None) == []

    @patch("noctem.services.async_delivery.Config")
    def test_web_delivery_recorded(self, mock_config):
        mock_config.telegram_token.return_value = None
        mock_config.telegram_chat_id.return_value = None

        review = {
            "review_id": "review-test123",
            "reason_code": "approval",
            "category": "approval",
            "payload": {"question": "Approve this?", "workflow_id": 42},
        }
        deliveries = publish_review_notification(review)
        assert len(deliveries) >= 1

        web = [d for d in deliveries if d["channel"] == "web"]
        assert len(web) == 1
        assert web[0]["status"] == "delivered"
        assert web[0]["payload"]["review_id"] == "review-test123"

    @patch("noctem.services.async_delivery.Config")
    def test_telegram_skipped_when_not_configured(self, mock_config):
        mock_config.telegram_token.return_value = None
        mock_config.telegram_chat_id.return_value = None

        review = {
            "review_id": "review-test456",
            "reason_code": "clarification",
            "category": "clarification",
            "payload": {"question": "Which option?"},
        }
        deliveries = publish_review_notification(review)
        tg = [d for d in deliveries if d["channel"] == "telegram"]
        assert len(tg) == 1
        assert tg[0]["status"] == "skipped"
        assert "telegram_not_configured" in (tg[0].get("payload") or {}).get("reason", "")

    @patch("noctem.services.async_delivery.Config")
    def test_notification_text_contains_review_id(self, mock_config):
        """The notification should mention the review ID so the user can act on it."""
        mock_config.telegram_token.return_value = None
        mock_config.telegram_chat_id.return_value = None

        review = {
            "review_id": "review-abc",
            "reason_code": "approval",
            "category": "approval",
            "payload": {"question": "OK?"},
        }
        deliveries = publish_review_notification(review)
        assert any(d["payload"].get("review_id") == "review-abc" for d in deliveries)
