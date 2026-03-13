"""Tests for v0.9.3 Phase 2 agent workflow scaffolding."""
from datetime import date, timedelta
from uuid import uuid4
from noctem.db import get_db, init_db
from noctem.agent.router import IntentType, classify_intent
from noctem.agent.bulk_edit_parser import parse_bulk_edit_request, should_use_model_parser
from noctem.services import task_service, project_service
from noctem.config import Config


def _client():
    from noctem.web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_agent_submit_creates_task():
    client = _client()
    resp = client.post("/api/agent/submit", json={"input": "buy milk tomorrow"})
    assert resp.status_code == 200

    data = resp.get_json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert isinstance(data["workflow_id"], int)
    assert data.get("task")
    assert task_service.get_task(data["task"]["id"]) is not None


def test_agent_status_returns_workflow_and_actions():
    client = _client()
    submit = client.post("/api/agent/submit", json={"input": "call mom friday"})
    workflow_id = submit.get_json()["workflow_id"]

    resp = client.get(f"/api/agent/status/{workflow_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["workflow"]["id"] == workflow_id
    assert len(data["actions"]) >= 2


def test_agent_interrupt_and_resume_flow():
    client = _client()

    # Non-alphanumeric text forces a clarification interrupt in v0.9.3 workflow
    resp = client.post("/api/agent/submit", json={"input": "!!!"})
    assert resp.status_code == 200
    first = resp.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"
    assert first["interrupt"]["id"] is not None

    resume = client.post(
        f"/api/agent/resume/{first['workflow_id']}",
        json={"response": "email team tomorrow 9am"},
    )
    assert resume.status_code == 200
    resumed = resume.get_json()
    assert resumed["success"] is True
    assert resumed["status"] == "completed"
    assert resumed.get("task")

def test_chat_auto_resumes_clarify_interrupt_with_followup_text():
    client = _client()
    marker = f"clarify-resume-{uuid4().hex[:8]}"

    first = client.post("/api/chat", json={"message": ". !!!"})
    assert first.status_code == 200
    first_data = first.get_json()
    assert first_data["success"] is True
    assert first_data["status"] == "interrupted"
    assert isinstance(first_data.get("workflow_id"), int)
    assert first_data.get("thread_id")

    second = client.post(
        "/api/chat",
        json={
            "message": f"buy {marker} tomorrow",
            "thread_id": first_data.get("thread_id"),
        },
    )
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["success"] is True
    assert second_data["mode"] == "resume"
    assert second_data["workflow_id"] == first_data["workflow_id"]
    assert second_data["status"] == "completed"

    active = task_service.get_all_tasks(include_done=False)
    assert any(marker in t.name.lower() for t in active)


def test_chat_model_progress_callback_emits_start_and_completion(monkeypatch):
    events: list[dict] = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": (
                    '{"reply":"All good.","requires_action":false,'
                    '"fast_path_input":null,"clarification_question":null,"memory_update":null}'
                )
            }

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    from noctem.agent.chat_orchestrator import process_chat_message

    result = process_chat_message(
        "hello there",
        source="web",
        thread_id=f"progress-{uuid4().hex[:8]}",
        progress_callback=events.append,
    )
    assert result["mode"] == "model"
    stages = [event.get("stage") for event in events if isinstance(event, dict)]
    assert "started" in stages
    assert "completed" in stages



def test_review_queue_endpoints_include_pending_interrupts():
    client = _client()
    submit = client.post("/api/agent/submit", json={"input": "!!!"})
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"

    review_list = client.get("/api/agent/reviews?status=pending")
    assert review_list.status_code == 200
    review_payload = review_list.get_json()
    assert review_payload["success"] is True
    assert isinstance(review_payload["reviews"], list)
    assert any(
        (item.get("payload") or {}).get("workflow_id") == first["workflow_id"]
        for item in review_payload["reviews"]
    )

    blocked = client.get("/api/agent/reviews/blocked")
    assert blocked.status_code == 200
    blocked_payload = blocked.get_json()
    assert blocked_payload["success"] is True
    assert any(item.get("workflow_id") == first["workflow_id"] for item in blocked_payload["blocked_workflows"])


