import test from "node:test";
import assert from "node:assert/strict";

import {
  dispatchPersonaPresetRefreshFromToolResult,
  getPersonaPresetMutationDetail,
} from "../personaPresetToolResult.ts";
import {
  subscribePersonaPresetsChanged,
  type PersonaPresetsChangedDetail,
} from "../../../../../hooks/personaPresetEvents.ts";

test("recognizes persona preset mutation payloads from tool results", () => {
  assert.deepEqual(
    getPersonaPresetMutationDetail({
      action: "created",
      entity_type: "persona_preset",
      preset: { id: "preset-1", name: "Planner" },
      message: "Created",
    }),
    { action: "created", presetId: "preset-1", presetName: "Planner" },
  );
});

test("ignores non-persona tool results", () => {
  assert.equal(
    getPersonaPresetMutationDetail({
      action: "created",
      entity_type: "other_entity",
    }),
    null,
  );
});

test("dispatches persona preset refresh events for matching tool results", () => {
  const target = new EventTarget();
  const seen: PersonaPresetsChangedDetail[] = [];
  const unsubscribe = subscribePersonaPresetsChanged(
    (detail) => seen.push(detail),
    target,
  );

  const dispatched = dispatchPersonaPresetRefreshFromToolResult(
    {
      action: "updated",
      entity_type: "persona_preset",
      preset: { id: "preset-2", name: "Writer" },
    },
    target,
  );

  unsubscribe();

  assert.equal(dispatched, true);
  assert.deepEqual(seen, [
    { action: "updated", presetId: "preset-2", presetName: "Writer" },
  ]);
});
