/** @vitest-environment jsdom */

import { useState, type ReactNode } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import {
  activateRightPanel,
  getRightPanelSnapshot,
  resetRightPanelCoordinator,
} from "../rightPanelCoordinator";
import { useRightPanelEntry } from "../useRightPanelEntry";
import { useSidebarPanel } from "../../../hooks/useSidebarPanel";
import { ToolResultPanel } from "../../chat/ChatMessage/items/ToolResultPanel";
import { EditorSidebar } from "../EditorSidebar";
import { ModalSurface } from "../ModalSurface";
import {
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
  getRightPanelLayoutSnapshot,
} from "../../../hooks/rightPanelWidthEvents";

function installMatchMedia(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
  });
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("min-width: 1200px")
      ? width >= 1200
      : query.includes("max-width: 639px")
        ? width <= 639
        : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

beforeEach(() => {
  resetRightPanelCoordinator();
  localStorage.clear();
  installMatchMedia(1440);
});

test("Escape dismisses a modal above a docked panel without closing that panel", () => {
  const closePanel = vi.fn();
  const closeModal = vi.fn();
  render(
    <>
      <EditorSidebar open onClose={closePanel} title="Editor">
        body
      </EditorSidebar>
      <ModalSurface open onClose={closeModal} label="Confirm">
        Confirm
      </ModalSurface>
    </>,
  );
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(closeModal).toHaveBeenCalledOnce();
  expect(closePanel).not.toHaveBeenCalled();
});

