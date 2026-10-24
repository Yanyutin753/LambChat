/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { AppShell } from "../AppShell";

vi.mock("../Header", () => ({ Header: () => null }));
vi.mock("../../../../utils/mobile", () => ({ isMobileDevice: () => true }));
vi.mock("../../../../hooks/useAppViewport", () => ({
  isStandaloneDisplayMode: () => false,
}));

test("mobile chat leaves document scroll under browser control on mount and resize", () => {
  vi.useFakeTimers();
  const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.stubGlobal("visualViewport", { height: 800 });
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(
    801,
  );
  vi.stubGlobal("innerHeight", 800);
  try {
    render(
      <AppShell
        activeTab="chat"
        showProfileModal={false}
        onCloseProfileModal={() => {}}
        setMobileSidebarOpen={() => {}}
        onNewSession={() => {}}
        onShowProfile={() => {}}
      >
        <main>Conversation</main>
      </AppShell>,
    );
    vi.advanceTimersByTime(1000);
    window.dispatchEvent(new Event("resize"));
    window.dispatchEvent(new Event("orientationchange"));
    vi.advanceTimersByTime(1000);
    expect(scrollTo).not.toHaveBeenCalled();
  } finally {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  }
});
