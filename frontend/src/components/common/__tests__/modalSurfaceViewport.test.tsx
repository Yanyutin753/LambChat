/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useAppViewport } from "../../../hooks/useAppViewport";
import { ModalSurface } from "../ModalSurface";

test("a body-portal dialog receives the keyboard inset when only the visual viewport shrinks", () => {
  vi.useFakeTimers();
  const viewport = new EventTarget();
  Object.assign(viewport, { height: 844, offsetTop: 0 });
  vi.stubGlobal("visualViewport", viewport);
  vi.stubGlobal("innerHeight", 844);
  vi.stubGlobal("innerWidth", 390);
  vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("iPhone");
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) =>
    window.setTimeout(() => callback(0), 0),
  );
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(window.clearTimeout);
  function Fixture() {
    useAppViewport();
    return (
      <ModalSurface open onClose={() => {}} label="Feedback">
        <textarea aria-label="Comment" />
        <button>Submit feedback</button>
      </ModalSurface>
    );
  }
  const view = render(<Fixture />);
  try {
    const field = screen.getByRole("textbox", { name: "Comment" });
    field.scrollIntoView = vi.fn();
    act(() => {
      vi.advanceTimersByTime(1);
      field.focus();
      Object.assign(viewport, { height: 420, offsetTop: 30 });
      viewport.dispatchEvent(new Event("resize"));
      vi.advanceTimersByTime(300);
    });
    expect(window.innerHeight).toBe(844);
    expect(document.documentElement.dataset.mobileKeyboard).toBe("true");
    expect(
      document.documentElement.style.getPropertyValue("--app-keyboard-inset"),
    ).toBe("394px");

    // jsdom does not lay out visual viewports. Check that the actual portal is
    // selected by the production rule consuming those measured keyboard bounds.
    const utilities = readFileSync(
      resolve(import.meta.dirname, "../../../styles/utilities.css"),
      "utf8",
    );
    const rule = utilities.match(
      /(html\[data-mobile-keyboard="true"\][^{]+)\{([^}]*bottom:\s*var\(--app-keyboard-inset[^}]+)\}/,
    );
    expect(rule).not.toBeNull();
    const overlay = screen.getByRole("dialog").parentElement!;
    expect(overlay.matches(rule![1].trim())).toBe(true);
    expect(rule![2]).toContain("top: var(--app-viewport-offset-top, 0px)");
    expect(rule![2]).toContain("max-height: var(--app-viewport-height, 100dvh)");
  } finally {
    view.unmount();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
});
