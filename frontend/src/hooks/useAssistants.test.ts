import assert from "node:assert/strict";
import test from "node:test";

import {
  EMPTY_ASSISTANT_TAGS,
  coerceAssistantList,
  getAssistantTagsKey,
  normalizeAssistantTags,
} from "./useAssistants.ts";

test("coerces null assistant responses into an empty list", () => {
  assert.deepEqual(coerceAssistantList(null), []);
  assert.deepEqual(coerceAssistantList(undefined), []);
  assert.deepEqual(coerceAssistantList({}), []);
});

test("preserves valid assistant arrays", () => {
  const items = [
    {
      assistant_id: "assistant-1",
      name: "Writer",
      description: "",
      system_prompt: "prompt",
      scope: "public",
      is_active: true,
      tags: [],
      version: "1.0.0",
      bound_skill_names: [],
      default_agent_options: {},
      default_disabled_tools: [],
      default_disabled_skills: [],
    },
  ];

  assert.equal(coerceAssistantList(items), items);
});

test("reuses a shared empty tags array when filters are omitted", () => {
  assert.equal(normalizeAssistantTags(undefined), EMPTY_ASSISTANT_TAGS);
  assert.equal(normalizeAssistantTags([]), EMPTY_ASSISTANT_TAGS);
});

test("generates the same tags key for equivalent arrays", () => {
  assert.equal(getAssistantTagsKey(undefined), "");
  assert.equal(getAssistantTagsKey([]), "");
  assert.equal(
    getAssistantTagsKey(["creative", "writer"]),
    getAssistantTagsKey(["creative", "writer"]),
  );
});