function TestPanel({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const entry = useRightPanelEntry({ open, onClose, kind: "editor" });
  if (!open) return null;

  return (
    <section
      data-right-panel-root
      hidden={!entry.active}
      inert={!entry.active ? true : undefined}
      aria-label={title}
    >
      {children}
    </section>
  );
}

test("exposes only the top registered entry and restores the prior entry", async () => {
  const firstClose = vi.fn();
  const secondClose = vi.fn();
  const view = render(
    <>
      <TestPanel open onClose={firstClose} title="First">
        first
      </TestPanel>
      <TestPanel open onClose={secondClose} title="Second">
        second
      </TestPanel>
    </>,
  );

  expect(
    screen.getByText("first").closest("[data-right-panel-root]"),
  ).toHaveAttribute("hidden");
  expect(screen.getByText("second")).toBeInTheDocument();

  view.rerender(
    <>
      <TestPanel open onClose={firstClose} title="First">
        first
      </TestPanel>
      <TestPanel open={false} onClose={secondClose} title="Second">
        second
      </TestPanel>
    </>,
  );

  expect(
    (await screen.findByText("first")).closest("[data-right-panel-root]"),
  ).not.toHaveAttribute("hidden");
});

test("keeps hidden editor DOM mounted so draft state survives Back", async () => {
  function Draft() {
    const [value, setValue] = useState("");
    return (
      <input
        aria-label="draft"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
    );
  }

  const user = userEvent.setup();
  const view = render(
    <>
      <TestPanel open onClose={vi.fn()} title="First">
        <Draft />
      </TestPanel>
      <TestPanel open={false} onClose={vi.fn()} title="Second">
        second
      </TestPanel>
    </>,
  );
  await user.type(screen.getByRole("textbox", { name: "draft" }), "kept");

  view.rerender(
    <>
      <TestPanel open onClose={vi.fn()} title="First">
        <Draft />
      </TestPanel>
      <TestPanel open onClose={vi.fn()} title="Second">
        second
      </TestPanel>
    </>,
  );
  view.rerender(
    <>
      <TestPanel open onClose={vi.fn()} title="First">
        <Draft />
      </TestPanel>
      <TestPanel open={false} onClose={vi.fn()} title="Second">
        second
      </TestPanel>
    </>,
  );

  expect(screen.getByRole("textbox", { name: "draft" })).toHaveValue("kept");
});

function SidebarPanelHarness() {
  const panel = useSidebarPanel({
    open: true,
    onClose: vi.fn(),
    kind: "content",
    widthStorageKey: "test-right-panel-width",
    widthCssVar: "--test-right-panel-width",
    defaultWidthPct: 48,
    minPanelPx: 320,
    minMainPx: 560,
  });

  return (
    <div
      ref={panel.panelRef}
      data-testid="panel"
      data-presentation={panel.presentation}
      data-width={panel.sidebarWidth}
    >
      <div data-testid="separator" {...panel.resizeSeparatorProps} />
    </div>
  );
}

test("clamps an unsafe stored width and supports accessible keyboard resizing", async () => {
  installMatchMedia(1200);
  localStorage.setItem("test-right-panel-width", "75");
  render(<SidebarPanelHarness />);

  expect(screen.getByTestId("panel")).toHaveAttribute(
    "data-presentation",
    "docked",
  );
  expect(screen.getByTestId("panel")).toHaveAttribute("data-width", "53");
  expect(localStorage.getItem("test-right-panel-width")).toBe("75");
  expect(document.documentElement).toHaveAttribute(
    "data-right-panel-presentation",
    "docked",
  );
  expect(
    document.documentElement.style.getPropertyValue(
      "--right-panel-active-width",
    ),
  ).toBe("636px");

  const separator = screen.getByRole("separator");
  fireEvent.keyDown(separator, { key: "ArrowLeft" });
  expect(screen.getByTestId("panel")).toHaveAttribute("data-width", "52");
  expect(localStorage.getItem("test-right-panel-width")).toBe("52");

  fireEvent.keyDown(separator, { key: "Home" });
  expect(screen.getByTestId("panel")).toHaveAttribute("data-width", "48");
  expect(localStorage.getItem("test-right-panel-width")).toBe("48");
  await act(async () => {});
  expect(getRightPanelLayoutSnapshot()?.open).toBe(true);
});

test("editor uses complementary semantics when docked", () => {
  render(
    <EditorSidebar open onClose={vi.fn()} title="Model editor">
      body
    </EditorSidebar>,
  );

  expect(
    screen.getByRole("complementary", { name: "Model editor" }),
  ).toHaveAttribute("data-panel-presentation", "docked");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("an open preview follows viewport changes from fullscreen through overlay to docked", () => {
  installMatchMedia(390);
  render(
    <ToolResultPanel open onClose={vi.fn()} title="Responsive preview">
      body
    </ToolResultPanel>,
  );
  expect(screen.getByRole("dialog")).toHaveAttribute(
    "data-panel-presentation",
    "fullscreen",
  );
  installMatchMedia(800);
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("dialog")).toHaveAttribute(
    "data-panel-presentation",
    "overlay",
  );
  installMatchMedia(1440);
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("complementary")).toHaveAttribute(
    "data-panel-presentation",
    "docked",
  );
});

test("editor close is labelled and resize rail is keyboard accessible", () => {
  render(
    <EditorSidebar open onClose={vi.fn()} title="Model editor">
      body
    </EditorSidebar>,
  );

  expect(screen.getByRole("button", { name: /^Close tab:/i })).toBeVisible();
  expect(screen.getByRole("separator")).toHaveAttribute("aria-valuenow");
});

test("editor uses modal dialog semantics in overlay and fullscreen modes", () => {
  installMatchMedia(1024);
  const view = render(
    <EditorSidebar open onClose={vi.fn()} title="Overlay editor">
      body
    </EditorSidebar>,
  );
  expect(
    screen.getByRole("dialog", { name: "Overlay editor" }),
  ).toHaveAttribute("aria-modal", "true");

  view.unmount();
  installMatchMedia(390);
  render(
    <EditorSidebar open onClose={vi.fn()} title="Mobile editor">
      body
    </EditorSidebar>,
  );
  expect(screen.getByRole("dialog", { name: "Mobile editor" })).toHaveAttribute(
    "data-panel-presentation",
    "fullscreen",
  );
});

test("manual close restores focus to the opening trigger", async () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open editor</button>
        <EditorSidebar
          open={open}
          onClose={() => setOpen(false)}
          title="Editor"
        >
          body
        </EditorSidebar>
      </>
    );
  }

  const user = userEvent.setup();
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Open editor" });
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: /^Close tab:/i }));

  await waitFor(() => expect(trigger).toHaveFocus());
});

test("a tool panel hides an editor and closing it restores the editor", async () => {
  const toolClose = vi.fn();
  const view = render(
    <>
      <EditorSidebar open onClose={vi.fn()} title="Editor">
        draft
      </EditorSidebar>
      <ToolResultPanel open onClose={toolClose} title="Preview">
        preview
      </ToolResultPanel>
    </>,
  );

  expect(
    screen.getByText("draft").closest("[data-right-panel-root]"),
  ).toHaveAttribute("hidden");
  expect(
    screen.getByText("preview").closest("[data-right-panel-root]"),
  ).not.toHaveAttribute("hidden");

  view.rerender(
    <>
      <EditorSidebar open onClose={vi.fn()} title="Editor">
        draft
      </EditorSidebar>
      <ToolResultPanel open={false} onClose={toolClose} title="Preview">
        preview
      </ToolResultPanel>
    </>,
  );

  expect(
    (await screen.findByText("draft")).closest("[data-right-panel-root]"),
  ).not.toHaveAttribute("hidden");
});

