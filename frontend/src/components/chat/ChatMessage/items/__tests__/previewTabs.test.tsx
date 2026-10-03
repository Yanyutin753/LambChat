/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import { RevealPreviewHost } from "../RevealPreviewHost";
import {
  clearRevealPreviewTabs,
  getActiveRevealPreviewState,
  getRevealPreviewTabs,
  setActiveRevealPreviewState,
} from "../activeRevealPreviewStore";
import { createActiveRevealPreviewState } from "../revealPreviewState";
import {
  PersistentToolPanelHost,
  closeAllPersistentToolPanels,
  openPersistentToolPanel,
  updatePersistentToolPanel,
} from "../persistentToolPanelState";
import { resetRightPanelCoordinator } from "../../../../common/rightPanelCoordinator";

beforeAll(async () => {
  // 文件预览弹窗（含 tab 条）整体在 LazyDocumentPreview 的 Suspense 边界内，
  // 冷启动 CI 上首次 import DocumentPreview 分块可能超过 findByRole 默认 1s
  // 超时；预热让 lazy() 立即 resolve，不再与超时竞速。
  await import("../../../../documents/DocumentPreview");
});

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});
afterEach(() => {
  cleanup();
  clearRevealPreviewTabs();
  closeAllPersistentToolPanels();
  resetRightPanelCoordinator();
});

test("files and tools share tabs; closing a background file does not close the selected file", async () => {
  render(
    <>
      <RevealPreviewHost
        preview={null}
        onClose={() => setActiveRevealPreviewState(null)}
      />
      <PersistentToolPanelHost />
    </>,
  );
  act(() =>
    setActiveRevealPreviewState(
      createActiveRevealPreviewState(
        {
          kind: "file",
          previewKey: "a",
          filePath: "alpha.txt",
          content: "alpha content",
        },
        "manual",
      ),
    ),
  );
  await screen.findByRole("tab", { name: "alpha.txt" }, { timeout: 5000 });
  act(() =>
    openPersistentToolPanel({
      panelKey: "tool:a",
      title: "Tool",
      status: "success",
      children: "tool content",
    }),
  );
  act(() =>
    setActiveRevealPreviewState(
      createActiveRevealPreviewState(
        {
          kind: "file",
          previewKey: "b",
          filePath: "beta.txt",
          content: "beta content",
        },
        "manual",
      ),
    ),
  );
  await screen.findByRole("tab", { name: "beta.txt" }, { timeout: 5000 });
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "alpha.txt",
    "Tool",
    "beta.txt",
  ]);
  fireEvent.click(screen.getByRole("tab", { name: "alpha.txt" }));
  expect(getActiveRevealPreviewState()?.request.previewKey).toBe("a");
  fireEvent.click(screen.getByRole("button", { name: "Close tab: beta.txt" }));
  expect(getRevealPreviewTabs().map((tab) => tab.request.previewKey)).toEqual([
    "a",
  ]);
  expect(screen.getByRole("tab", { name: "alpha.txt" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  act(() =>
    updatePersistentToolPanel(
      (panel) => ({ ...panel, children: "updated tool" }),
      "tool:a",
    ),
  );
  fireEvent.click(screen.getByRole("tab", { name: "Tool" }));
  await waitFor(() => expect(screen.getByText("updated tool")).toBeVisible());
});

test("same file paths in different projects keep separate tabs", async () => {
  render(
    <RevealPreviewHost
      preview={null}
      onClose={() => setActiveRevealPreviewState(null)}
    />,
  );
  for (const name of ["Project A", "Project B"]) {
    act(() =>
      setActiveRevealPreviewState(
        createActiveRevealPreviewState(
          {
            kind: "project",
            previewKey: name,
            project: {
              version: 1,
              name,
              mode: "folder",
              template: "static",
              fileCount: 1,
              files: { "/same.txt": name },
            },
          },
          "manual",
        ),
      ),
    );
    const project = await screen.findByRole("complementary", { name });
    fireEvent.click(
      await within(project).findByRole("button", { name: /^same.txt/ }),
    );
    await screen.findAllByRole("tab", { name: "same.txt" }, { timeout: 5000 });
  }
  expect(
    getRevealPreviewTabs().filter((tab) => tab.request.kind === "file"),
  ).toHaveLength(2);
});
