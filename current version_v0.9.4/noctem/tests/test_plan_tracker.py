"""Tests for agent/plan_tracker.py — plan CRUD, step lifecycle, failure halting."""
import pytest

from ..agent.plan_tracker import (
    approve_plan_step,
    complete_plan_step,
    create_plan_object,
    fail_plan_step,
    get_plan_status,
)


# We need a workflow row to satisfy the foreign key. Create a minimal one.
_workflow_counter = 0

def _ensure_workflow(conn) -> int:
    global _workflow_counter
    _workflow_counter += 1
    import uuid
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"
    conn.execute(
        """
        INSERT INTO agent_workflows (workflow_type, thread_id, status, current_node, input_text)
        VALUES ('test', ?, 'active', 'start', 'test input')
        """,
        (thread_id,),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return row[0]


class TestCreatePlan:
    def test_create_plan_with_steps(self):
        from ..db import get_db
        with get_db() as conn:
            wf_id = _ensure_workflow(conn)

        plan = create_plan_object(workflow_id=wf_id, steps=["Step A", "Step B", "Step C"])
        assert plan["plan_id"].startswith("plan-")
        assert plan["total_steps"] == 3
        assert plan["completed_steps"] == 0
        assert plan["status"] == "pending"
        assert len(plan["steps"]) == 3
        assert plan["steps"][0]["description"] == "Step A"
        assert plan["steps"][2]["step_index"] == 2

    def test_get_nonexistent_plan(self):
        status = get_plan_status("plan-doesnotexist")
        assert status["status"] == "not_found"
        assert status["steps"] == []


class TestStepLifecycle:
    def _create_test_plan(self, steps=None):
        from ..db import get_db
        with get_db() as conn:
            wf_id = _ensure_workflow(conn)
        return create_plan_object(workflow_id=wf_id, steps=steps or ["A", "B", "C"])

    def test_approve_step(self):
        plan = self._create_test_plan()
        step_id = plan["steps"][0]["id"]
        updated = approve_plan_step(step_id)
        assert updated is not None
        assert updated["status"] == "approved"

    def test_complete_step(self):
        plan = self._create_test_plan()
        step_id = plan["steps"][0]["id"]
        updated = complete_plan_step(step_id, result={"output": "done"})
        assert updated["status"] == "completed"
        assert updated["result"]["output"] == "done"

    def test_complete_all_steps_marks_plan_completed(self):
        plan = self._create_test_plan(["X", "Y"])
        for step in plan["steps"]:
            complete_plan_step(step["id"])
        status = get_plan_status(plan["plan_id"])
        assert status["status"] == "completed"
        assert status["completed_steps"] == 2


class TestFailureHalting:
    def _create_test_plan(self, steps=None):
        from ..db import get_db
        with get_db() as conn:
            wf_id = _ensure_workflow(conn)
        return create_plan_object(workflow_id=wf_id, steps=steps or ["A", "B", "C"])

    def test_fail_step_skips_remaining(self):
        plan = self._create_test_plan(["A", "B", "C"])
        first_id = plan["steps"][0]["id"]
        fail_plan_step(first_id, error="something broke")

        status = get_plan_status(plan["plan_id"])
        assert status["status"] == "failed"
        assert status["failed_steps"] == 1
        # B and C should be skipped
        assert status["steps"][1]["status"] == "skipped"
        assert status["steps"][2]["status"] == "skipped"

    def test_fail_last_step_no_skipping(self):
        plan = self._create_test_plan(["A", "B"])
        complete_plan_step(plan["steps"][0]["id"])
        fail_plan_step(plan["steps"][1]["id"], error="late fail")

        status = get_plan_status(plan["plan_id"])
        assert status["status"] == "failed"
        assert status["steps"][0]["status"] == "completed"
        assert status["steps"][1]["status"] == "failed"
