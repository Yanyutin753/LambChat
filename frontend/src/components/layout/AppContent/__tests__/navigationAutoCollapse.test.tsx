/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  act(() => {
    window.dispatchEvent(new Event("resize"));
  });
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

test("temporarily collapses below 680px and restores without saving the automatic change", () => {
  render(<AppContent activeTab="chat" />);
  resize(680);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  resize(679);
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

test("collapses on a narrow initial mount while keeping the mobile drawer usable", () => {
  resize(500);
  render(<AppContent activeTab="chat" />);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  fireEvent.click(screen.getByRole("button", { name: "Mobile drawer" }));
  expect(screen.getByRole("button", { name: "Mobile drawer" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

test("honors manual expansion until space recovers, then collapses on the next narrow resize", () => {
  resize(670);
  render(<AppContent activeTab="chat" />);
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

test("preserves the saved collapsed preference when the window grows", () => {
  localStorage.setItem("sidebar_collapsed", "true");
  resize(670);
  render(<AppContent activeTab="chat" />);
  resize(1000);
  expect(screen.getByRole("button", { name: "Navigation" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(localStorage.getItem("sidebar_collapsed")).toBe("true");
});
