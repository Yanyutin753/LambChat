/** @vitest-environment jsdom */

import { fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { ToolArgsDisplay } from "../../ToolArgsDisplay";
import { FileTreeView } from "../FileTreeView";
import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
  registerActiveSidebarSnapshotTarget,
} from "../sidebarPanelSnapshot";

afterEach(() => {
  clearSidebarPanelSnapshots();
  document.body.replaceChildren();
});

test("captures expanded nested object arguments", () => {
  const view = render(<ToolArgsDisplay args={{ config: { mode: "safe" } }} />);
  registerActiveSidebarSnapshotTarget("panel:args", view.container);
  const configLabel = view.getByText("Config");
  const row = configLabel.parentElement;

  expect(row).not.toBeNull();
  if (!row) return;
  fireEvent.click(row);

  expect(row).toHaveAttribute("aria-expanded", "true");
  expect(captureActiveSidebarPanelSnapshot()?.expanded).toEqual([
    { locator: { path: [0, 0, 0] }, expanded: true },
  ]);
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
