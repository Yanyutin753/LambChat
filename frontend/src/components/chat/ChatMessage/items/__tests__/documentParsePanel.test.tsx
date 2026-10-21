/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { DocumentParseItem } from "../DocumentParseItem";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

afterEach(() => {
  cleanup();
  closePersistentToolPanel();
});

test("a failed document parse exposes the provider error in its detail panel", () => {
  const item = render(
    <DocumentParseItem
      args={{ url: "https://example.com/report.pdf" }}
      result={{ error: "The document is encrypted." }}
      success={false}
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getByRole("alert")).toHaveTextContent(
    "The document is encrypted.",
  );
});
