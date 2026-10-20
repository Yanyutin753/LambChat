/** @vitest-environment jsdom */
import { cleanup, render, fireEvent } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { GrepItem } from "../GrepItem";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

afterEach(() => {
  cleanup();
  closePersistentToolPanel();
});

test("file search details distinguish duplicate names and expose every matching path", () => {
  const paths = Array.from(
    { length: 25 },
    (_, i) => `/workspace/topic-${i}/report.md`,
  );
  const item = render(
    <GrepItem
      args={{ pattern: "delivery" }}
      result={JSON.stringify(paths)}
      success
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.container.querySelectorAll(".tool-file-row")).toHaveLength(25);
  for (const path of paths) expect(panel.getByText(path)).toBeTruthy();
});
