/** @vitest-environment jsdom */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";

import { resetRightPanelCoordinator } from "../../../../common/rightPanelCoordinator";
import { BlockPreviewPortal } from "../McpBlockPreview";
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
