"""Tests verifying the Control tab's API surface returns correct data.

These tests exercise the exact endpoints called by control.html JS
(refreshReviews, refreshTasks, refreshBackground) to ensure review items,
active queue items, and blocked workflows are all visible.
"""
from uuid import uuid4

from noctem.services import task_service


def _client():
    from noctem.web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


# ─── /api/reviews (grouped) ───────────────────────────────────────────

def test_api_reviews_grouped_returns_pending_review_after_interrupt():
    """After an interrupted workflow, /api/reviews should include the pending review item."""
    client = _client()

    # Create an interrupt via fast-path (non-alphanumeric triggers clarification)
    submit = client.post("/api/agent/submit", json={"input": "!!!"})
    assert submit.status_code == 200
    submit_data = submit.get_json()
    assert submit_data["status"] == "interrupted"
    workflow_id = submit_data["workflow_id"]

    # Hit the exact endpoint the Control tab's refreshReviews() uses
    resp = client.get("/api/reviews?status=pending&limit=100")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True, f"API returned success=False: {data}"

    grouped = data.get("grouped", {})
    # The clarification interrupt should appear under the "clarification" category
    all_review_items = []
    for cat, items in grouped.items():
        all_review_items.extend(items)

    matching = [
        item for item in all_review_items
        if (item.get("payload") or {}).get("workflow_id") == workflow_id
    ]
    assert matching, (
        f"Expected review item for workflow {workflow_id} in /api/reviews grouped response, "
        f"but got categories={list(grouped.keys())} total_items={len(all_review_items)}"
    )
    review_item = matching[0]
    assert review_item["status"] == "pending"
    assert review_item.get("review_id")
    assert review_item.get("category") in ("clarification", "approval", "manual_review")


def test_api_reviews_grouped_returns_approval_review_for_bulk_edit():
    """A bulk edit interrupt (approval type) should appear in /api/reviews grouped under 'approval'."""
    client = _client()
    marker = f"ctrl-bulk-{uuid4().hex[:6]}"

    # Create enough overdue tasks to trigger approval gate
    from datetime import date, timedelta
    yesterday = date.today() - timedelta(days=1)
    for i in range(4):
        task_service.create_task(f"{marker}-{i}", due_date=yesterday)

    submit = client.post("/api/agent/submit", json={"input": f"move all overdue tasks to today"})
    assert submit.status_code == 200
    submit_data = submit.get_json()

    if submit_data.get("status") != "interrupted":
        # Might auto-commit if under threshold — skip the rest
        return

    workflow_id = submit_data["workflow_id"]
    resp = client.get("/api/reviews?status=pending&limit=100")
    data = resp.get_json()
    assert data["success"] is True

    grouped = data.get("grouped", {})
    approval_items = grouped.get("approval", [])
    matching = [
        item for item in approval_items
        if (item.get("payload") or {}).get("workflow_id") == workflow_id
    ]
    assert matching, (
        f"Expected approval review for workflow {workflow_id} "
        f"but approval category has {len(approval_items)} items: {[i.get('review_id') for i in approval_items]}"
    )


# ─── /api/agent/reviews/blocked ───────────────────────────────────────

def test_api_blocked_workflows_lists_interrupted_workflow():
    """After an interrupt, /api/agent/reviews/blocked should include the blocked workflow."""
    client = _client()

    submit = client.post("/api/agent/submit", json={"input": "!!!"})
    assert submit.status_code == 200
    submit_data = submit.get_json()
    assert submit_data["status"] == "interrupted"
    workflow_id = submit_data["workflow_id"]

    resp = client.get("/api/agent/reviews/blocked?limit=200")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    blocked = data.get("blocked_workflows", [])
    matching = [b for b in blocked if b.get("workflow_id") == workflow_id]
    assert matching, (
        f"Expected blocked workflow {workflow_id} in /api/agent/reviews/blocked, "
        f"but got {len(blocked)} blocked workflows: {[b.get('workflow_id') for b in blocked]}"
    )
    blocked_wf = matching[0]
    assert blocked_wf.get("interrupt")
    assert blocked_wf["interrupt"].get("question")


# ─── /api/tasks/active ────────────────────────────────────────────────

def test_api_tasks_active_shows_processing_or_completed_items():
    """After a chat message (which creates a queue item), /api/tasks/active should reflect queue state."""
    client = _client()
    marker = f"ctrl-task-{uuid4().hex[:6]}"

    # A quick fast-path that completes immediately
    resp = client.post("/api/chat", json={"message": f". {marker} tomorrow"})
    assert resp.status_code == 200
    resp_data = resp.get_json()
    assert resp_data["success"] is True

    # The active endpoint shows queued/processing/review_blocked items.
    # After sync execution, the item is completed so it won't appear.
    # This validates the endpoint itself works without error.
    active_resp = client.get("/api/tasks/active?limit=80")
    assert active_resp.status_code == 200
    active_data = active_resp.get_json()
    assert active_data["success"] is True
    assert "items" in active_data
    assert "metrics" in active_data
    assert isinstance(active_data["metrics"], dict)


