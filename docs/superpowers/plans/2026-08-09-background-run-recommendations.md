# Background Run Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate recommendations from the final assistant output in a non-blocking background task, persist them per run, and display them live and after reload while preserving legacy event compatibility.

**Architecture:** Agent nodes schedule recommendation work only after capturing `output_text`. Presenter/storage APIs atomically persist a bounded run field and publish an authenticated WebSocket notification; trace reads synthesize the legacy event contract when required. The frontend routes WebSocket recommendations to the assistant message identified by `run_id`.

**Tech Stack:** Python 3.12, asyncio, FastAPI infrastructure, MongoDB/Motor, Redis-routed WebSocket delivery, React 19, TypeScript, Vitest, pytest.

## Global Constraints

- Work in the current branch; do not create a worktree or sub-agent.
- Follow strict red-green-refactor TDD.
- Recommendation generation must not block the main agent run.
- Include the final `output_text` in recommendation generation.
- Keep old `recommend:questions` and `followup:questions` history readable.
- Keep recommendation payloads bounded to three non-empty strings.

---

### Task 1: Run-level recommendation persistence and compatibility reads

**Files:**
- Modify: `src/infra/session/trace_storage.py`
- Modify: `src/infra/session/dual_writer.py`
- Test: `tests/infra/session/test_trace_storage_lifecycle.py`
- Test: `tests/infra/session/test_trace_storage_recommendations.py`

**Interfaces:**
- Produces: `TraceStorage.set_run_recommend_questions(session_id: str, run_id: str, questions: list[str]) -> bool`.
- Produces: `DualEventWriter.set_run_recommend_questions(...) -> bool`.
- Produces: session history events that synthesize `recommend:questions` only when no legacy recommendation event exists.

- [x] Write failing tests for bounded atomic persistence, synthetic compatibility events, and legacy-event deduplication.
- [x] Run the focused pytest files and confirm failures are caused by missing behavior.
- [x] Implement normalization, indexed update, projections, run summaries, and compatibility event synthesis.
- [x] Re-run the focused tests until green.

### Task 2: Final-output background scheduling and WebSocket publication

**Files:**
- Modify: `src/agents/core/recommendations.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `src/infra/writer/present.py`
- Test: `tests/agents/core/test_recommendation_node.py`
- Test: `tests/agents/test_disabled_skills_config_propagation.py`
- Test: `tests/infra/test_presenter_token_usage.py`

**Interfaces:**
- Produces: `Presenter.publish_recommend_questions(questions)`, which persists the run field then sends `recommend:questions` through the existing distributed WebSocket manager.
- Changes: `schedule_recommend_questions_from_state(..., output_text)` schedules one tracked background coroutine after agent streaming finishes.

- [x] Write failing tests proving the scheduler receives final output, returns before generation completes, persists questions, and sends the exact WebSocket payload.
- [x] Run the focused pytest tests and confirm expected red failures.
- [x] Implement presenter publication and collapse nested background scheduling into one tracked task.
- [x] Move all three agent-node scheduling calls after final output capture and pass `output_text`.
- [x] Re-run focused backend tests until green.

### Task 3: Frontend WebSocket recognition and run-based rendering

**Files:**
- Modify: `frontend/src/hooks/useWebSocket.ts`
- Modify: `frontend/src/hooks/useAgent.ts`
- Modify: `frontend/src/hooks/useAgent/types.ts`
- Modify: `frontend/src/components/layout/AppContent/useWebSocketNotifications.tsx`
- Modify: `frontend/src/components/layout/AppContent/ChatAppContent.tsx`
- Create: `frontend/src/hooks/useAgent/__tests__/recommendQuestionsUpdate.test.ts`
- Modify: relevant existing WebSocket tests.

**Interfaces:**
- Produces: `RecommendQuestionsNotification` and `onRecommendQuestions` WebSocket callback.
- Produces: `UseAgentReturn.applyRecommendQuestions(runId, questions)` with idempotent part replacement.

- [x] Write failing Vitest tests for WebSocket dispatch, session filtering, run targeting, and duplicate replacement.
- [x] Run focused Vitest tests and confirm expected red failures.
- [x] Implement the typed callback and pure run-based message updater, then wire it through `ChatAppContent`.
- [x] Re-run focused frontend tests until green.

### Task 4: Cross-stack verification and review

**Files:**
- Review all files changed by Tasks 1-3.

**Interfaces:**
- Consumes all prior behavior; produces verified delivery.

- [x] Run focused backend recommendation, trace-storage, presenter, and agent-node tests.
- [x] Run focused frontend WebSocket, history-loader, and event-processor tests.
- [x] Run Ruff on changed Python files and frontend lint/build/type verification in proportion to the changes.
- [x] Inspect `git diff --check`, the complete diff, compatibility behavior, background-task lifecycle, and failure isolation.
- [x] Record any environment-limited verification explicitly; otherwise mark the goal complete only with fresh passing evidence.
