"""Tests for agent/review_queue.py — reason codes, categories, CRUD, resolve."""
import pytest

from ..agent.review_queue import (
    _REASON_CODES,
    _REASON_CODE_CATEGORY,
    _normalize_reason_code,
    _normalize_status,
    create_review_item,
    get_review_item,
    list_review_items,
    resolve_review_item,
)


class TestReasonCodes:
    def test_all_reason_codes_have_category(self):
        for code in _REASON_CODES:
            assert code in _REASON_CODE_CATEGORY, f"Missing category for {code}"

    def test_normalize_known_codes(self):
        assert _normalize_reason_code("ambiguity") == "ambiguity"
        assert _normalize_reason_code("POLICY_GATE") == "policy_gate"
        assert _normalize_reason_code("  plan_review  ") == "plan_review"

    def test_normalize_unknown_code_falls_back(self):
        assert _normalize_reason_code("nonsense") == "manual_review"
        assert _normalize_reason_code(None) == "manual_review"
        assert _normalize_reason_code("") == "manual_review"

    def test_normalize_status(self):
        assert _normalize_status("pending") == "pending"
        assert _normalize_status("APPROVED") == "approved"
        assert _normalize_status("garbage") == "pending"
        assert _normalize_status(None) == "pending"


class TestCreateAndGetReview:
    def test_create_and_get(self):
        item = create_review_item(reason_code="ambiguity", payload={"q": "which?"})
        assert item["review_id"].startswith("review-")
        assert item["reason_code"] == "ambiguity"
        assert item["category"] == "clarification"
        assert item["status"] == "pending"
        assert item["payload"]["q"] == "which?"

        fetched = get_review_item(item["review_id"])
        assert fetched is not None
        assert fetched["review_id"] == item["review_id"]

    def test_create_with_unknown_reason_code(self):
        item = create_review_item(reason_code="unknown_thing")
        assert item["reason_code"] == "manual_review"

    def test_get_nonexistent_returns_none(self):
        assert get_review_item("review-does-not-exist") is None


class TestListReviewItems:
    def test_list_pending(self):
        create_review_item(reason_code="approval")
        create_review_item(reason_code="clarification")
        items = list_review_items(status="pending")
        assert len(items) >= 2

    def test_list_filters_by_reason_code(self):
        create_review_item(reason_code="approval")
        create_review_item(reason_code="clarification")
        items = list_review_items(reason_code="approval")
        assert all(i["reason_code"] == "approval" for i in items)


class TestResolveReviewItem:
    def test_resolve_sets_status(self):
        item = create_review_item(reason_code="approval")
        resolved = resolve_review_item(item["review_id"], status="approved", resolution_notes="LGTM")
        assert resolved is not None
        assert resolved["status"] == "approved"
        assert resolved["resolution_notes"] == "LGTM"
        assert resolved["resolved_at"] is not None

    def test_resolve_back_to_pending_raises(self):
        item = create_review_item(reason_code="approval")
        with pytest.raises(ValueError, match="pending"):
            resolve_review_item(item["review_id"], status="pending")

    def test_resolve_nonexistent_returns_none(self):
        result = resolve_review_item("review-no-such-thing")
        assert result is None