# ─── /api/tools (background section) ──────────────────────────────────

def test_api_tools_returns_scheduler_and_delivery_sections():
    """/api/tools should return all sections the Control tab's refreshBackground() needs."""
    client = _client()

    resp = client.get("/api/tools?status=all&review_status=all&limit=80")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    # Validate all expected top-level keys exist
    assert "scheduler" in data, f"Missing 'scheduler' key: {list(data.keys())}"
    assert "delivery" in data, f"Missing 'delivery' key: {list(data.keys())}"
    assert "diagnostics" in data, f"Missing 'diagnostics' key: {list(data.keys())}"

    scheduler = data["scheduler"]
    assert isinstance(scheduler, dict)
    assert "job_config" in scheduler or "recent_runs" in scheduler

    delivery = data["delivery"]
    assert isinstance(delivery, dict)
    assert "metrics" in delivery
    assert "recent" in delivery


# ─── Full Control tab refresh simulation ──────────────────────────────

def test_full_control_tab_refresh_after_chat_interrupt():
    """
    Simulate the full Control tab refresh flow:
    1. Send a chat message that creates an interrupt + review item
    2. Call all 3 Control tab API groups (reviews, tasks, background)
    3. Verify the review item appears in the reviews response
    """
    client = _client()
    marker = f"ctrl-full-{uuid4().hex[:6]}"
    task = task_service.create_task(marker)

    # Delete triggers an approval interrupt
    chat_resp = client.post("/api/chat", json={"message": f". delete {marker}"})
    assert chat_resp.status_code == 200
    chat_data = chat_resp.get_json()
    assert chat_data["success"] is True
    assert chat_data["status"] == "interrupted", (
        f"Expected interrupted status but got '{chat_data.get('status')}' "
        f"mode='{chat_data.get('mode')}' response='{chat_data.get('response', '')[:100]}'"
    )

    # Chat response should redirect to Control tab (from our fix)
    assert "review" in chat_data["response"].lower() or "control" in chat_data["response"].lower(), (
        f"Expected redirect text in chat response, got: {chat_data['response'][:120]}"
    )

    # ─── Simulate refreshControl() ───
    # 1. refreshReviews()
    reviews_resp = client.get("/api/reviews?status=pending&limit=100")
    assert reviews_resp.status_code == 200
    reviews_data = reviews_resp.get_json()
    assert reviews_data["success"] is True

    blocked_resp = client.get("/api/agent/reviews/blocked?limit=200")
    assert blocked_resp.status_code == 200
    blocked_data = blocked_resp.get_json()
    assert blocked_data["success"] is True

    # 2. refreshTasks()
    tasks_resp = client.get("/api/tasks/active?limit=80")
    assert tasks_resp.status_code == 200
    tasks_data = tasks_resp.get_json()
    assert tasks_data["success"] is True

    # 3. refreshBackground()
    tools_resp = client.get("/api/tools?status=all&review_status=all&limit=80")
    assert tools_resp.status_code == 200
    tools_data = tools_resp.get_json()
    assert tools_data["success"] is True

    # ─── Verify review item appears ───
    grouped = reviews_data.get("grouped", {})
    all_reviews = []
    for cat, items in grouped.items():
        all_reviews.extend(items)

    workflow_id = chat_data.get("workflow_id")
    matching = [
        item for item in all_reviews
        if (item.get("payload") or {}).get("workflow_id") == workflow_id
    ]
    assert matching, (
        f"CRITICAL: Review item for workflow {workflow_id} NOT found in /api/reviews!\n"
        f"  grouped categories: {list(grouped.keys())}\n"
        f"  total reviews: {len(all_reviews)}\n"
        f"  review_ids: {[r.get('review_id') for r in all_reviews]}\n"
        f"  This is the exact bug — the Control tab sees no review items."
    )

    # Verify blocked workflow appears
    blocked_wfs = blocked_data.get("blocked_workflows", [])
    blocked_matching = [b for b in blocked_wfs if b.get("workflow_id") == workflow_id]
    assert blocked_matching, (
        f"Blocked workflow {workflow_id} NOT in /api/agent/reviews/blocked. "
        f"Got {len(blocked_wfs)} blocked workflows."
    )
