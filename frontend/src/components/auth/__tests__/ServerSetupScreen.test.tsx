/** @vitest-environment jsdom */
/** 打包壳首启服务器配置屏：校验→探测→落盘→重载。 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    {
      method: "GET",
    },
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
