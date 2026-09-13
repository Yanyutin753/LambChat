import { computeMissingBindings } from "../personaPresetEditor";

test("returns empty when nothing is declared", () => {
  expect(computeMissingBindings(undefined, ["a"])).toEqual([]);
  expect(computeMissingBindings([], ["a"])).toEqual([]);
});

test("returns declared names missing from the available set", () => {
  expect(
    computeMissingBindings(["source-triage", "deepwiki-skill"], ["deepwiki-skill", "other"]),
  ).toEqual(["source-triage"]);
});

test("returns everything when the user has none available", () => {
  expect(computeMissingBindings(["a", "b"], [])).toEqual(["a", "b"]);
});
