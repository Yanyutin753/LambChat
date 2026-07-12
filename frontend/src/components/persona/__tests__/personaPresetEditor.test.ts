import { buildPersonaPresetPayload } from "../personaPresetEditor.ts";
import type { PersonaPreset } from "../../../types";

const draft = {
  name: "Planner",
  description: "Plan carefully",
  avatar: "",
  system_prompt: "Plan first.",
  starter_prompts: [
    { icon: "🧭", text: "帮我拆解这个目标" },
    {
      icon: "",
      text: { zh: "先列一个执行计划", en: "Draft an execution plan" },
    },
  ],
  tags: ["planning"],
  skill_names: ["planner"],
};

test("builds published global payload for new official preset", () => {
  expect(
    buildPersonaPresetPayload(null, draft, {
      scope: "global",
      status: "published",
    }),
  ).toEqual({
    ...draft,
    avatar: null,
    scope: "global",
    visibility: "public",
    status: "published",
  });
});

test("builds draft private payload for new user preset", () => {
  expect(
    buildPersonaPresetPayload(null, draft, {
      scope: "user",
      status: "published",
    }),
  ).toEqual({
    ...draft,
    avatar: null,
    scope: "user",
    visibility: "private",
    status: "draft",
  });
});

test("preserves user preset updates without admin-only fields", () => {
  const preset = {
    id: "preset-1",
    scope: "user",
    name: "Mine",
    description: "",
    tags: [],
    system_prompt: "Hi",
    starter_prompts: [],
    skill_names: [],
    visibility: "private",
    status: "draft",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } satisfies PersonaPreset;

  expect(
    buildPersonaPresetPayload(preset, draft, {
      scope: "user",
      status: "published",
    }),
  ).toEqual({ ...draft, avatar: null });
});

test("includes public global fields when editing a user preset as official", () => {
  const preset = {
    id: "preset-1",
    scope: "user",
    name: "Mine",
    description: "",
    tags: [],
    system_prompt: "Hi",
    starter_prompts: [],
    skill_names: [],
    visibility: "private",
    status: "draft",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } satisfies PersonaPreset;

  expect(
    buildPersonaPresetPayload(preset, draft, {
      scope: "global",
      status: "published",
    }),
  ).toEqual({
    ...draft,
    avatar: null,
    scope: "global",
    visibility: "public",
    status: "published",
  });
});

test("includes private user fields when editing an official preset as mine", () => {
  const preset = {
    id: "preset-2",
    scope: "global",
    name: "Official",
    description: "",
    tags: [],
    system_prompt: "Hi",
    starter_prompts: [],
    skill_names: [],
    visibility: "public",
    status: "published",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } satisfies PersonaPreset;

  expect(
    buildPersonaPresetPayload(preset, draft, {
      scope: "user",
      status: "published",
    }),
  ).toEqual({
    ...draft,
    avatar: null,
    scope: "user",
    visibility: "private",
    status: "draft",
  });
});

test("includes status when updating an official preset", () => {
  const preset = {
    id: "preset-2",
    scope: "global",
    name: "Official",
    description: "",
    tags: [],
    system_prompt: "Hi",
    starter_prompts: [],
    skill_names: [],
    visibility: "public",
    status: "draft",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } satisfies PersonaPreset;

  expect(
    buildPersonaPresetPayload(preset, draft, {
      scope: "global",
      status: "published",
    }),
  ).toEqual({
    ...draft,
    avatar: null,
    visibility: "public",
    status: "published",
  });
});
