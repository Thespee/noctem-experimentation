# Noctem v0.7.0 Self-Improvement Engine Implementation
## Overview
Implement a self-improvement engine that learns from execution logs, identifies patterns, and generates actionable recommendations. Built on v0.6.1's execution logging infrastructure.
## Current State
v0.6.1 provides:
* `execution_logs` table with trace_id, stage, component, confidence, duration
* `ExecutionLogger` class for pipeline tracing
* `model_registry` for model discovery/benchmarking
* `maintenance_insights` for storing recommendations
* Fast path capture with thoughts table
* Slow mode loop for background processing
## Implementation Plan
### Phase 1: Enhanced Execution Traces (Priority 1)
**Goal:** Complete trace coverage for thought → classification → action → resolution with project linking.
**Files to create:**
* `noctem/logging/trace_analyzer.py` - Helper functions for querying/analyzing traces
**Files to modify:**
* `noctem/slow/task_analyzer.py` - Add ExecutionLogger traces
* `noctem/slow/project_analyzer.py` - Add ExecutionLogger traces
* `noctem/fast/capture.py` - Enhance existing traces with more metadata
* `noctem/butler/clarifications.py` - Add traces for clarification outcomes
**Database changes:**
* Add `project_id` column to execution_logs (optional, NULL allowed)
**Key implementation details:**
* Every slow skill invocation should create a trace
* Link traces to projects via execution_logs.metadata JSON field initially
* Track time-to-resolution for clarifications
* Store model decisions (which model was selected and why)
### Phase 2: Slow System Logging (Priority 2)
**Goal:** Extend logging to all slow skills with decision tracking.
**Files to modify:**
* `noctem/slow/task_analyzer.py` - Log analysis decisions, model used, confidence
* `noctem/slow/project_analyzer.py` - Log next-action decisions
* `noctem/butler/protocol.py` - Log Butler contact decisions
**New trace metadata to capture:**
* Slow skill decisions: which suggestion was chosen, alternatives considered
* Clarification outcomes: user response, resolution time, whether it helped
* Model performance: tokens/sec, quality of output, whether suggestion was useful
* Suggestion acceptance: did user act on suggestion, skip it, or modify it?
### Phase 3: Log Review Skill (Priority 3)
**Goal:** Periodic analysis of logs to identify patterns and improvement opportunities.
**Files to create:**
* `noctem/slow/log_review.py` - Main log review skill
* `noctem/slow/pattern_detection.py` - Pattern detection algorithms
**Core analysis functions:**
* `analyze_classification_accuracy()` - Compare fast classifier decisions to user corrections
* `detect_recurring_ambiguities()` - Find phrases/patterns that often need clarification
* `analyze_extraction_failures()` - Identify date/time/priority parsing failures
* `analyze_user_corrections()` - Weight heavily: summon corrections, task amendments
* `analyze_model_performance()` - Compare models on same task types
* `detect_stale_suggestions()` - Find projects with ignored suggestions
**Pattern detection:**
* Recurring words/phrases in ambiguous thoughts (>3 occurrences)
* Time expressions that fail to parse ("soon", "later", "this weekend")
* Tasks often created then immediately modified (medium confidence <0.8)
* Clarification questions that users don't respond to (low value questions)
* Model selection patterns (faster model good enough vs. need bigger model)
**Integration with slow work queue:**
* Add `WorkType.LOG_REVIEW` to queue
* Schedule: weekly, or after N new thoughts processed (N=50)
* Lower priority than task/project analysis
### Phase 4: Improvement Suggestions (Priority 4)
**Goal:** Generate actionable recommendations from pattern analysis.
**Files to create:**
* `noctem/slow/improvement_engine.py` - Main improvement suggestion generator
* `noctem/services/insight_service.py` - CRUD for maintenance_insights
**Recommendation types:**
* **Keyword rules:** "Add 'dentist appointment' → high importance" (pattern: user often changes importance)
* **Ambiguity rules:** "Flag 'work on X' as scope ambiguity" (pattern: often needs clarification)
* **Time expression mappings:** "'this weekend' → Saturday 9am" (pattern: user's weekend preferences)
* **Model switching:** "Use qwen2.5:14b for project planning" (pattern: better quality, worth slowdown)
* **Butler timing:** "User responds fastest at 7pm" (pattern: response time analysis)
* **Confidence thresholds:** "Lower threshold to 0.7 for tasks with deadlines" (pattern: high-urgency tasks need less perfection)
**Insight priority scoring:**
* Frequency: How often does this pattern occur? (>5 times = high priority)
* Impact: How much user friction does this cause? (corrections = high impact)
* Confidence: How certain are we about this pattern? (>80% = confident)
* Actionability: Can this be auto-applied or needs user approval?
**Surface via Butler:**
* Format: "💡 **System Insight** - [title]. [1-sentence explanation]. [Proposed action]. Reply 'apply' to accept or 'dismiss' to ignore."
* Delivery: Via maintenance report (existing v0.6.1 infrastructure)
* Tracking: Store in maintenance_insights, update status on user response
### Phase 5: Testing Infrastructure
**Files to create:**
* `tests/test_v070_traces.py` - Test enhanced trace coverage
* `tests/test_v070_log_review.py` - Test pattern detection
* `tests/test_v070_improvements.py` - Test suggestion generation
* `tests/test_v070_integration.py` - End-to-end improvement flow
**Test scenarios:**
* Trace coverage: every path creates trace (fast, slow, butler, summon)
* Pattern detection: given N similar ambiguous thoughts, detect pattern
* User corrections: summon correction creates weighted pattern
* Suggestion generation: patterns → insights with correct priority
* Insight application: accepting insight updates classifier rules
* JSONL export: execution logs can be exported for audit/replay
**Test data fixtures:**
* 50 thoughts with recurring ambiguity patterns
* 20 user corrections via /summon
* 10 tasks with low confidence that user amended
* Execution traces for multiple models on same tasks
### Phase 6: Documentation & Manual Updates
**Files to modify:**
* `docs/improvements.md` - Mark v0.7.0 items as done, add learnings section
* `docs/USER_GUIDE.md` - Document new features, log review status, insights
* `README.md` - Update feature list with self-improvement engine
**New user-facing features:**
* System learns from corrections and suggests improvements
* Log review runs weekly (or `maintenance scan --logs`)
* Insights surfaced via Butler reports
* CLI: `noctem insights` to view pending suggestions
## Database Schema Changes
```SQL
-- Optional: Add project linking to execution logs
ALTER TABLE execution_logs ADD COLUMN project_id INTEGER REFERENCES projects(id);
-- Pattern tracking table (stores detected patterns before becoming insights)
CREATE TABLE IF NOT EXISTS detected_patterns (
    id INTEGER PRIMARY KEY,
    pattern_type TEXT,        -- 'ambiguity', 'extraction_failure', 'correction', 'model_perf'
    pattern_key TEXT,         -- Unique identifier (e.g., 'phrase:work on X')
    occurrence_count INTEGER DEFAULT 1,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    context TEXT,             -- JSON: example traces, metadata
    confidence REAL,          -- 0.0-1.0 how confident we are in this pattern
    status TEXT DEFAULT 'pending',  -- 'pending', 'promoted_to_insight', 'dismissed'
    UNIQUE(pattern_type, pattern_key)
);
CREATE INDEX IF NOT EXISTS idx_patterns_status ON detected_patterns(status, occurrence_count);
```
## Implementation Order
1. Enhanced traces in slow skills (1-2 hours)
2. Trace analyzer helper functions (1 hour)
3. Pattern detection algorithms (2-3 hours)
4. Log review skill (2 hours)
5. Improvement suggestion engine (2-3 hours)
6. Testing infrastructure (3-4 hours)
7. Documentation updates (1 hour)
8. Integration testing & bug fixes (2-3 hours)
**Total estimate:** 14-19 hours
## Success Criteria
* ✅ All slow skills create execution traces
* ✅ Pattern detection identifies >80% of recurring issues (validated with test data)
* ✅ Log review skill runs automatically weekly
* ✅ Insights generated have actionable recommendations
* ✅ User can accept/dismiss insights via Butler
* ✅ Execution logs can be exported to JSONL for audit
* ✅ All tests pass (target: 450+ tests)
* ✅ Documentation updated with learnings
## Questions & Decisions
1. **JSONL export:** Defer to future or implement now? **Decision:** Create export function but make it optional CLI command.
2. **Auto-apply insights:** Should some low-risk insights auto-apply? **Decision:** No, all insights require user approval for v0.7.0.
3. **Pattern confidence threshold:** When to promote pattern → insight? **Decision:** occurrence_count >= 5 AND confidence >= 0.7.
4. **Storage duration:** How long to keep execution logs? **Decision:** Keep all logs, add optional cleanup command for later.
## Risks & Mitigations
* **Risk:** Pattern detection generates too many false positives → **Mitigation:** High confidence thresholds, require multiple occurrences
* **Risk:** Execution logging overhead slows system → **Mitigation:** Async logging, batch inserts, monitoring in tests
* **Risk:** Insights overwhelming user → **Mitigation:** Priority scoring, max 3 insights per Butler report
* **Risk:** Test data not representative → **Mitigation:** Use real-world scenarios from improvements.md examples
