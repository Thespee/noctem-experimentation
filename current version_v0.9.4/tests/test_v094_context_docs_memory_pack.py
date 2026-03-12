"""v0.9.4 context docs and memory-pack assembly tests."""

from uuid import uuid4

from noctem.agent.memory_pack import (
    CONTEXT_DOCS_BUDGET,
    RECENT_CHATS_BUDGET,
    RECENT_COMMITS_BUDGET,
    WIKI_CONTEXT_BUDGET,
    assemble_memory_pack,
)
from noctem.mcp import get_mcp_server
from noctem.services.conversation_service import record_message
from noctem.services.object_context_docs import (
    get_object_context_doc,
    has_stale_context_docs,
    list_stale_object_ids,
    synthesize_object_context_doc,
    synthesize_stale_context_docs,
)
from noctem.db import get_db


def _create_task_via_mcp(name: str) -> int:
    mcp_server = get_mcp_server()
    result = mcp_server.call_tool(
        "tasks.create",
        {"name": name},
        context={"source": "test.context_docs"},
    )
    assert result.get("ok") is True
    task_payload = result["result"]["task"]
    return int(task_payload["id"])


def test_object_context_doc_can_be_synthesized_from_object_history():
    marker = f"context-doc-{uuid4().hex[:8]}"
    task_id = _create_task_via_mcp(marker)
    object_id = f"task:{task_id}"

    doc = synthesize_object_context_doc(object_id)
    assert doc is not None
    assert doc["object_id"] == object_id
    assert doc["object_type"] == "task"
    assert isinstance(doc["context_json"], dict)
    assert doc["context_json"]["current_snapshot"]["id"] == task_id
    assert marker in (doc["summary"] or "")

    persisted = get_object_context_doc(object_id)
    assert persisted is not None
    assert persisted["object_id"] == object_id
    assert persisted["markdown"]


def test_stale_context_doc_batch_generation_reports_results():
    marker = f"stale-doc-{uuid4().hex[:8]}"
    _create_task_via_mcp(marker)

    assert has_stale_context_docs() is True
    result = synthesize_stale_context_docs(max_items=10)
    assert result["checked_count"] >= 1
    assert result["generated_count"] >= 1
    assert isinstance(result["generated_object_ids"], list)


def test_stale_context_doc_detection_is_change_driven_not_age_driven():
    marker = f"stale-age-check-{uuid4().hex[:8]}"
    task_id = _create_task_via_mcp(marker)
    object_id = f"task:{task_id}"
    stored = synthesize_object_context_doc(object_id)
    assert stored is not None

    with get_db() as conn:
        conn.execute(
            """
            UPDATE object_context_docs
            SET generated_at = ?
            WHERE object_id = ?
            """,
            ("2000-01-02T00:00:00Z", object_id),
        )
        conn.execute(
            """
            UPDATE objects
            SET created_at = ?, updated_at = ?
            WHERE object_id = ?
            """,
            ("2000-01-01T00:00:00Z", "2000-01-01T00:00:00Z", object_id),
        )

    stale_ids = set(list_stale_object_ids(limit=200))
    assert object_id not in stale_ids


def test_memory_pack_uses_fixed_budget_buckets():
    marker = f"memory-pack-{uuid4().hex[:8]}"
    thread_id = f"thread-{uuid4().hex[:8]}"
    task_id = _create_task_via_mcp(marker)
    synthesize_object_context_doc(f"task:{task_id}")

    record_message(
        content=f"Please remember {marker}",
        role="user",
        source="web",
        session_id=thread_id,
    )
    record_message(
        content=f"I captured task {marker}.",
        role="assistant",
        source="web",
        session_id=thread_id,
    )

    pack = assemble_memory_pack(query_text=f"What is {marker}?", thread_id=thread_id)
    assert isinstance(pack, dict)
    assert pack["budget"]["recent_chats"] == RECENT_CHATS_BUDGET
    assert pack["budget"]["recent_commits"] == RECENT_COMMITS_BUDGET
    assert pack["budget"]["context_docs"] == CONTEXT_DOCS_BUDGET
    assert pack["budget"]["wiki"] == WIKI_CONTEXT_BUDGET

    usage = pack["token_usage"]
    assert usage["recent_chats"] <= RECENT_CHATS_BUDGET
    assert usage["recent_commits"] <= RECENT_COMMITS_BUDGET
    assert usage["context_docs"] <= CONTEXT_DOCS_BUDGET
    assert usage["wiki"] <= WIKI_CONTEXT_BUDGET
    assert pack["total_tokens"] == sum(usage.values())
    assert marker in (pack["sections"]["recent_chats"] or "")
