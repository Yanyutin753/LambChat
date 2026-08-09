/** @vitest-environment jsdom */

import { useState } from "react";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { resetRightPanelCoordinator } from "../../../../common/rightPanelCoordinator";
import { ToolResultPanel } from "../ToolResultPanel";
import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
  queueSidebarPanelSnapshot,
  type SidebarPanelSnapshot,
} from "../sidebarPanelSnapshot";

function SnapshotContent({ version = 1 }: { version?: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div>
      <button
        type="button"
        data-sidebar-snapshot-key="args"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        Arguments
      </button>
      <div data-testid="expanded-state">
        {expanded ? "expanded" : "collapsed"}
      </div>
      <div data-sidebar-snapshot-key="results" data-testid="results-scroll">
        version {version}
      </div>
    </div>
  );
}

beforeEach(() => {
  resetRightPanelCoordinator();
  clearSidebarPanelSnapshots();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});

afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
  clearSidebarPanelSnapshots();
});

test("registers the active tool panel as the sidebar snapshot target", async () => {
  const view = render(
    <ToolResultPanel
      open
      onClose={vi.fn()}
      title="Tool A"
      registryKey="panel:a"
    >
      <SnapshotContent />
    </ToolResultPanel>,
  );
  const scroller = await view.findByTestId("results-scroll");
  scroller.scrollTop = 88;

  await waitFor(() => {
    expect(captureActiveSidebarPanelSnapshot()).toMatchObject({
      panelKey: "panel:a",
      scroll: [
        {
          locator: { key: "results" },
          top: 88,
          left: 0,
        },
      ],
    });
  });
});

test("restores a history snapshot before revealing panel content", async () => {
  const snapshot: SidebarPanelSnapshot = {
    panelKey: "panel:a",
    expanded: [{ locator: { key: "args" }, expanded: true }],
    pressed: [],
    details: [],
    scroll: [{ locator: { key: "results" }, top: 144, left: 18 }],
  };
  queueSidebarPanelSnapshot(snapshot);

  const view = render(
    <ToolResultPanel
      open
      onClose={vi.fn()}
      title="Tool A"
      registryKey="panel:a"
    >
      <SnapshotContent />
    </ToolResultPanel>,
  );

  const body = document.querySelector<HTMLElement>(".tool-console-body");
  expect(body?.getAttribute("aria-busy")).toBe("true");

  await waitFor(() => {
    expect(view.getByTestId("expanded-state")).toHaveTextContent("expanded");
    expect(view.getByTestId("results-scroll").scrollTop).toBe(144);
    expect(view.getByTestId("results-scroll").scrollLeft).toBe(18);
    expect(body?.getAttribute("aria-busy")).toBe("false");
  });

  view.rerender(
    <ToolResultPanel
      open
      onClose={vi.fn()}
      title="Tool A"
      registryKey="panel:a"
    >
      <SnapshotContent version={2} />
    </ToolResultPanel>,
  );

  expect(view.getByTestId("expanded-state")).toHaveTextContent("expanded");
  expect(body?.getAttribute("aria-busy")).toBe("false");
});
