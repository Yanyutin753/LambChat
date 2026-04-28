import assert from "node:assert/strict";
import test from "node:test";

import {
  getAssistantIndicatorName,
  getRestoredAssistantSelection,
  hasActiveAssistantSelection,
} from "./assistantState.ts";

test("restores assistant selection from session metadata", () => {
  assert.deepEqual(
    getRestoredAssistantSelection({
      assistant_id: "assistant-1",
      assistant_name: "Planner",
      assistant_prompt_snapshot: "You are a planner.",
    }),
    {
      assistantId: "assistant-1",
      assistantName: "Planner",
      assistantPromptSnapshot: "You are a planner.",
    },
  );
});

test("falls back to empty assistant selection when metadata is missing", () => {
  assert.deepEqual(getRestoredAssistantSelection({}), {
    assistantId: "",
    assistantName: "",
    assistantPromptSnapshot: "",
  });
});

test("detects when an assistant selection is active", () => {
  assert.equal(
    hasActiveAssistantSelection({
      assistantId: "assistant-1",
      assistantPromptSnapshot: "prompt",
    }),
    true,
  );
  assert.equal(
    hasActiveAssistantSelection({
      assistantId: "",
      assistantPromptSnapshot: "",
    }),
    false,
  );
});

test("builds a stable indicator name from assistant name or id", () => {
  assert.equal(
    getAssistantIndicatorName({
      assistantId: "assistant-1",
      assistantName: "Planner",
    }),
    "Planner",
  );
  assert.equal(
    getAssistantIndicatorName({
      assistantId: "assistant-1",
      assistantName: "",
    }),
    "assistant-1",
  );
});
