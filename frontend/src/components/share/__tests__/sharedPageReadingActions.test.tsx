/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SharedPage } from "../SharedPage";
import { LanguagePreferenceProvider } from "../../../hooks/useLanguagePreference";
import { APP_NAME } from "../../../constants";
import i18n from "../../../i18n";

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: undefined }),
}));
beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage("en");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderReader() {
  return render(
    <MemoryRouter>
      <LanguagePreferenceProvider>
        <SharedPage
          initialData={{
            session: { id: "demo", name: "Reading sample", agent_id: "fast" },
            events: [],
            owner: { username: "Demo" },
            share_type: "full",
            share_scope: "session",
          }}
        />
      </LanguagePreferenceProvider>
    </MemoryRouter>,
  );
}

test("public reader home and source links have names and consistent touch targets", async () => {
  renderReader();
  const home = await screen.findByRole("link", { name: APP_NAME, exact: true });
  expect(home).toHaveAttribute("href", "/");
  expect(home).toHaveClass("min-h-11");
  expect(screen.getByRole("link", { name: "GitHub" })).toHaveClass(
    "ui-button--lg",
    "ui-icon-button",
  );
});

test("reader scroll actions measure ready content and react to viewport and content resizing", async () => {
  let height = 1000;
  let measure = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal("innerHeight", 1000);
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockImplementation(
    () => height,
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        measure = callback;
      }
      observe = vi.fn();
      disconnect = disconnect;
    },
  );
  const { unmount } = renderReader();
  await screen.findByRole("heading", { name: "Reading sample" });
  expect(screen.queryByRole("button", { name: "Scroll to bottom" })).toBeNull();
  height = 1800;
  fireEvent.resize(window);
  expect(
    screen.getByRole("button", { name: "Scroll to bottom" }),
  ).toBeEnabled();
  height = 1000;
  act(() => measure());
  expect(screen.queryByRole("button", { name: "Scroll to bottom" })).toBeNull();
  unmount();
  expect(disconnect).toHaveBeenCalledOnce();
});

test("reader scroll shortcuts respect reduced motion", async () => {
  vi.stubGlobal("innerHeight", 1000);
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(
    2000,
  );
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  const scroll = vi.fn();
  vi.stubGlobal("scrollTo", scroll);
  renderReader();
  await screen.findByRole("heading", { name: "Reading sample" });
  fireEvent.click(screen.getByRole("button", { name: "Scroll to bottom" }));
  expect(scroll).toHaveBeenCalledWith({ top: 2000, behavior: "instant" });
});
