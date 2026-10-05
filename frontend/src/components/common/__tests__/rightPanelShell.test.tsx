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
import { afterEach, beforeEach, expect, test, vi } from "vitest";

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
import { UpdateTitlebarIndicator } from "../../layout/TitleBar/UpdateTitlebarIndicator";
import type { UpdateState } from "../../../types";
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
afterEach(() => vi.restoreAllMocks());

test.each(["last", "surface"])(
  "tool overlay wraps Tab from its %s into its own controls",
  async (from) => {
    installMatchMedia(390);
    vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
      {},
    ] as DOMRectList);
    render(
      <ToolResultPanel open onClose={vi.fn()} title="Tool">
        <button>Last tool action</button>
      </ToolResultPanel>,
    );
    const last = await screen.findByRole("button", {
      name: "Last tool action",
    });
    const dialog = screen.getByRole("dialog", { name: "Tool" });
    (from === "last" ? last : dialog).focus();
    const event = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey: from === "surface",
      bubbles: true,
      cancelable: true,
    });
    fireEvent(document.activeElement!, event);
    expect(event.defaultPrevented).toBe(true);
    expect(
      from === "last" ? screen.getByRole("tab", { name: "Tool" }) : last,
    ).toHaveFocus();
  },
);

test("mobile tool Escape closes the overlay after IME composition ends", async () => {
  installMatchMedia(390);
  const close = vi.fn();
  render(
    <ToolResultPanel open onClose={close} title="Tool">
      <button>Tool action</button>
    </ToolResultPanel>,
  );
  const action = await screen.findByRole("button", { name: "Tool action" });
  action.focus();
  fireEvent.keyDown(action, { key: "Escape", isComposing: true });
  fireEvent.keyDown(action, { key: "Escape", keyCode: 229 });
  expect(close).not.toHaveBeenCalled();
  fireEvent.keyDown(action, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
});

test("nested details receive Escape before the underlying mobile tool", async () => {
  installMatchMedia(390);
  const toolClose = vi.fn();
  function Harness() {
    const [details, setDetails] = useState(false);
    return (
      <>
        <ToolResultPanel open onClose={toolClose} title="Tool">
          <button onClick={() => setDetails(true)}>Open details</button>
        </ToolResultPanel>
        <ModalSurface
          open={details}
          onClose={() => setDetails(false)}
          label="Details"
        >
          <input aria-label="Detail field" />
        </ModalSurface>
      </>
    );
  }
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(await screen.findByRole("button", { name: "Open details" }));
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Detail field" }), {
    key: "Escape",
  });
  expect(screen.queryByRole("dialog", { name: "Details" })).toBeNull();
  expect(toolClose).not.toHaveBeenCalled();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(toolClose).toHaveBeenCalledOnce();
});

test("overlay Tab wraps visible controls instead of entering collapsed fields", async () => {
  installMatchMedia(800);
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    {},
  ] as DOMRectList);
  render(
    <EditorSidebar open onClose={vi.fn()} title="Editor">
      <button>Last visible</button>
      <div inert aria-hidden="true">
        <input aria-label="Collapsed field" />
      </div>
    </EditorSidebar>,
  );
  await act(async () => {});
  screen.getByRole("button", { name: "Last visible" }).focus();
  const event = new KeyboardEvent("keydown", {
    key: "Tab",
    bubbles: true,
    cancelable: true,
  });
  fireEvent(document.activeElement!, event);
  expect(event.defaultPrevented).toBe(true);
  expect(screen.getByRole("tab", { name: "Editor" })).toHaveFocus();
});

test.each([{ isComposing: true }, { keyCode: 229 }])(
  "cancelling IME composition does not close the editor panel (%j)",
  (composition) => {
    installMatchMedia(390);
    const close = vi.fn();
    render(
      <EditorSidebar open onClose={close} title="Editor">
        <input aria-label="Name" />
      </EditorSidebar>,
    );
    const input = screen.getByRole("textbox", { name: "Name" });
    fireEvent.keyDown(input, { key: "Escape", ...composition });
    expect(close).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
  },
);

test.each([390, 800])(
  "closing a %ipx editor restores the original page scroll state",
  (width) => {
    installMatchMedia(width);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "auto";
    const view = render(
      <EditorSidebar open onClose={vi.fn()} title="Editor">
        body
      </EditorSidebar>,
    );
    try {
      expect(document.body.style.overflow).toBe("hidden");
      view.rerender(
        <EditorSidebar open={false} onClose={vi.fn()} title="Editor">
          body
        </EditorSidebar>,
      );
      expect(document.body.style.overflow).toBe("auto");
    } finally {
      view.unmount();
      document.body.style.overflow = previous;
    }
  },
);