def test_review_approve_endpoint_resumes_delete_workflow():
    client = _client()
    task = task_service.create_task(f"review-delete-{uuid4().hex[:8]}")

    submit = client.post("/api/agent/submit", json={"input": f"delete {task.name}"})
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"
    review_id = (first.get("review") or {}).get("review_id") or (first.get("interrupt") or {}).get("review_id")
    assert review_id

    approve = client.post(
        f"/api/agent/reviews/{review_id}/approve",
        json={"response": "yes"},
    )
    assert approve.status_code == 200
    approve_payload = approve.get_json()
    assert approve_payload["success"] is True
    assert approve_payload["resume_result"] is not None
    assert approve_payload["resume_result"]["status"] == "completed"
    assert task_service.get_task(task.id) is None

    refreshed_review = approve_payload.get("review") or {}
    assert refreshed_review.get("status") in {"approved", "resolved"}


def test_review_resume_endpoint_completes_clarification_workflow():
    client = _client()
    marker = f"review-resume-{uuid4().hex[:8]}"

    submit = client.post("/api/agent/submit", json={"input": "!!!"})
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["status"] == "interrupted"
    review_id = (first.get("review") or {}).get("review_id") or (first.get("interrupt") or {}).get("review_id")
    assert review_id

    resume = client.post(
        f"/api/agent/reviews/{review_id}/resume",
        json={"response": f"buy {marker} tomorrow"},
    )
    assert resume.status_code == 200
    payload = resume.get_json()
    assert payload["success"] is True
    assert payload["resume_result"] is not None
    assert payload["resume_result"]["status"] == "completed"

    active = task_service.get_all_tasks(include_done=False)
    assert any(marker in t.name.lower() for t in active)


