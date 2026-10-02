/** @vitest-environment jsdom */
/** 打包壳首启服务器配置屏：校验→探测→落盘→重载。 */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

import { ServerSetupScreen } from "../ServerSetupScreen";
import { getStoredServerUrl } from "../../../services/api/serverConfig";

const reloadSpy = vi.fn();
const fetchMock = vi.fn();

beforeEach(async () => {
  await i18n.changeLanguage("en");
  window.localStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(window, "location", {
    value: { ...window.location, reload: reloadSpy },
    writable: true,
  });
  fetchMock.mockReset();
  reloadSpy.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("connects, stores normalized url and reloads on healthy server", async () => {
  fetchMock.mockResolvedValueOnce(new Response("ok", { status: 200 }));
  render(<ServerSetupScreen />);

  fireEvent.change(screen.getByPlaceholderText("https://chat.example.com"), {
    target: { value: "my-lambchat.example.com/" },
  });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));

  await waitFor(() => expect(reloadSpy).toHaveBeenCalled());
  expect(fetchMock).toHaveBeenCalledWith(
    "https://my-lambchat.example.com/health",
    expect.objectContaining({
      method: "GET",
      signal: expect.any(AbortSignal),
    }),
  );
  expect(getStoredServerUrl()).toBe("https://my-lambchat.example.com");
});

test("unreachable server shows error and keeps url unset", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("network"));
  render(<ServerSetupScreen />);

  fireEvent.change(screen.getByPlaceholderText("https://chat.example.com"), {
    target: { value: "https://down.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));

  await waitFor(() =>
    expect(screen.getByText(/cannot reach/i)).toBeInTheDocument(),
  );
  expect(getStoredServerUrl()).toBeNull();
  expect(reloadSpy).not.toHaveBeenCalled();
});

test("non-2xx health shows status error", async () => {
  fetchMock.mockResolvedValueOnce(new Response("nope", { status: 502 }));
  render(<ServerSetupScreen />);

  fireEvent.change(screen.getByPlaceholderText("https://chat.example.com"), {
    target: { value: "https://bad.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));

  await waitFor(() => expect(screen.getByText(/502/)).toBeInTheDocument());
  expect(getStoredServerUrl()).toBeNull();
});

test("invalid url disables connect", () => {
  render(<ServerSetupScreen />);
  fireEvent.change(screen.getByPlaceholderText("https://chat.example.com"), {
    target: { value: "not a url" },
  });
  expect(screen.getByRole("button", { name: /connect/i })).toBeDisabled();
});

test("first setup cannot save a health response after unmount", async () => {
  let resolve!: (value: { ok: boolean }) => void;
  fetchMock.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const { unmount } = render(<ServerSetupScreen />);
  fireEvent.change(screen.getByPlaceholderText("https://chat.example.com"), {
    target: { value: "https://new.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));
  unmount();
  await act(async () => resolve({ ok: true }));
  expect(getStoredServerUrl()).toBeNull();
  expect(reloadSpy).not.toHaveBeenCalled();
});

test("first setup has a labelled field and freezes it during a check", () => {
  fetchMock.mockImplementationOnce(() => new Promise(() => {}));
  render(<ServerSetupScreen />);
  const input = screen.getByLabelText(/server address/i);
  fireEvent.change(input, { target: { value: "https://new.example.com" } });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));
  expect(input).toBeDisabled();
  expect(
    screen.getByRole("form", { name: /connect to your.*server/i }),
  ).toHaveFocus();
});

test("stalled health check releases the form and ignores late success", async () => {
  vi.useFakeTimers();
  let resolve!: (value: { ok: boolean }) => void;
  fetchMock.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(<ServerSetupScreen />);
  fireEvent.change(screen.getByPlaceholderText("https://chat.example.com"), {
    target: { value: "https://slow.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));
  await act(async () => {
    vi.advanceTimersByTime(15_000);
  });
  expect(screen.getByRole("alert")).toHaveTextContent(/cannot reach/i);
  expect(screen.getByPlaceholderText("https://chat.example.com")).toBeEnabled();
  await act(async () => resolve({ ok: true }));
  expect(getStoredServerUrl()).toBeNull();
  expect(reloadSpy).not.toHaveBeenCalled();
});
