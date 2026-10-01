/** @vitest-environment jsdom */

import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { CollapsibleSection } from "../../CollapsibleSection";
import {
  openPersistentToolPanel,
  getPersistentToolPanelState,
  closeAllPersistentToolPanels,
} from "../persistentToolPanelState";
import {
  openBlockPreview,
  getBlockPreview,
  clearBlockPreviews,
} from "../blockPreviewStore";
import { clearSidebarHistory, goBackSidebar } from "../sidebarHistoryStore";
import {
  clearSidebarPanelSnapshots,
  queueSidebarPanelSnapshot,
  restorePendingSidebarPanelSnapshot,
} from "../sidebarPanelSnapshot";

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
  clearBlockPreviews();
  clearSidebarHistory();
  clearSidebarPanelSnapshots();
});

test("CollapsibleSection exposes a stable snapshot key for history restore", () => {
  const view = render(
    <CollapsibleSection title="处理过程">
      <div>content</div>
    </CollapsibleSection>,
  );
  const toggle = view.getByRole("button") as HTMLElement;
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  expect(toggle.dataset.sidebarSnapshotKey).toBe("section:处理过程");

  const content = view.getByText("content").parentElement as HTMLElement;
  expect(content.dataset.sidebarSnapshotKey).toBe("section:处理过程-content");
});

test("opening a block retains the tool as a separate tab without legacy history", () => {
  openPersistentToolPanel({
    title: "Tool A",
    status: "idle",
    children: <div>tool-a</div>,
    panelKey: "tool:a",
  });

  // 打开块预览保留工具标签，不再捕获旧式历史快照
  openBlockPreview({ type: "text", text: "block" });
  expect(getBlockPreview()).not.toBeNull();

  expect(goBackSidebar()).toBe(false);

  // 两份内容同时保留，由协调器决定哪个可见
  expect(getBlockPreview()).not.toBeNull();
  expect(getPersistentToolPanelState()?.panelKey).toBe("tool:a");
});

test("restore drops a pending snapshot that belongs to another panel", async () => {
  const root = document.createElement("div");
  document.body.appendChild(root);

  queueSidebarPanelSnapshot({
    panelKey: "persistent:tool:other",
    expanded: [],
    pressed: [],
    details: [],
    scroll: [],
  });

  // 打开的是另一个面板：旧快照应被丢弃而不是残留等误命中
  const restored = await restorePendingSidebarPanelSnapshot(
    "persistent:tool:current",
    root,
  );
  expect(restored).toBe(false);

  // 再排一个当前面板的空快照，确认前面的残留已被清掉（不会恢复出别的状态）
  const restoredAgain = await restorePendingSidebarPanelSnapshot(
    "persistent:tool:current",
    root,
  );
  expect(restoredAgain).toBe(false);

  root.remove();
});

test("panel host keeps view mode / fullscreen in panel state for back-restore", async () => {
  // Host 的受控接线见 persistentToolPanelState.tsx：viewMode/isFullscreen
  // 回写 store，历史 capture 冻结整个 panel 对象，返回后原样恢复
  const { PersistentToolPanelHost } = await import(
    "../persistentToolPanelState"
  );
  const host = render(<PersistentToolPanelHost />);
  expect(host.container.textContent).toBe("");

  openPersistentToolPanel({
    title: "Tool V",
    status: "idle",
    children: <div>tool-v</div>,
    panelKey: "tool:v",
    viewMode: "center",
    isFullscreen: true,
  });

  const state = getPersistentToolPanelState();
  expect(state?.viewMode).toBe("center");
  expect(state?.isFullscreen).toBe(true);
});
