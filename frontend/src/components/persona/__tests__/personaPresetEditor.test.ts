import test from "node:test";
import assert from "node:assert/strict";

import { buildPersonaPresetPayload } from "../personaPresetEditor.ts";
import type { PersonaPreset } from "../../../types";

const draft = {
  name: "Planner",
  description: "Plan carefully",
  avatar: "",
  system_prompt: "Plan first.",
  tags: ["planning"],
  skill_names: ["planner"],
};

test("builds published global payload for new official preset", () => {
  assert.deepEqual(
    buildPersonaPresetPayload(null, draft, {
      scope: "global",
      status: "published",
    }),
    {
      ...draft,
      avatar: null,
      scope: "global",
      visibility: "public",
      status: "published",
    },
  );
});

test("builds draft private payload for new user preset", () => {
  assert.deepEqual(
    buildPersonaPresetPayload(null, draft, {
      scope: "user",
      status: "published",
    }),
    {
      ...draft,
      avatar: null,
      scope: "user",
      visibility: "private",
      status: "draft",
    },
  );
});

test("preserves user preset updates without admin-only fields", () => {
  const preset = {
    id: "preset-1",
    scope: "user",
    name: "Mine",
    description: "",
    tags: [],
    system_prompt: "Hi",
    skill_names: [],
    visibility: "private",
    status: "draft",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } satisfies PersonaPreset;

  assert.deepEqual(
    buildPersonaPresetPayload(preset, draft, {
      scope: "user",
      status: "published",
    }),
    { ...draft, avatar: null },
  );
});

test("includes status when updating an official preset", () => {
  const preset = {
    id: "preset-2",
    scope: "global",
    name: "Official",
    description: "",
    tags: [],
    system_prompt: "Hi",
    skill_names: [],
    visibility: "public",
    status: "draft",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } satisfies PersonaPreset;

  assert.deepEqual(
    buildPersonaPresetPayload(preset, draft, {
      scope: "global",
      status: "published",
    }),
    {
      ...draft,
      avatar: null,
      visibility: "public",
      status: "published",
    },
  );
});
