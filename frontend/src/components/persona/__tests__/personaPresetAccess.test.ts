import test from "node:test";
import assert from "node:assert/strict";

import { getPersonaPresetCapabilities } from "../personaPresetAccess.ts";
import type { PersonaPreset } from "../../../types";

function buildPreset(scope: "user" | "global"): PersonaPreset {
  return {
    id: `${scope}-preset`,
    scope,
    name: scope === "global" ? "Official" : "Mine",
    description: "",
    tags: [],
    system_prompt: "prompt",
    skill_names: [],
    visibility: scope === "global" ? "public" : "private",
    status: scope === "global" ? "published" : "draft",
    version: 1,
    usage_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

test("non-admin writers can copy official presets but cannot edit or delete them", () => {
  assert.deepEqual(
    getPersonaPresetCapabilities(buildPreset("global"), {
      canWrite: true,
      canAdmin: false,
    }),
    {
      canCopy: true,
      canEdit: false,
      canDelete: false,
    },
  );
});

test("admins can manage official presets directly", () => {
  assert.deepEqual(
    getPersonaPresetCapabilities(buildPreset("global"), {
      canWrite: true,
      canAdmin: true,
    }),
    {
      canCopy: true,
      canEdit: true,
      canDelete: true,
    },
  );
});

test("writers can manage their own presets", () => {
  assert.deepEqual(
    getPersonaPresetCapabilities(buildPreset("user"), {
      canWrite: true,
      canAdmin: false,
    }),
    {
      canCopy: false,
      canEdit: true,
      canDelete: true,
    },
  );
});
