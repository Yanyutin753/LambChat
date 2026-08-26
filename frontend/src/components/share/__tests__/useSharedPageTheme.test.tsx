/** @vitest-environment jsdom */
import { act } from "react";
import { renderHook } from "@testing-library/react";
import { useSharedPageTheme } from "../useSharedPageTheme";

// jsdom does not implement matchMedia; stub it so theme initialization is deterministic.
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({ matches: false, media: query }),
  });
});

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = "";
});

test("initializes to stored sepia preference", () => {
  window.localStorage.setItem("lambchat-theme", "sepia");

  const { result } = renderHook(() => useSharedPageTheme());

  expect(result.current.theme).toBe("sepia");
});

test("toggling away from sepia removes the stale theme-sepia class from <html>", () => {
  window.localStorage.setItem("lambchat-theme", "sepia");
  // Class left on <html> by the index.html boot script / ThemeProvider when
  // the stored preference is sepia.
  document.documentElement.classList.add("theme-sepia");

  const { result } = renderHook(() => useSharedPageTheme());
  expect(result.current.theme).toBe("sepia");

  act(() => result.current.toggleTheme());

  expect(result.current.theme).toBe("light");
  expect(document.documentElement.classList.contains("theme-sepia")).toBe(
    false,
  );
});

test("toggling away from sepia removes the stale dark class from <html>", () => {
  window.localStorage.setItem("lambchat-theme", "sepia");
  document.documentElement.classList.add("dark", "theme-sepia");

  const { result } = renderHook(() => useSharedPageTheme());

  act(() => result.current.toggleTheme());
  act(() => result.current.toggleTheme());

  expect(result.current.theme).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(document.documentElement.classList.contains("theme-sepia")).toBe(
    false,
  );
});

test("cycles light -> dark -> sepia -> light and syncs <html> classes", () => {
  const { result } = renderHook(() => useSharedPageTheme());
  expect(result.current.theme).toBe("light");

  act(() => result.current.toggleTheme());
  expect(result.current.theme).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);

  act(() => result.current.toggleTheme());
  expect(result.current.theme).toBe("sepia");
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  expect(document.documentElement.classList.contains("theme-sepia")).toBe(true);

  act(() => result.current.toggleTheme());
  expect(result.current.theme).toBe("light");
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  expect(document.documentElement.classList.contains("theme-sepia")).toBe(false);
});

test("persists the active theme to the lambchat-theme storage key", () => {
  const { result } = renderHook(() => useSharedPageTheme());

  act(() => result.current.toggleTheme());

  expect(window.localStorage.getItem("lambchat-theme")).toBe("dark");
});