test("automatic tool panels do not replace a deliberate editor", () => {
  render(
    <>
      <EditorSidebar open onClose={vi.fn()} title="Editor">
        draft
      </EditorSidebar>
      <ToolResultPanel automatic open onClose={vi.fn()} title="Auto">
        auto
      </ToolResultPanel>
    </>,
  );

  expect(
    screen.getByText("draft").closest("[data-right-panel-root]"),
  ).not.toHaveAttribute("hidden");
  expect(
    screen.getByText("auto").closest("[data-right-panel-root]"),
  ).toHaveAttribute("hidden");
});

test("tool Back closes only the top panel and reveals prior work", async () => {
  function Harness() {
    const [toolOpen, setToolOpen] = useState(true);
    return (
      <>
        <EditorSidebar open onClose={vi.fn()} title="Editor">
          saved draft
        </EditorSidebar>
        <ToolResultPanel
          open={toolOpen}
          onClose={() => setToolOpen(false)}
          title="Preview"
        >
          preview body
        </ToolResultPanel>
      </>
    );
  }

  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "Back" }));

  await waitFor(() =>
    expect(
      screen.getByText("saved draft").closest("[data-right-panel-root]"),
    ).not.toHaveAttribute("hidden"),
  );
  expect(screen.queryByText("preview body")).not.toBeInTheDocument();
});

test("Escape closes only the active panel and restores the prior panel", async () => {
  const editorClose = vi.fn();

  function Harness() {
    const [toolOpen, setToolOpen] = useState(true);
    return (
      <>
        <EditorSidebar open onClose={editorClose} title="Editor">
          preserved draft
        </EditorSidebar>
        <ToolResultPanel
          open={toolOpen}
          onClose={() => setToolOpen(false)}
          title="Preview"
        >
          active preview
        </ToolResultPanel>
      </>
    );
  }

  render(<Harness />);
  fireEvent.keyDown(document, { key: "Escape" });

  await waitFor(() =>
    expect(
      screen.getByText("preserved draft").closest("[data-right-panel-root]"),
    ).not.toHaveAttribute("hidden"),
  );
  expect(editorClose).not.toHaveBeenCalled();
  expect(screen.queryByText("active preview")).not.toBeInTheDocument();
});

test("tab switches hand off layout without reporting a closed sidebar", async () => {
  const view = render(
    <>
      <EditorSidebar open onClose={() => {}} title="First">
        first
      </EditorSidebar>
      <ToolResultPanel open onClose={() => {}} title="Second">
        second
      </ToolResultPanel>
    </>,
  );
  const closed = vi.fn();
  const listener = (event: Event) => {
    if (!(event as CustomEvent).detail) closed();
  };
  window.addEventListener(RIGHT_PANEL_WIDTH_CHANGED_EVENT, listener);
  try {
    const entries = getRightPanelSnapshot().entries;
    for (const entry of [entries[0], entries[1], entries[0]]) {
      await act(async () => activateRightPanel(entry.id));
      expect(getRightPanelLayoutSnapshot()?.open).toBe(true);
      expect(closed).not.toHaveBeenCalled();
    }
    view.unmount();
    await act(async () => {});
    expect(getRightPanelLayoutSnapshot()).toBeNull();
    expect(closed).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener(RIGHT_PANEL_WIDTH_CHANGED_EVENT, listener);
  }
});

test("a sidebar is visible immediately without waiting for animation frames", () => {
  render(
    <EditorSidebar open onClose={() => {}} title="Immediate">
      body
    </EditorSidebar>,
  );
  expect(screen.getByRole("complementary", { name: "Immediate" })).toHaveClass(
    "editor-sidebar--animate-in",
  );
});

test("editor uses one tab title without a duplicate header", async () => {
  const onClose = vi.fn();
  render(
    <EditorSidebar
      open
      onClose={onClose}
      title="Edit team"
      subtitle="Build roles"
    >
      <div>Team form</div>
    </EditorSidebar>,
  );
  await waitFor(() =>
    expect(screen.getByRole("tab", { name: "Edit team" })).toBeTruthy(),
  );
  expect(screen.getAllByText("Edit team")).toHaveLength(1);
  expect(screen.queryByText("Build roles")).toBeNull();
  expect(document.querySelector(".editor-sidebar-header")).toBeNull();
  expect(screen.getByRole("complementary", { name: "Edit team" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Close tab: Edit team" }));
  expect(onClose).toHaveBeenCalledOnce();
});