test("closing an underlying panel keeps the page locked until the modal closes", () => {
  installMatchMedia(800);
  const previous = document.body.style.overflow;
  document.body.style.overflow = "auto";
  const content = (panel: boolean, modal: boolean) => (
    <>
      <EditorSidebar open={panel} onClose={vi.fn()} title="Editor">
        body
      </EditorSidebar>
      <ModalSurface open={modal} onClose={vi.fn()} label="Confirm">
        Confirm
      </ModalSurface>
    </>
  );
  const view = render(content(true, true));
  try {
    view.rerender(content(false, true));
    expect(document.body.style.overflow).toBe("hidden");
    view.rerender(content(false, false));
    expect(document.body.style.overflow).toBe("auto");
  } finally {
    view.unmount();
    document.body.style.overflow = previous;
  }
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

test.each([410, 800])(
  "Escape closes the active tool preview at %ipx",
  (width) => {
    installMatchMedia(width);
    const close = vi.fn();
    render(
      <ToolResultPanel open onClose={close} title="Preview">
        body
      </ToolResultPanel>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
  },
);

test("hidden preview dialogs do not consume the active editor Escape", () => {
  installMatchMedia(800);
  const closeEditor = vi.fn();
  const closePreview = vi.fn();
  render(
    <>
      <EditorSidebar open onClose={closeEditor} title="Editor">
        draft
      </EditorSidebar>
      <ToolResultPanel open onClose={closePreview} title="Preview">
        preview
      </ToolResultPanel>
    </>,
  );
  const editorId = getRightPanelSnapshot().entries.find(
    (entry) => entry.kind === "editor",
  )!.id;
  act(() => activateRightPanel(editorId));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(closeEditor).toHaveBeenCalledOnce();
  expect(closePreview).not.toHaveBeenCalled();
});

test("Escape closes an update popover without closing its background editor", () => {
  const close = vi.fn();
  const update = {
    available: true,
    version: "99",
    releaseAssets: [],
    downloading: false,
  } as UpdateState;
  render(
    <>
      <EditorSidebar open onClose={close} title="Editor">
        draft
      </EditorSidebar>
      <UpdateTitlebarIndicator
        state={update}
        onInstall={() => {}}
        onSkipVersion={() => {}}
      />
    </>,
  );
  fireEvent.click(document.querySelector('button[aria-haspopup="dialog"]')!);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
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

test.each([false, true])(
  "closing a nested editor restores its opener in the remaining modal (unmounted=%s)",
  async (unmounted) => {
    installMatchMedia(390);
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <ModalSurface open onClose={vi.fn()} label="Persona picker">
            <button onClick={() => setOpen(true)}>Preview persona</button>
          </ModalSurface>
          {(!unmounted || open) && (
            <EditorSidebar
              open={open}
              onClose={() => setOpen(false)}
              title="Persona preview"
            >
              body
            </EditorSidebar>
          )}
        </>
      );
    }
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Preview persona" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: /^Close tab:/i }));
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(
      screen.getByRole("dialog", { name: "Persona picker" }),
    ).toBeVisible();
  },
);

test.each([
  { state: "hidden", hasControl: true },
  { state: "hidden", hasControl: false },
  { state: "removed", hasControl: true },
  { state: "removed", hasControl: false },
])(
  "a $state nested editor opener keeps focus in its modal (has control=$hasControl)",
  async ({ state, hasControl }) => {
    installMatchMedia(390);
    vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(
      function (this: HTMLElement) {
        return (this.closest('[hidden],[inert],[aria-hidden="true"]')
          ? []
          : [{}]) as unknown as DOMRectList;
      },
    );
    function Harness() {
      const [open, setOpen] = useState(false);
      const [previewed, setPreviewed] = useState(false);
      return (
        <>
          <main>
            <button>Background action</button>
          </main>
          <ModalSurface open onClose={vi.fn()} label="Persona picker">
            {!(state === "removed" && previewed && !open) && (
              <button
                hidden={state === "hidden" && previewed && !open}
                onClick={() => {
                  setPreviewed(true);
                  setOpen(true);
                }}
              >
                Preview persona
              </button>
            )}
            {hasControl && <button>Another persona</button>}
          </ModalSurface>
          <EditorSidebar
            open={open}
            onClose={() => setOpen(false)}
            title="Persona preview"
          >
            body
          </EditorSidebar>
        </>
      );
    }
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Preview persona" }));
    await user.click(screen.getByRole("button", { name: /^Close tab:/i }));
    await waitFor(() =>
      expect(
        hasControl
          ? screen.getByRole("button", { name: "Another persona" })
          : screen.getByRole("dialog", { name: "Persona picker" }),
      ).toHaveFocus(),
    );
  },
);

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

test("closing a tab reveals prior work without a redundant Back button", async () => {
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
  expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Close tab: Preview" }));

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
    await waitFor(() => expect(getRightPanelLayoutSnapshot()).toBeNull());
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

test.each(["hidden", "inert"])(
  "closing a docked editor returns to the visible section when its opener is %s",
  async (state) => {
    vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(
      function (this: HTMLElement) {
        return (this.closest('[hidden],[inert],[aria-hidden="true"]')
          ? []
          : [{}]) as unknown as DOMRectList;
      },
    );
    function Harness() {
      const [open, setOpen] = useState(false);
      const [models, setModels] = useState(true);
      return (
        <main>
          <button aria-pressed={!models} onClick={() => setModels(false)}>
            Assistants
          </button>
          <button aria-pressed={models} onClick={() => setModels(true)}>
            Models
          </button>
          <div
            hidden={state === "hidden" && !models}
            inert={state === "inert" && !models ? true : undefined}
          >
            <button onClick={() => setOpen(true)}>Add model</button>
          </div>
          <EditorSidebar
            open={open}
            onClose={() => setOpen(false)}
            title="Model editor"
          >
            body
          </EditorSidebar>
        </main>
      );
    }
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Add model" }));
    await user.click(screen.getByRole("button", { name: "Assistants" }));
    await user.click(screen.getByRole("button", { name: /^Close tab:/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Assistants" })).toHaveFocus(),
    );
  },
);


test.each([390, 900, 1440])("collapse keeps drafts and scroll state at %ipx", async (width) => {
  installMatchMedia(width);
  function Harness() {
    const [open, setOpen] = useState(true);
    return <EditorSidebar open={open} onClose={() => setOpen(false)} title="Draft editor">
      <input aria-label="Unsaved draft" defaultValue="draft" />
    </EditorSidebar>;
  }
  render(<Harness />);
  const input = screen.getByRole("textbox", { name: "Unsaved draft" });
  fireEvent.change(input, { target: { value: "keep me" } });
  const body = input.closest(".editor-sidebar-body")!;
  body.scrollTop = 123;
  fireEvent.click(screen.getByRole("button", { name: "Collapse panel" }));
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  expect(getRightPanelSnapshot().depth).toBe(1);
  await waitFor(() => expect(getRightPanelLayoutSnapshot()).toBeNull());
  const reopen = screen.getByRole("button", { name: "Expand panel" });
  await waitFor(() => expect(reopen).toHaveFocus());
  fireEvent.click(reopen);
  expect(screen.getByRole("textbox", { name: "Unsaved draft" })).toBe(input);
  expect(input).toHaveValue("keep me");
  expect(body.scrollTop).toBe(123);
  await waitFor(() => expect(screen.getByRole("tab")).toHaveFocus());
  fireEvent.click(screen.getByRole("button", { name: "Close tab: Draft editor" }));
  expect(screen.queryByRole("button", { name: "Expand panel" })).not.toBeInTheDocument();
  expect(getRightPanelSnapshot().depth).toBe(0);
});

test("tool tabs preserve detailed titles and reserve Back for explicit inner navigation", () => {
  const back = vi.fn();
  const { rerender } = render(<ToolResultPanel open onClose={() => {}} title="LambChat" subtitle="vanilla · 176 files">content</ToolResultPanel>);
  expect(screen.getByRole("tab", { name: "LambChat · vanilla · 176 files" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  rerender(<ToolResultPanel open onClose={() => {}} onBack={back} title="LambChat">content</ToolResultPanel>);
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(back).toHaveBeenCalledOnce();
});

test("restoring an automatic preview moves keyboard focus into its tab", async () => {
  render(<ToolResultPanel automatic open onClose={() => {}} title="Automatic result">result</ToolResultPanel>);
  const collapse = screen.getByRole("button", { name: "Collapse panel" });
  fireEvent.pointerDown(collapse);
  fireEvent.click(collapse);
  const restore = screen.getByRole("button", { name: "Expand panel" });
  await waitFor(() => expect(restore).toHaveFocus());
  installMatchMedia(390);
  fireEvent(window, new Event("resize"));
  fireEvent.click(restore);
  await waitFor(() => expect(screen.getByRole("tab", { name: "Automatic result" })).toHaveFocus());
});
