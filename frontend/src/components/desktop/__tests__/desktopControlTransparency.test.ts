/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";

vi.mock("react-dom/client", () => ({
  createRoot: () => ({ render: vi.fn() }),
}));
vi.mock("../../../i18n", () => ({ i18nReady: Promise.resolve() }));
vi.mock("../DesktopControl", () => ({ DesktopControl: () => null }));

afterEach(() => {
  vi.resetModules();
  localStorage.clear();
  history.replaceState(null, "", "/");
  document.documentElement.removeAttribute("style");
  document.documentElement.removeAttribute("class");
  document.body.removeAttribute("style");
});

test.each(["light", "dark", "sepia"])(
  "%s theme leaves the entire overlay document transparent",
  async (theme) => {
    localStorage.setItem("lambchat-theme", theme);
    history.replaceState(null, "", "/cua-control.html?surface=overlay");
    document.body.innerHTML = '<div id="root"></div>';
    await import("../../../desktop-control");
    expect(document.documentElement.style.backgroundColor).toBe("transparent");
    expect(document.body.style.backgroundColor).toBe("transparent");
  },
);

test("the interactive toolbar retains its opaque theme background", async () => {
  localStorage.setItem("lambchat-theme", "dark");
  history.replaceState(null, "", "/cua-control.html");
  document.body.innerHTML = '<div id="root"></div>';
  await import("../../../desktop-control");
  expect(document.body.style.backgroundColor).toBe("rgb(23, 24, 25)");
});
