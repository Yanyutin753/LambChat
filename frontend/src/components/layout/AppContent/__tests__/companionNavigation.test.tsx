/** @vitest-environment jsdom */
import { Suspense, type ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AppContent } from "../index";

vi.mock("../../../agent/useAgentCatalog", () => ({
  useAgentCatalog: () => [],
}));
vi.mock("../../../agent/agentDisplayCatalog", () => ({
  AgentDisplayCatalogProvider: ({ children }: { children: ReactNode }) =>
    children,
}));
vi.mock("../../../../hooks/useAuth", () => ({
  SIDEBAR_COLLAPSED_STORAGE_KEY: "sidebar-collapsed",
}));
vi.mock("../../../../services/api", () => ({ authApi: {} }));
vi.mock("../../../assistants/AssistantsPanel", () => ({
  AssistantsPanel: () => <div>Standalone companions</div>,
}));
vi.mock("../NonChatAppContent", () => ({
  NonChatAppContent: ({
    activeTab,
    sidebarCollapsed,
  }: {
    activeTab: string;
    sidebarCollapsed: boolean;
  }) => (
    <nav aria-label="Global navigation" data-collapsed={sidebarCollapsed}>
      {activeTab}
    </nav>
  ),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
});

test.each([false, true])(
  "companions keeps shared navigation and its saved collapse preference (%s)",
  async (collapsed) => {
    localStorage.setItem("sidebar-collapsed", String(collapsed));
    render(
      <Suspense fallback={null}>
        <AppContent activeTab="assistants" />
      </Suspense>,
    );
    const navigation = await screen.findByRole("navigation", {
      name: "Global navigation",
    });
    expect(navigation).toHaveTextContent("assistants");
    expect(navigation).toHaveAttribute("data-collapsed", String(collapsed));
    expect(screen.queryByText("Standalone companions")).toBeNull();
  },
);
