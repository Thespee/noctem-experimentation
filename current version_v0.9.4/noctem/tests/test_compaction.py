"""Tests for agent/compaction.py — deterministic fact extraction, merge, format, store."""
import pytest

from ..agent.compaction import (
    extract_facts,
    format_compaction_header,
    get_recent_compactions,
    merge_compaction_facts,
    store_compaction,
)


class TestExtractFacts:
    def test_extracts_task_mention(self):
        lines = ["task: 'Buy groceries' (high priority)"]
        facts = extract_facts(lines)
        assert any(f["type"] == "task_mention" for f in facts)

    def test_extracts_decision(self):
        lines = ["We decided to use Flask for the backend."]
        facts = extract_facts(lines)
        assert any(f["type"] == "decision" for f in facts)

    def test_extracts_due_date(self):
        lines = ["This is due 2025-12-01"]
        facts = extract_facts(lines)
        assert any(f["type"] == "due_date" for f in facts)

    def test_extracts_project_ref(self):
        lines = ["project 'Noctem' is progressing well."]
        facts = extract_facts(lines)
        assert any(f["type"] == "project_ref" for f in facts)

    def test_extracts_status_change(self):
        lines = ["completed: deploy the v0.9.4 release."]
        facts = extract_facts(lines)
        assert any(f["type"] == "status_change" for f in facts)

    def test_deduplicates_facts(self):
        lines = [
            "task: 'Buy groceries' (today)",
            "task: 'Buy groceries' (repeat)",
        ]
        facts = extract_facts(lines)
        task_mentions = [f for f in facts if f["type"] == "task_mention" and "Buy groceries" in f["value"]]
        assert len(task_mentions) == 1

    def test_empty_lines_produce_no_facts(self):
        assert extract_facts([]) == []
        assert extract_facts(["", "  ", None]) == []


class TestMergeCompactionFacts:
    def test_merges_and_deduplicates(self):
        records = [
            {"facts": [{"type": "decision", "value": "Use Flask"}]},
            {"facts": [{"type": "decision", "value": "Use Flask"}, {"type": "due_date", "value": "2025-12-01"}]},
        ]
        merged = merge_compaction_facts(records)
        assert len(merged) == 2

    def test_handles_string_facts(self):
        import json
        records = [
            {"facts": json.dumps([{"type": "decision", "value": "test"}])},
        ]
        merged = merge_compaction_facts(records)
        assert len(merged) == 1

    def test_handles_missing_facts(self):
        records = [{"facts": None}, {}]
        merged = merge_compaction_facts(records)
        assert merged == []


class TestFormatCompactionHeader:
    def test_format_with_facts(self):
        facts = [
            {"type": "task_mention", "value": "Buy groceries"},
            {"type": "decision", "value": "Use Flask"},
        ]
        header = format_compaction_header(facts)
        assert "[Compacted context summary]" in header
        assert "Buy groceries" in header
        assert "Use Flask" in header

    def test_format_empty_facts(self):
        header = format_compaction_header([])
        assert "compacted" in header.lower()

    def test_truncates_at_15_facts(self):
        facts = [{"type": "note", "value": f"fact {i}"} for i in range(20)]
        header = format_compaction_header(facts)
        # Should only include up to 15 bullet points
        assert header.count("•") <= 15


class TestStoreAndGetCompactions:
    def test_store_and_get(self):
        facts = [{"type": "decision", "value": "Test store"}]
        compaction_id = store_compaction("thread-test-1", ["dropped line 1"], facts)
        assert compaction_id > 0

        records = get_recent_compactions("thread-test-1", limit=5)
        assert len(records) >= 1
        latest = records[0]
        assert latest["thread_id"] == "thread-test-1"
        assert latest["dropped_line_count"] == 1
        assert len(latest["facts"]) == 1
        assert latest["facts"][0]["value"] == "Test store"

    def test_get_empty_thread(self):
        records = get_recent_compactions("nonexistent-thread", limit=5)
        assert records == []
