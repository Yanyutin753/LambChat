/** @vitest-environment jsdom */

import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { ToolArgsDisplay } from "../../ToolArgsDisplay";
import { FileTreeView } from "../FileTreeView";
import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
  registerActiveSidebarSnapshotTarget,
  queueSidebarPanelSnapshot,
  restorePendingSidebarPanelSnapshot,
} from "../sidebarPanelSnapshot";

afterEach(() => {
  clearSidebarPanelSnapshots();
  document.body.replaceChildren();
});

test("restores expanded nested object arguments", async () => {
  const view = render(<ToolArgsDisplay args={{ config: { mode: "safe" } }} />);
  registerActiveSidebarSnapshotTarget("panel:args", view.container);
  const row = view.getByRole("button", { expanded: false });
  fireEvent.click(row);

  expect(row).toHaveAttribute("aria-expanded", "true");
  const snapshot = captureActiveSidebarPanelSnapshot();
  expect(snapshot?.expanded).toHaveLength(1);
  expect(snapshot?.expanded[0].expanded).toBe(true);
  fireEvent.click(row);
  expect(row).toHaveAttribute("aria-expanded", "false");
  queueSidebarPanelSnapshot(snapshot);
  await act(async () => {
    expect(
      await restorePendingSidebarPanelSnapshot("panel:args", view.container),
    ).toBe(true);
  });
  expect(row).toHaveAttribute("aria-expanded", "true");
  expect(view.getByText(/"mode": "safe"/)).toBeVisible();
});

test("captures every expanded project directory by stable path", () => {
  const view = render(
    <FileTreeView
      files={{
        "src/components/panel.tsx": "export const panel = true;",
        "src/index.ts": "export {};",
      }}
      binaryFiles={{}}
      showHeader={false}
    />,
  );
  registerActiveSidebarSnapshotTarget("panel:tree", view.container);
  const srcButton = view.getByText("src").closest("button");

  expect(srcButton).not.toBeNull();
  if (!srcButton) return;
  fireEvent.click(srcButton);

  expect(srcButton).toHaveAttribute("aria-expanded", "true");
  expect(srcButton).toHaveAttribute(
    "data-sidebar-snapshot-key",
    "file-tree:/src",
  );
  expect(captureActiveSidebarPanelSnapshot()?.expanded).toContainEqual({
    locator: { key: "file-tree:/src" },
    expanded: true,
  });
});
