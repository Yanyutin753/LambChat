/** @vitest-environment jsdom */
import { cleanup, render, fireEvent } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ReadFileItem } from "../ReadFileItem";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

afterEach(() => {
  cleanup();
  closePersistentToolPanel();
});

test("a failed read shows the original error without a numbered file editor", () => {
  const item = render(
    <ReadFileItem
      args={{ file_path: "/missing.md" }}
      result="File not found: /missing.md"
      success={false}
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getByRole("alert").textContent).toContain(
    "File not found: /missing.md",
  );
  expect(panel.container.querySelector(".tool-panel-code")).toBeNull();
});
