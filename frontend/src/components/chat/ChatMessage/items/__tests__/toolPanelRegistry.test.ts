import {
  clearToolPanelRegistry,
  registerToolPanel,
} from "../toolPanelRegistry";

test("registering a remounted panel with the same registry key does not close it", () => {
  clearToolPanelRegistry();

  let closeCount = 0;
  const ownerA = Symbol("ownerA");
  const ownerB = Symbol("ownerB");

  const cleanupA = registerToolPanel(
    ownerA,
    () => {
      closeCount += 1;
    },
    "reveal:file-1",
  );

  const cleanupB = registerToolPanel(
    ownerB,
    () => {
      closeCount += 1;
    },
    "reveal:file-1",
  );

  expect(closeCount).toBe(0);

  cleanupA();
  cleanupB();
  clearToolPanelRegistry();
});
