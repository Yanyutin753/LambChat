/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import {
  NavigationHistoryProvider,
  useNavigationHistory,
} from "../useNavigationHistory";

function Page() {
  const location = useLocation();
  const navigate = useNavigate();
  const { canBack, canForward, back, forward } = useNavigationHistory();
  return (
    <>
      <output>{location.pathname}</output>
      <button onClick={() => navigate("/settings")}>Settings</button>
      <button disabled={!canBack} onClick={back}>
        Back
      </button>
      <button disabled={!canForward} onClick={forward}>
        Forward
      </button>
      <input aria-label="Editor" />
      <select aria-label="Language">
        <option>English</option>
      </select>
    </>
  );
}

beforeEach(() => {
  window.history.replaceState({ idx: 0 }, "", "/chat");
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
  );
});

test("navigation preserves native select keyboard controls", () => {
  setup();
  const select = screen.getByRole("combobox");
  expect(fireEvent.keyDown(select, { key: "ArrowLeft", altKey: true })).toBe(
    true,
  );
  expect(screen.getByText("/settings")).toBeInTheDocument();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function setup() {
  render(
    <BrowserRouter>
      <NavigationHistoryProvider>
        <Page />
      </NavigationHistoryProvider>
    </BrowserRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
}

function shortcut(key: string, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", {
    key,
    metaKey: true,
    bubbles: true,
    cancelable: true,
    ...init,
  });
  fireEvent(window, event);
  return event;
}

test("macOS Command brackets navigate back and forward", async () => {
  setup();
  expect(shortcut("[").defaultPrevented).toBe(true);
  await screen.findByText("/chat");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Forward" })).toBeEnabled(),
  );
  expect(shortcut("]").defaultPrevented).toBe(true);
  await screen.findByText("/settings");
});

test("navigation leaves editor shortcuts and word movement untouched", () => {
  setup();
  const input = screen.getByRole("textbox", { name: "Editor" });
  for (const init of [
    { key: "[", metaKey: true },
    { key: "ArrowLeft", altKey: true },
  ]) {
    const event = new KeyboardEvent("keydown", {
      ...init,
      bubbles: true,
      cancelable: true,
    });
    input.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  }
  expect(screen.getByText("/settings")).toBeInTheDocument();
});

test("navigation ignores composing, consumed and shifted shortcuts", () => {
  setup();
  expect(shortcut("[", { isComposing: true }).defaultPrevented).toBe(false);
  expect(shortcut("[", { shiftKey: true }).defaultPrevented).toBe(false);
  const consumed = new KeyboardEvent("keydown", {
    key: "[",
    metaKey: true,
    bubbles: true,
    cancelable: true,
  });
  consumed.preventDefault();
  window.dispatchEvent(consumed);
  expect(screen.getByText("/settings")).toBeInTheDocument();
});

test("navigation leaves an open modal in place", () => {
  setup();
  const modal = document.createElement("div");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  document.body.append(modal);
  expect(shortcut("[").defaultPrevented).toBe(false);
  modal.remove();
});

test("Windows keeps Alt arrows and does not claim Command brackets", async () => {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
  );
  setup();
  expect(shortcut("[").defaultPrevented).toBe(false);
  expect(
    shortcut("ArrowLeft", { metaKey: false, altKey: true }).defaultPrevented,
  ).toBe(true);
  await screen.findByText("/chat");
});
