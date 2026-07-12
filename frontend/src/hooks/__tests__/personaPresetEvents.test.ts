import {
  dispatchPersonaPresetsChanged,
  type PersonaPresetsChangedDetail,
  subscribePersonaPresetsChanged,
} from "../personaPresetEvents.ts";

test("persona preset change events can be subscribed and dispatched", () => {
  const target = new EventTarget();
  const seen: PersonaPresetsChangedDetail[] = [];

  const unsubscribe = subscribePersonaPresetsChanged(
    (detail) => seen.push(detail),
    target,
  );

  const dispatched = dispatchPersonaPresetsChanged(
    { action: "created", presetId: "preset-1", presetName: "Planner" },
    target,
  );

  unsubscribe();

  expect(dispatched).toBe(true);
  expect(seen).toEqual([
    { action: "created", presetId: "preset-1", presetName: "Planner" },
  ]);
});

test("unsubscribed listeners stop receiving persona preset change events", () => {
  const target = new EventTarget();
  let seen = 0;

  const unsubscribe = subscribePersonaPresetsChanged(() => {
    seen += 1;
  }, target);

  unsubscribe();
  dispatchPersonaPresetsChanged({ action: "updated" }, target);

  expect(seen).toBe(0);
});
