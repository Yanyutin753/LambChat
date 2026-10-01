/** @vitest-environment jsdom */
import { renderHook, act } from "@testing-library/react";
import { useAppViewport } from "../useAppViewport";

test("global viewport responds to keyboard resize, scroll and dismissal and cleans up", () => {
  vi.useFakeTimers();
  const viewport = new EventTarget();
  Object.assign(viewport, { height: 800, offsetTop: 0 });
  vi.stubGlobal("visualViewport", viewport);
  vi.stubGlobal("innerHeight", 800);
  vi.stubGlobal("innerWidth", 390);
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) =>
    window.setTimeout(() => callback(0), 0),
  );
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(
    window.clearTimeout,
  );
  vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("iPhone");
  const input = document.createElement("textarea");
  input.scrollIntoView = vi.fn();
  document.body.append(input);
  const { unmount } = renderHook(() => useAppViewport());
  try {
    act(() => {
      vi.advanceTimersByTime(1);
      input.focus();
    });
    Object.assign(viewport, { height: 420, offsetTop: 30 });
    act(() => {
      viewport.dispatchEvent(new Event("resize"));
      vi.advanceTimersByTime(300);
    });
    expect(document.documentElement.dataset.mobileKeyboard).toBe("true");
    expect(
      document.documentElement.style.getPropertyValue("--app-viewport-height"),
    ).toBe("420px");
    expect(
      document.documentElement.style.getPropertyValue("--app-keyboard-inset"),
    ).toBe("350px");
    expect(input.scrollIntoView).toHaveBeenCalled();
    // Native Android resizes the layout viewport as well: avoid a second inset.
    vi.stubGlobal("innerHeight", 420);
    Object.assign(viewport, { offsetTop: 0 });
    act(() => {
      window.dispatchEvent(new Event("resize"));
      vi.advanceTimersByTime(300);
    });
    expect(
      document.documentElement.style.getPropertyValue("--app-keyboard-inset"),
    ).toBe("0px");
    expect(document.documentElement.dataset.mobileKeyboard).toBe("true");
    // Rotation changes the baseline, so native IME state remains authoritative.
    document.documentElement.style.setProperty(
      "--app-native-keyboard-height",
      "380px",
    );
    vi.stubGlobal("innerWidth", 780);
    act(() => {
      window.dispatchEvent(new Event("resize"));
      vi.advanceTimersByTime(300);
    });
    expect(document.documentElement.dataset.mobileKeyboard).toBe("true");
    document.documentElement.style.removeProperty(
      "--app-native-keyboard-height",
    );
    vi.stubGlobal("innerHeight", 800);
    Object.assign(viewport, { height: 800 });
    act(() => {
      viewport.dispatchEvent(new Event("resize"));
      vi.advanceTimersByTime(300);
    });
    expect(document.documentElement.dataset.mobileKeyboard).toBeUndefined();
    expect(
      document.documentElement.style.getPropertyValue("--app-viewport-height"),
    ).toBe("");
  } finally {
    unmount();
    document.documentElement.style.removeProperty(
      "--app-native-keyboard-height",
    );
    input.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
});
