/** @vitest-environment jsdom */
import { useEffect, useRef, useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  toolCallPanelStore,
  type ToolCallPanelData,
} from "../../chat/ChatMessage/toolCallPanelStore";
import { openToolLivePanel } from "../../chat/ChatMessage/items/ToolLivePanelContent";
import { EditorSidebar } from "../EditorSidebar";
import { resetRightPanelCoordinator } from "../rightPanelCoordinator";
import {
  PersistentToolPanelHost,
  openPersistentToolPanel,
  closeAllPersistentToolPanels,
} from "../../chat/ChatMessage/items/persistentToolPanelState";

beforeEach(() => {
  resetRightPanelCoordinator();
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1440,
  });
});
afterEach(() => {
  cleanup();
  toolCallPanelStore.clear();
  closeAllPersistentToolPanels?.();
  resetRightPanelCoordinator();
});

test.each([320, 390, 834, 1440])(
  "switches tabs at %ipx without losing drafts, scroll or imperative viewer instances",
  async (width) => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: width,
    });
    let initializations = 0;
    function Draft() {
      const [value, setValue] = useState("");
      const host = useRef<HTMLDivElement>(null);
      useEffect(() => {
        initializations++;
        const viewer = document.createElement("textarea");
        viewer.setAttribute("aria-label", "Imperative viewer");
        host.current!.appendChild(viewer);
        return () => viewer.remove();
      }, []);
      return (
        <div ref={host}>
          <input
            aria-label="Draft"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </div>
      );
    }
    function Harness() {
      const [second, setSecond] = useState(false);
      return (
        <>
          <button onClick={() => setSecond(true)}>Open second</button>
          <EditorSidebar open onClose={() => {}} title="First">
            <Draft />
          </EditorSidebar>
          <EditorSidebar
            open={second}
            onClose={() => setSecond(false)}
            title="Second"
          >
            second
          </EditorSidebar>
        </>
      );
    }
    render(<Harness />);
    fireEvent.change(screen.getByRole("textbox", { name: "Draft" }), {
      target: { value: "unsaved" },
    });
    const body = document.querySelector<HTMLElement>(".editor-sidebar-body")!;
    body.scrollTop = 123;
    const viewer = screen.getByRole("textbox", { name: "Imperative viewer" });
    fireEvent.change(viewer, { target: { value: "viewer state" } });
    expect(initializations).toBe(1);
    fireEvent.click(screen.getByText("Open second"));
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "First",
      "Second",
    ]);
    expect(initializations).toBe(1);
    fireEvent.click(screen.getByRole("tab", { name: "First" }));
    expect(screen.getByRole("textbox", { name: "Draft" })).toHaveValue(
      "unsaved",
    );
    expect(body.scrollTop).toBe(123);
    expect(screen.getByRole("textbox", { name: "Imperative viewer" })).toBe(
      viewer,
    );
    expect(viewer).toHaveValue("viewer state");
    expect(initializations).toBe(1);
    fireEvent.keyDown(screen.getByRole("tab", { name: "First" }), {
      key: "ArrowRight",
    });
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Second" })).toHaveFocus(),
    );
    fireEvent.keyDown(screen.getByRole("tab", { name: "Second" }), {
      key: "Delete",
    });
    expect(screen.getByRole("textbox", { name: "Draft" })).toHaveValue(
      "unsaved",
    );
    expect(screen.queryByRole("tab", { name: "Second" })).toBeNull();
  },
);

test("keeps multiple tool results and reopens the existing tab without reordering", async () => {
  render(<PersistentToolPanelHost />);
  act(() =>
    openPersistentToolPanel({
      panelKey: "a",
      title: "Alpha",
      status: "success",
      children: <input aria-label="Alpha draft" defaultValue="kept" />,
    }),
  );
  await screen.findByRole("textbox", { name: "Alpha draft" });
  act(() =>
    openPersistentToolPanel({
      panelKey: "b",
      title: "Beta",
      status: "success",
      children: "beta",
    }),
  );
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Alpha",
    "Beta",
  ]);
  act(() =>
    openPersistentToolPanel({
      panelKey: "a",
      title: "Alpha",
      status: "success",
      children: <input aria-label="Alpha draft" defaultValue="new" />,
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "Alpha draft" })).toHaveValue(
      "kept",
    ),
  );
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Alpha",
    "Beta",
  ]);
});

test("closing a background tab leaves the foreground selected and closing all releases content", async () => {
  render(<PersistentToolPanelHost />);
  act(() => {
    openPersistentToolPanel({
      panelKey: "one",
      title: "One",
      status: "success",
      children: "first result",
    });
    openPersistentToolPanel({
      panelKey: "two",
      title: "Two",
      status: "success",
      children: "second result",
    });
    openPersistentToolPanel({
      panelKey: "three",
      title: "Three",
      status: "success",
      children: "third result",
    });
  });
  fireEvent.click(screen.getByRole("button", { name: "Close tab: Two" }));
  expect(screen.getByRole("tab", { name: "Three" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.queryByText("second result")).toBeNull();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Three" }), {
    key: "Delete",
  });
  expect(screen.getByRole("tab", { name: "One" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  act(() => closeAllPersistentToolPanels());
  expect(screen.queryByRole("tablist")).toBeNull();
  expect(screen.queryByText("first result")).toBeNull();
});

test("an automatic preview becomes a retained tab after deliberate interaction", async () => {
  render(<PersistentToolPanelHost />);
  act(() =>
    openPersistentToolPanel({
      panelKey: "auto",
      title: "Automatic",
      status: "success",
      auto: true,
      children: <button>Inspect result</button>,
    }),
  );
  const inspect = await screen.findByRole("button", { name: "Inspect result" });
  fireEvent.pointerDown(inspect);
  act(() =>
    openPersistentToolPanel({
      panelKey: "manual",
      title: "Manual",
      status: "success",
      children: "manual",
    }),
  );
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Automatic",
    "Manual",
  ]);
});

test("background tool updates do not render until selected, then show the latest result", async () => {
  toolCallPanelStore.set({
    toolCallId: "live",
    toolName: "read_file",
    formattedToolName: "Read",
    args: {},
    status: "loading",
    result: "pending",
  });
  const build = vi.fn((data: ToolCallPanelData) => (
    <div>{String(data.result)}</div>
  ));
  render(<PersistentToolPanelHost />);
  act(() =>
    openToolLivePanel({
      id: "live",
      title: "Live",
      status: "loading",
      buildDetail: build,
    }),
  );
  await screen.findByText("pending");
  act(() =>
    openPersistentToolPanel({
      panelKey: "other",
      title: "Other",
      status: "success",
      children: "other",
    }),
  );
  const previousRenders = build.mock.calls.length;
  act(() =>
    toolCallPanelStore.set({
      ...toolCallPanelStore.get("live")!,
      result: "finished",
      status: "success",
    }),
  );
  expect(build.mock.calls.length).toBe(previousRenders);
  fireEvent.click(screen.getByRole("tab", { name: "Live" }));
  await waitFor(() => expect(screen.getByText("finished")).toBeVisible());
});
