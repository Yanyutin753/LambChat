/** @vitest-environment jsdom */

import { cleanup, render, waitFor, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";

import { resetRightPanelCoordinator } from "../../../../common/rightPanelCoordinator";
import { BlockPreviewPortal, ToolResultContent } from "../McpBlockPreview";
import { closeBlockPreview, openBlockPreview } from "../blockPreviewStore";
import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
} from "../sidebarPanelSnapshot";

beforeEach(() => {
  resetRightPanelCoordinator();
  clearSidebarPanelSnapshots();
  closeBlockPreview();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});

afterEach(() => {
  cleanup();
  closeBlockPreview();
  resetRightPanelCoordinator();
  clearSidebarPanelSnapshots();
});

test("gives block preview history a stable snapshot identity", async () => {
  openBlockPreview({ type: "text", text: "hello" });
  render(<BlockPreviewPortal />);

  await waitFor(() => {
    expect(captureActiveSidebarPanelSnapshot()).toMatchObject({
      panelKey: "block-preview:text:hello",
    });
  });
});

test("generic generated-image previews load the small thumbnail and display original byte size", () => {
  render(
    <ToolResultContent
      result={{
        images: [
          {
            url: "https://app.example.com/api/upload/file/generated-images/large.png",
            content_type: "image/png",
            size: 2097152,
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("img", { name: "large.png" })).toHaveAttribute(
    "src",
    "https://app.example.com/api/upload/file/generated-images/large.png?thumb=1",
  );
  expect(screen.getByText("2.0 MB")).toBeVisible();
});
