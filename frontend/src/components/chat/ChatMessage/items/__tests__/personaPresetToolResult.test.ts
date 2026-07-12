import {
  dispatchPersonaPresetRefreshFromToolResult,
  getPersonaPresetMutationDetail,
} from "../personaPresetToolResult.ts";
import {
  subscribePersonaPresetsChanged,
  type PersonaPresetsChangedDetail,
} from "../../../../../hooks/personaPresetEvents.ts";

test("recognizes persona preset mutation payloads from tool results", () => {
  expect(
    getPersonaPresetMutationDetail({
      action: "created",
      entity_type: "persona_preset",
      preset: { id: "preset-1", name: "Planner" },
      message: "Created",
    }),
  ).toEqual({ action: "created", presetId: "preset-1", presetName: "Planner" });
});

test("ignores non-persona tool results", () => {
  expect(
    getPersonaPresetMutationDetail({
      action: "created",
      entity_type: "other_entity",
    }),
  ).toBe(null);
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

  expect(dispatched).toBe(true);
  expect(seen).toEqual([
    { action: "updated", presetId: "preset-2", presetName: "Writer" },
  ]);
});
