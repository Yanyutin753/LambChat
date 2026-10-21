/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppContent } from "../index";

vi.mock("../ChatAppContent", () => ({
  ChatAppContent: ({
    sidebarCollapsed,
    setSidebarCollapsed,
    mobileSidebarOpen,
    setMobileSidebarOpen,
  }: {
    sidebarCollapsed: boolean;
    setSidebarCollapsed: (collapsed: boolean) => void;
    mobileSidebarOpen: boolean;
    setMobileSidebarOpen: (open: boolean) => void;
  }) => (
    <>
      <button
        aria-expanded={!sidebarCollapsed}
        onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
      >
        Navigation
      </button>
      <button
        aria-expanded={mobileSidebarOpen}
        onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
      >
        Mobile drawer
      </button>
    </>
  ),
}));
vi.mock("../NonChatAppContent", () => ({ NonChatAppContent: () => null }));
vi.mock("../../../../hooks/useAuth", () => ({
  SIDEBAR_COLLAPSED_STORAGE_KEY: "sidebar_collapsed",
}));
vi.mock("../../../../services/api", () => ({
  authApi: { updateMetadata: vi.fn().mockResolvedValue({}) },
}));
vi.mock("../../../../hooks/rightPanelWidthEvents", () => ({
  getRightPanelLayoutSnapshot: () => null,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT: "right-panel-width-changed",
  notifyRightPanelWidthChanged: vi.fn(),
}));

function resize(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
  });
  act(() => {
    window.dispatchEvent(new Event("resize"));
  });
}

async function renderAppContent() {
  const subscribe = vi.spyOn(window, "addEventListener");
  try {
    render(<AppContent activeTab="chat" />);
    await screen.findByRole("button", { name: "Navigation" });
    // A lazy child's DOM can appear before AppContent's passive subscription.
    await waitFor(() =>
      expect(subscribe).toHaveBeenCalledWith("resize", expect.any(Function)),
    );
  } finally {
    subscribe.mockRestore();
  }
}

beforeEach(() => {
  localStorage.clear();
  resize(1000);
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  resize(1000);
});

test("temporarily collapses below the minimum chat width and restores without saving the automatic change", async () => {
  await renderAppContent();
  resize(792);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  resize(791);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(localStorage.getItem("sidebar_collapsed")).toBeNull();
  resize(1000);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

test("excludes mobile widths while keeping the mobile drawer usable", async () => {
  resize(500);
  await renderAppContent();
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "Mobile drawer" }));
  expect(screen.getByRole("button", { name: "Mobile drawer" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

test("honors manual expansion until space recovers, then collapses on the next narrow resize", async () => {
  resize(670);
  await renderAppContent();
  fireEvent.click(screen.getByRole("button", { name: "Navigation" }));
  resize(660);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  resize(1000);
  resize(670);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});

test("preserves the saved collapsed preference when the window grows", async () => {
  localStorage.setItem("sidebar_collapsed", "true");
  resize(670);
  await renderAppContent();
  resize(1000);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(localStorage.getItem("sidebar_collapsed")).toBe("true");
});

test("accounts for a saved wide navigation before chat becomes cramped", async () => {
  localStorage.setItem("lambchat_desktop_sidebar_width", "480");
  await renderAppContent();
  resize(1000);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  resize(1100);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

test("rechecks chat space as navigation and docked panel widths change", async () => {
  resize(1200);
  await renderAppContent();
  act(() => {
    window.dispatchEvent(
      new CustomEvent("right-panel-width-changed", {
        detail: {
          open: true,
          kind: "content",
          presentation: "docked",
          widthPx: 350,
        },
      }),
    );
  });
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  act(() => {
    window.dispatchEvent(
      new CustomEvent("navigation-width-changed", { detail: 400 }),
    );
  });
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  act(() => {
    window.dispatchEvent(
      new CustomEvent("right-panel-width-changed", { detail: null }),
    );
  });
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});
