import {
  clearMissingSelections,
  isEveryVisibleSessionSelected,
  toggleAllVisibleSessions,
  toggleSessionSelection,
} from "../sessionSelection.ts";

test("toggleSessionSelection adds and removes one session id", () => {
  const first = toggleSessionSelection(new Set(), "session-1");
  expect(Array.from(first)).toEqual(["session-1"]);

  const second = toggleSessionSelection(first, "session-1");
  expect(Array.from(second)).toEqual([]);
});

test("toggleAllVisibleSessions selects all visible ids or clears them", () => {
  const visibleIds = ["session-1", "session-2", "session-3"];

  const selected = toggleAllVisibleSessions(new Set(["session-9"]), visibleIds);
  expect(Array.from(selected).sort()).toEqual([
    "session-1",
    "session-2",
    "session-3",
    "session-9",
  ]);

  const cleared = toggleAllVisibleSessions(selected, visibleIds);
  expect(Array.from(cleared)).toEqual(["session-9"]);
});

test("isEveryVisibleSessionSelected ignores empty visible lists", () => {
  expect(isEveryVisibleSessionSelected(new Set(), [])).toBe(false);
  expect(
    isEveryVisibleSessionSelected(new Set(["session-1", "session-2"]), [
      "session-1",
      "session-2",
    ]),
  ).toBe(true);
});

test("clearMissingSelections removes ids that are no longer loaded", () => {
  const selected = clearMissingSelections(
    new Set(["session-1", "session-2", "session-3"]),
    ["session-2", "session-3", "session-4"],
  );

  expect(Array.from(selected).sort()).toEqual(["session-2", "session-3"]);
});
