/** @vitest-environment jsdom */

import { act, render } from "@testing-library/react";
import { beforeAll, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  updateMetadata: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../services/api", () => ({
  authApi: { updateMetadata: mocks.updateMetadata },
}));

import { ThemeProvider, useTheme } from "../ThemeContext";

function Probe() {
  const { theme } = useTheme();
  return <div data-testid="probe">{theme}</div>;
}

function probeText(container: HTMLElement) {
  return container.querySelector<HTMLElement>('[data-testid="probe"]')!
    .textContent;
}

function fireThemeShortcut(target: HTMLElement, overrides?: KeyboardEventInit) {
  target.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "l",
      ctrlKey: true,
      shiftKey: true,
      bubbles: true,
      ...overrides,
    }),
  );
}

// jsdom does not implement matchMedia; stub it so theme initialization is deterministic.
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
});

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = "";
  mocks.updateMetadata.mockClear();
  mocks.updateMetadata.mockResolvedValue(undefined);
});

test("Ctrl/Cmd+Shift+L cycles light → dark → sepia", () => {
  const { container } = render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  );
  expect(probeText(container)).toBe("light");

  act(() => fireThemeShortcut(document.body));
  expect(probeText(container)).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);

  act(() => fireThemeShortcut(document.body));
  expect(probeText(container)).toBe("sepia");
  expect(document.documentElement.classList.contains("theme-sepia")).toBe(true);
});

test("theme shortcut yields to typing in editable targets", () => {
  const { container } = render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  );
  const input = document.createElement("input");
  container.appendChild(input);

  act(() => fireThemeShortcut(input));

  expect(probeText(container)).toBe("light");
});

test("Ctrl+L without shift does not switch the theme", () => {
  const { container } = render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  );

  act(() => fireThemeShortcut(document.body, { shiftKey: false }));

  expect(probeText(container)).toBe("light");
});
