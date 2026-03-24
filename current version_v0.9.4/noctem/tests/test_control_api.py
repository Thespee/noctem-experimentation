"""Tests for web/app.py control-surface routes."""
import pytest

from ..web.app import create_app
from ..agent.review_queue import create_review_item


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestControlRoute:
    def test_control_returns_200(self, client):
        resp = client.get("/control")
        assert resp.status_code == 200

    def test_reviews_redirects_to_control(self, client):
        resp = client.get("/reviews", follow_redirects=False)
        assert resp.status_code in (301, 302, 308)
        assert "/control" in resp.headers.get("Location", "")

    def test_tools_redirects_to_control(self, client):
        resp = client.get("/tools", follow_redirects=False)
        assert resp.status_code in (301, 302, 308)
        assert "/control" in resp.headers.get("Location", "")


class TestReviewsAPI:
    def test_list_reviews(self, client):
        create_review_item(reason_code="approval", payload={"q": "test"})
        resp = client.get("/api/agent/reviews")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] >= 1

    def test_list_reviews_filter_by_status(self, client):
        create_review_item(reason_code="approval")
        resp = client.get("/api/agent/reviews?status=pending")
        data = resp.get_json()
        assert all(r["status"] == "pending" for r in data["reviews"])

    def test_grouped_reviews(self, client):
        create_review_item(reason_code="approval")
        create_review_item(reason_code="clarification")
        resp = client.get("/api/reviews")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "grouped" in data


class TestTasksActiveAPI:
    def test_active_tasks_returns_200(self, client):
        resp = client.get("/api/tasks/active")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "items" in data
        assert "metrics" in data


class TestResolveReviewAPI:
    def test_resolve_approve(self, client):
        item = create_review_item(reason_code="approval", payload={"q": "approve this?"})
        resp = client.post(
            f"/api/reviews/{item['review_id']}/resolve",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["review"]["status"] == "approved"

    def test_resolve_reject(self, client):
        item = create_review_item(reason_code="approval", payload={"q": "reject this?"})
        resp = client.post(
            f"/api/reviews/{item['review_id']}/resolve",
            json={"action": "reject"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["review"]["status"] == "rejected"

    def test_resolve_not_found(self, client):
        resp = client.post(
            "/api/reviews/review-fake/resolve",
            json={"action": "approve"},
        )
        assert resp.status_code == 404

    def test_resolve_invalid_action(self, client):
        item = create_review_item(reason_code="approval")
        resp = client.post(
            f"/api/reviews/{item['review_id']}/resolve",
            json={"action": "invalid"},
        )
        assert resp.status_code == 400