def test_chat_endpoint_uses_agent_workflow():
    client = _client()
    resp = client.post("/api/chat", json={"message": "done task-that-does-not-exist-xyz"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["workflow_id"], int)
    assert data["status"] in ("interrupted", "completed")
    assert data.get("thread_id")


def test_chat_dot_fast_path_handles_shorthand_done():
    client = _client()
    marker = f"dotfast-{uuid4().hex[:10]}"
    task = task_service.create_task(marker)

    resp = client.post("/api/chat", json={"message": f".d {marker}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["mode"] == "fast"
    assert isinstance(data["workflow_id"], int)

    refreshed = task_service.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == "done"

def test_chat_bare_command_bypasses_model_and_uses_fast_path(monkeypatch):
    client = _client()
    marker = f"barefast-{uuid4().hex[:10]}"
    task = task_service.create_task(marker)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Model call should not occur for bare command input.")

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", _fail_if_called)

    resp = client.post("/api/chat", json={"message": f"done {marker}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["mode"] == "fast"
    assert isinstance(data.get("workflow_id"), int)

    refreshed = task_service.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == "done"


def test_chat_double_dot_escape_uses_model_path(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": (
                    '{"reply":".noted","requires_action":false,'
                    '"fast_path_input":null,"clarification_question":null,"memory_update":null}'
                )
            }

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": "..hello alfred"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["mode"] == "model"
    assert data["response"].startswith(".")
    assert data.get("workflow_id") is None


def test_chat_model_payload_can_execute_action(monkeypatch):
    marker = f"model-action-{uuid4().hex[:8]}"

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": (
                    '{"reply":"On it.","requires_action":true,'
                    f'"fast_path_input":"buy {marker} tomorrow",'
                    '"clarification_question":null,"memory_update":null}'
                )
            }

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": f"please add buy {marker} tomorrow"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["mode"] == "model"
    assert isinstance(data["workflow_id"], int)
    assert data["status"] == "completed"

    active = task_service.get_all_tasks(include_done=False)
    assert any(marker in t.name.lower() for t in active)


def test_chat_streamed_model_payload_does_not_fallback_to_consumed_response(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            yield (
                '{"response":"{\\"reply\\":\\"streamed ok\\",\\"requires_action\\":false,'
                '\\"fast_path_input\\":null,\\"clarification_question\\":null,\\"memory_update\\":null}",'
                '"done":true}'
            )

        def json(self):
            raise RuntimeError("The content for this response was already consumed")

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": "hello streamed model"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["mode"] == "model"
    assert data.get("fallback_reason") is None
    assert "streamed ok" in str(data.get("response") or "").lower()


def test_chat_forces_grounded_query_execution_when_model_skips_action(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": (
                    '{"reply":"No tasks scheduled for today.","requires_action":false,'
                    '"fast_path_input":null,"clarification_question":null,"memory_update":null}'
                )
            }

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": "What do I have on for today?"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data.get("workflow_id"), int)
    assert data.get("intent") == IntentType.QUERY.value
    assert isinstance(data.get("intent_classifier"), str)


def test_chat_falls_back_to_deterministic_when_model_payload_invalid(monkeypatch):
    marker = f"fallback-{uuid4().hex[:8]}"

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "NOT_VALID_JSON"}

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": f"buy {marker} tomorrow"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["mode"] == "fallback_fast"
    assert isinstance(data["workflow_id"], int)
    assert data["status"] in ("completed", "interrupted")

    active = task_service.get_all_tasks(include_done=False)
    assert any(marker in t.name.lower() for t in active)


def test_chat_history_uses_server_thread_messages():
    client = _client()
    marker = f"history-{uuid4().hex[:8]}"

    first = client.post("/api/chat", json={"message": f". buy {marker} tomorrow"})
    assert first.status_code == 200
    first_data = first.get_json()
    assert first_data["success"] is True
    thread_id = first_data.get("thread_id")
    assert thread_id

    second = client.post("/api/chat", json={"message": f".d {marker}"})
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["success"] is True
    assert second_data.get("thread_id") == thread_id

    history = client.get("/api/chat/history")
    assert history.status_code == 200
    payload = history.get_json()
    assert payload.get("thread_id") == thread_id
    assert isinstance(payload.get("messages"), list)

    texts = [m.get("content", "") for m in payload["messages"]]
    assert any(marker in t for t in texts)


def test_settings_page_includes_chat_and_calendar_sections():
    client = _client()
    resp = client.get("/settings")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Alfred Chat" in html
    assert "Calendar Import" in html
    assert "chat_assistant_name" in html
    assert "chat_default_thread_id" in html


def test_settings_post_persists_chat_fields():
    client = _client()
    payload = {
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "timezone": "UTC",
        "morning_message_time": "07:00",
        "web_host": "0.0.0.0",
        "web_port": "5000",
        "chat_assistant_name": "AlfredPrime",
        "chat_default_thread_id": "alfred-shared",
        "chat_ollama_model": "qwen2.5:7b-instruct-q4_K_M",
        "chat_ollama_base_url": "http://localhost:11434",
        "chat_model_first_enabled": "on",
        "chat_unified_continuity": "on",
        "chat_brief_mode": "on",
    }
    resp = client.post("/settings", data=payload)
    assert resp.status_code in (301, 302, 303, 307, 308)

    Config.clear_cache()
    assert Config.get("chat_assistant_name") == "AlfredPrime"
    assert Config.get("chat_default_thread_id") == "alfred-shared"
    assert Config.get("chat_model_first_enabled") is True
    assert Config.get("chat_unified_continuity") is True
    assert Config.get("chat_brief_mode") is True


def test_settings_post_blank_telegram_fields_do_not_clear_existing_values():
    client = _client()
    Config.set("telegram_bot_token", "token-keep-me")
    Config.set("telegram_chat_id", "123456")
    Config.clear_cache()

    payload = {
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "timezone": "UTC",
        "web_host": "0.0.0.0",
        "web_port": "5000",
        "chat_assistant_name": "Alfred",
        "chat_default_thread_id": "alfred-main",
        "chat_ollama_model": "qwen2.5:7b-instruct-q4_K_M",
        "chat_ollama_base_url": "http://localhost:11434",
        "chat_model_first_enabled": "on",
        "chat_unified_continuity": "on",
        "chat_brief_mode": "on",
    }
    resp = client.post("/settings", data=payload)
    assert resp.status_code in (301, 302, 303, 307, 308)

    Config.clear_cache()
    assert Config.get("telegram_bot_token") == "token-keep-me"
    assert Config.get("telegram_chat_id") == "123456"


def test_calendar_action_can_redirect_to_settings_anchor():
    client = _client()
    resp = client.post("/calendar/clear", data={"next": "settings"})
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert "/settings#calendar-import" in (resp.headers.get("Location") or "")


def test_bulk_edit_moves_all_project_tasks_to_today():
    client = _client()
    home = project_service.create_project("Home Ops")
    other = project_service.create_project("Other")

    t1 = task_service.create_task("Water plants", project_id=home.id)
    t2 = task_service.create_task("Clean sink", project_id=home.id)
    t3 = task_service.create_task("Read docs", project_id=other.id)

    resp = client.post(
        "/api/agent/submit",
        json={"input": "move all tasks from Home Ops to today"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    if data["status"] == "interrupted":
        assert data["interrupt"]["type"] == "approve"
        resume = client.post(
            f"/api/agent/resume/{data['workflow_id']}",
            json={"response": "yes"},
        )
        assert resume.status_code == 200
        data = resume.get_json()
        assert data["success"] is True
    assert data["status"] == "completed"
    assert data["updated_count"] == 2

    updated_t1 = task_service.get_task(t1.id)
    updated_t2 = task_service.get_task(t2.id)
    unchanged_t3 = task_service.get_task(t3.id)
    assert updated_t1.due_date == date.today()
    assert updated_t2.due_date == date.today()
    assert unchanged_t3.due_date is None


def test_bulk_edit_moves_multiple_named_tasks_to_project():
    client = _client()
    target = project_service.create_project("Errands")
    t1 = task_service.create_task("Buy milk bulk-edit alpha")
    t2 = task_service.create_task("Call mom bulk-edit beta")
    t3 = task_service.create_task("Finish report")

    resp = client.post(
        "/api/agent/submit",
        json={"input": "move Buy milk bulk-edit alpha and Call mom bulk-edit beta to project Errands"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    if data["status"] == "interrupted":
        assert data["interrupt"]["type"] == "approve"
        resume = client.post(
            f"/api/agent/resume/{data['workflow_id']}",
            json={"response": "yes"},
        )
        assert resume.status_code == 200
        data = resume.get_json()
        assert data["success"] is True
    assert data["status"] == "completed"
    assert data["updated_count"] == 2

    moved_t1 = task_service.get_task(t1.id)
    moved_t2 = task_service.get_task(t2.id)
    unchanged_t3 = task_service.get_task(t3.id)
    assert moved_t1.project_id == target.id
    assert moved_t2.project_id == target.id
    assert unchanged_t3.project_id is None


def test_bulk_edit_handles_multiclause_delay_and_project_move():
    client = _client()
    interview = project_service.create_project("Interview bulk-edit multiclause")

    interview_due_today = task_service.create_task("Mock interview", project_id=interview.id, due_date=date.today())
    misc_due_today = task_service.create_task("Pay bill", due_date=date.today())
    interview_no_date = task_service.create_task("Research company", project_id=interview.id)

    resp = client.post(
        "/api/agent/submit",
        json={"input": "delay every thing from today ~ move everything in the interview bulk-edit multiclause project to today;"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    if data["status"] == "interrupted":
        assert data["interrupt"]["type"] == "approve"
        resume = client.post(
            f"/api/agent/resume/{data['workflow_id']}",
            json={"response": "yes"},
        )
        assert resume.status_code == 200
        data = resume.get_json()
        assert data["success"] is True
    assert data["status"] == "completed"
    assert data["updated_count"] >= 3

    t1 = task_service.get_task(interview_due_today.id)
    t2 = task_service.get_task(misc_due_today.id)
    t3 = task_service.get_task(interview_no_date.id)

    # Clause 1 moves all tasks due today to tomorrow; clause 2 moves interview tasks to today.
    assert t1.due_date == date.today()
    assert t2.due_date == date.today() + timedelta(days=1)
    assert t3.due_date == date.today()

def test_bulk_edit_moves_overdue_to_today_with_approval():
    client = _client()
    marker = uuid4().hex[:8]
    overdue_a = task_service.create_task(
        f"overdue-a-{marker}",
        due_date=date.today() - timedelta(days=2),
    )
    overdue_b = task_service.create_task(
        f"overdue-b-{marker}",
        due_date=date.today() - timedelta(days=1),
    )
    future = task_service.create_task(
        f"future-{marker}",
        due_date=date.today() + timedelta(days=2),
    )

    submit = client.post(
        "/api/agent/submit",
        json={"input": "move all overdue task to today"},
    )
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"
    assert first["interrupt"]["type"] == "approve"

    resume = client.post(
        f"/api/agent/resume/{first['workflow_id']}",
        json={"response": "yes"},
    )
    assert resume.status_code == 200
    final = resume.get_json()
    assert final["success"] is True
    assert final["status"] == "completed"
    assert final["updated_count"] >= 2

    refreshed_a = task_service.get_task(overdue_a.id)
    refreshed_b = task_service.get_task(overdue_b.id)
    refreshed_future = task_service.get_task(future.id)
    assert refreshed_a is not None and refreshed_a.due_date == date.today()
    assert refreshed_b is not None and refreshed_b.due_date == date.today()
    assert refreshed_future is not None and refreshed_future.due_date == date.today() + timedelta(days=2)

def test_query_returns_compact_overdue_list():
    client = _client()
    marker = f"overdue-list-{uuid4().hex[:8]}"
    task_service.create_task(
        marker,
        due_date=date.today() - timedelta(days=36500),
    )

    resp = client.post(
        "/api/agent/submit",
        json={"input": "can you tell me what those overdue task are?"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert "overdue task(s):" in data["response"].lower()
    assert marker in data["response"]

def test_chat_model_action_response_uses_grounded_workflow_result(monkeypatch):
    task_service.create_task(f"overdue-chat-a-{uuid4().hex[:6]}", due_date=date.today() - timedelta(days=2))
    task_service.create_task(f"overdue-chat-b-{uuid4().hex[:6]}", due_date=date.today() - timedelta(days=1))

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": (
                    "{\"reply\":\"Sure, moving all overdue tasks to today.\",\"requires_action\":true,"
                    "\"fast_path_input\":\"move all overdue task to today\","
                    "\"clarification_question\":null,\"memory_update\":null}"
                )
            }

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": "please move all overdue tasks to today"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["status"] == "interrupted"
    assert data["interrupt"]["type"] == "approve"
    assert "approve this update" in data["response"].lower()
    assert "sure, moving all overdue tasks to today." not in data["response"].lower()

def test_chat_auto_resumes_pending_bulk_approval(monkeypatch):
    marker = uuid4().hex[:8]
    overdue_a = task_service.create_task(
        f"resume-overdue-a-{marker}",
        due_date=date.today() - timedelta(days=2),
    )
    overdue_b = task_service.create_task(
        f"resume-overdue-b-{marker}",
        due_date=date.today() - timedelta(days=1),
    )

    class _FakeResponse:
        def __init__(self, payload: str):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return {"response": self._payload}

    payloads = [
        (
            "{\"reply\":\"Sure, moving all overdue tasks to today.\",\"requires_action\":true,"
            "\"fast_path_input\":\"move all overdue task to today\","
            "\"clarification_question\":null,\"memory_update\":null}"
        ),
        (
            "{\"reply\":\"yes\",\"requires_action\":false,"
            "\"fast_path_input\":null,\"clarification_question\":null,\"memory_update\":null}"
        ),
    ]
    call_count = {"value": 0}

    def _fake_post(*args, **kwargs):
        idx = min(call_count["value"], len(payloads) - 1)
        call_count["value"] += 1
        return _FakeResponse(payloads[idx])

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", _fake_post)

    client = _client()
    first = client.post("/api/chat", json={"message": "please move all overdue tasks to today"})
    assert first.status_code == 200
    first_data = first.get_json()
    assert first_data["success"] is True
    assert first_data["status"] == "interrupted"
    assert first_data["interrupt"]["type"] == "approve"
    assert isinstance(first_data.get("workflow_id"), int)

    second = client.post(
        "/api/chat",
        json={"message": "yes", "thread_id": first_data.get("thread_id")},
    )
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["success"] is True
    assert second_data["mode"] == "resume"
    assert second_data["status"] == "completed"
    assert second_data["workflow_id"] == first_data["workflow_id"]
    assert second_data["updated_count"] >= 2
    assert call_count["value"] == 1

    refreshed_a = task_service.get_task(overdue_a.id)
    refreshed_b = task_service.get_task(overdue_b.id)
    assert refreshed_a is not None and refreshed_a.due_date == date.today()
    assert refreshed_b is not None and refreshed_b.due_date == date.today()


def test_chat_forces_completed_prefix_to_execute_completion(monkeypatch):
    marker = f"completed-prefix-{uuid4().hex[:8]}"
    task = task_service.create_task(marker)

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": (
                    "{\"reply\":\"Paying rent completed.\",\"requires_action\":false,"
                    "\"fast_path_input\":null,\"clarification_question\":null,\"memory_update\":null}"
                )
            }

    monkeypatch.setattr("noctem.agent.chat_orchestrator.requests.post", lambda *args, **kwargs: _FakeResponse())

    client = _client()
    resp = client.post("/api/chat", json={"message": f"completed {marker}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data.get("workflow_id"), int)
    assert data["status"] == "completed"

    refreshed = task_service.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == "done"


def test_router_detects_bulk_edit_from_conversational_phrase():
    decision = classify_intent("could you delay every thing from today")
    assert decision.intent == IntentType.BULK_EDIT

def test_router_detects_completed_prefix_phrase():
    decision = classify_intent("completed paying rent")
    assert decision.intent == IntentType.COMPLETE_TASK


def test_bulk_edit_parser_extracts_overdue_scope():
    parsed = parse_bulk_edit_request("move all overdue task to today")
    assert parsed.scope_type == "overdue"
    assert parsed.target_due_date == date.today()

def test_router_detects_polite_delete_phrase():
    decision = classify_intent("can you delete the how's it going task from today?")
    assert decision.intent == IntentType.DELETE_TASK


def test_router_treats_question_mark_followup_as_query():
    decision = classify_intent("I still see it on the website; are you sure you deleted the correct task?")
    assert decision.intent == IntentType.QUERY


def test_model_parser_threshold_prefers_complex_inputs():
    assert should_use_model_parser("move water plant today") is False
    assert should_use_model_parser("delay every thing from today ~ move everything in the interview project to today") is True


def test_delete_requires_approval_then_deletes_on_yes():
    client = _client()
    task = task_service.create_task("delete-me-v093")

    submit = client.post("/api/agent/submit", json={"input": "delete delete-me-v093"})
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"
    assert first["interrupt"]["type"] == "approve"

    resume = client.post(
        f"/api/agent/resume/{first['workflow_id']}",
        json={"response": "yes"},
    )
    assert resume.status_code == 200
    final = resume.get_json()
    assert final["success"] is True
    assert final["status"] == "completed"
    assert final["deleted_task_id"] == task.id
    assert task_service.get_task(task.id) is None


def test_delete_cancelled_on_no():
    client = _client()
    task = task_service.create_task("keep-me-v093")

    submit = client.post("/api/agent/submit", json={"input": "delete keep-me-v093"})
    first = submit.get_json()
    assert first["status"] == "interrupted"

    resume = client.post(
        f"/api/agent/resume/{first['workflow_id']}",
        json={"response": "no"},
    )
    assert resume.status_code == 200
    final = resume.get_json()
    assert final["success"] is True
    assert final["status"] == "completed"
    assert "Canceled deletion" in final["response"]
    assert task_service.get_task(task.id) is not None


def test_polite_delete_phrase_resolves_target_and_requires_approval():
    client = _client()
    task = task_service.create_task("how's it going")

    submit = client.post(
        "/api/agent/submit",
        json={"input": "can you delete the how's it going task from today?"},
    )
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"
    assert first["interrupt"]["type"] == "approve"

    resume = client.post(
        f"/api/agent/resume/{first['workflow_id']}",
        json={"response": "yes"},
    )
    assert resume.status_code == 200
    final = resume.get_json()
    assert final["success"] is True
    assert final["status"] == "completed"
    assert final["deleted_task_id"] == task.id
    assert task_service.get_task(task.id) is None


def test_init_db_drops_legacy_runtime_tables():
    init_db()
    with get_db() as conn:
        table_names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    for legacy_table in (
        "butler_contacts",
        "slow_work_queue",
        "prompt_templates",
        "prompt_versions",
        "skills",
        "skill_executions",
        "feedback_sessions",
        "feedback_questions",
        "maintenance_insights",
    ):
        assert legacy_table not in table_names


def test_router_uses_ollama_classifier_when_enabled(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": "{\"intent\":\"query\",\"confidence\":0.88,\"reasoning\":\"model matched\"}"
            }

    def _fake_post(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setenv("NOCTEM_AGENT_INTENT_MODEL", "fake-local-model")
    monkeypatch.setattr("noctem.agent.router.requests.post", _fake_post)

    decision = classify_intent("please give me a status summary")
    assert decision.intent == IntentType.QUERY
    assert decision.classifier == "ollama:fake-local-model"
    assert decision.confidence == 0.88
