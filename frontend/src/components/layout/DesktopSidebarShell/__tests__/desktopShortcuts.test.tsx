/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { DesktopSidebarShell } from "../DesktopSidebarShell";
import { ModalSurface } from "../../../common/ModalSurface";

vi.mock("../desktopShellPlatform", async (original) => ({
  ...(await original<typeof import("../desktopShellPlatform")>()),
  isDesktopShell: () => true,
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: {},
    hasAnyPermission: () => true,
    hasPermission: () => true,
  }),
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ enableMemory: true }),
}));
afterEach(cleanup);

test("desktop shortcuts preserve formatting, IME and modal editing", () => {
  const toggle = vi.fn();
  function Shell() {
    const location = useLocation();
    return (
      <>
        <output>{location.pathname}</output>
        <DesktopSidebarShell collapsed={false} onToggleCollapsed={toggle}>
          <input aria-label="Draft" />
        </DesktopSidebarShell>
      </>
    );
  }
  const { rerender } = render(
    <MemoryRouter initialEntries={["/chat"]}>
      <Shell />
    </MemoryRouter>,
  );
  fireEvent.keyDown(screen.getByRole("textbox"), {
    key: "b",
    ctrlKey: true,
    metaKey: true,
  });
  fireEvent.keyDown(document, {
    key: "b",
    ctrlKey: true,
    metaKey: true,
    isComposing: true,
  });
  expect(toggle).not.toHaveBeenCalled();
  fireEvent.keyDown(document, { key: "b", ctrlKey: true, metaKey: true });
  expect(toggle).toHaveBeenCalledOnce();
  rerender(
    <MemoryRouter initialEntries={["/chat"]}>
      <Shell />
      <ModalSurface open onClose={() => {}} label="Draft">
        <button>Save</button>
      </ModalSurface>
    </MemoryRouter>,
  );
  fireEvent.keyDown(screen.getByRole("button", { name: "Save" }), {
    key: ",",
    ctrlKey: true,
    metaKey: true,
  });
  expect(screen.getByText("/chat")).toBeInTheDocument();
});
