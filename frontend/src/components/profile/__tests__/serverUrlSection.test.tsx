/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  reload: vi.fn(),
}));

vi.stubGlobal("fetch", mocks.fetch);

import { ServerUrlSection } from "../ServerUrlSection";

const originalLocation = window.location;

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
  window.localStorage.clear();
  // jsdom 的 location.reload 未实现：替换为可断言的替身
  // @ts-expect-error -- 测试替身（jsdom 允许 delete 后重挂）
  delete window.location;
  // @ts-expect-error -- 测试替身（jsdom 允许 delete 后重挂）
  window.location = { ...originalLocation, reload: mocks.reload };
});

afterEach(() => {
  // @ts-expect-error -- 还原真实 location
  window.location = originalLocation;
});

test("shows the effective server url with runtime override winning", () => {
  window.localStorage.setItem("lambchat_server_url", "https://test.lambchat.com");
  render(<ServerUrlSection />);
  expect(screen.getByText("https://test.lambchat.com")).toBeInTheDocument();
});

test("falls back to the page origin when nothing is configured", () => {
  render(<ServerUrlSection />);
  expect(screen.getByText(window.location.origin)).toBeInTheDocument();
});

test("saving a reachable url persists it and reloads", async () => {
  window.localStorage.setItem("lambchat_server_url", "https://old.example.com");
  mocks.fetch.mockResolvedValue({ ok: true });
  render(<ServerUrlSection />);

  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  const input = screen.getByLabelText(/server address/i);
  fireEvent.change(input, { target: { value: "https://new.example.com" } });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));

  await waitFor(() => expect(mocks.reload).toHaveBeenCalled());
  expect(mocks.fetch).toHaveBeenCalledWith(
    "https://new.example.com/health",
    expect.anything(),
  );
  expect(window.localStorage.getItem("lambchat_server_url")).toBe(
    "https://new.example.com",
  );
});

test("an unhealthy server shows the failure message and saves nothing", async () => {
  mocks.fetch.mockResolvedValue({ ok: false, status: 503 });
  render(<ServerUrlSection />);

  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  fireEvent.change(screen.getByLabelText(/server address/i), {
    target: { value: "https://broken.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));

  await waitFor(() =>
    expect(screen.getByText(/HTTP 503/)).toBeInTheDocument(),
  );
  expect(window.localStorage.getItem("lambchat_server_url")).toBeNull();
  expect(mocks.reload).not.toHaveBeenCalled();
});

test("reset clears the runtime override and reloads", async () => {
  window.localStorage.setItem("lambchat_server_url", "https://override.example.com");
  render(<ServerUrlSection />);

  fireEvent.click(screen.getByRole("button", { name: /reset/i }));

  await waitFor(() => expect(mocks.reload).toHaveBeenCalled());
  expect(window.localStorage.getItem("lambchat_server_url")).toBeNull();
});
