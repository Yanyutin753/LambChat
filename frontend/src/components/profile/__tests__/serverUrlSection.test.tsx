/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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
  window.localStorage.setItem(
    "lambchat_server_url",
    "https://test.lambchat.com",
  );
  render(<ServerUrlSection />);
  expect(screen.getByText("https://test.lambchat.com")).toBeInTheDocument();
});

test("falls back to the page origin when nothing is configured", () => {
  render(<ServerUrlSection />);
  expect(screen.getByText(window.location.origin)).toBeInTheDocument();
});

test("saving a reachable url persists it and reloads", async () => {
  window.localStorage.setItem("lambchat_server_url", "https://old.example.com");
  window.localStorage.setItem("access_token", "synthetic-old-access");
  window.localStorage.setItem("refresh_token", "synthetic-old-refresh");
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
  expect(window.localStorage.getItem("access_token")).toBeNull();
  expect(window.localStorage.getItem("refresh_token")).toBeNull();
});

test("an unhealthy server shows the failure message and saves nothing", async () => {
  mocks.fetch.mockResolvedValue({ ok: false, status: 503 });
  render(<ServerUrlSection />);

  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  fireEvent.change(screen.getByLabelText(/server address/i), {
    target: { value: "https://broken.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));

  await waitFor(() => expect(screen.getByText(/HTTP 503/)).toBeInTheDocument());
  expect(window.localStorage.getItem("lambchat_server_url")).toBeNull();
  expect(mocks.reload).not.toHaveBeenCalled();
});

test("reset clears the runtime override and reloads", async () => {
  window.localStorage.setItem(
    "lambchat_server_url",
    "https://override.example.com",
  );
  window.localStorage.setItem("access_token", "synthetic-old-access");
  window.localStorage.setItem("refresh_token", "synthetic-old-refresh");
  render(<ServerUrlSection />);

  fireEvent.click(screen.getByRole("button", { name: /reset/i }));

  await waitFor(() => expect(mocks.reload).toHaveBeenCalled());
  expect(window.localStorage.getItem("lambchat_server_url")).toBeNull();
  expect(window.localStorage.getItem("access_token")).toBeNull();
  expect(window.localStorage.getItem("refresh_token")).toBeNull();
});

test("cancelled health check cannot save a late success and returns focus", async () => {
  window.localStorage.setItem("lambchat_server_url", "https://old.example.com");
  let resolve!: (value: { ok: boolean }) => void;
  mocks.fetch.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(<ServerUrlSection />);
  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  fireEvent.change(screen.getByLabelText(/server address/i), {
    target: { value: "https://new.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));
  fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
  await act(async () => resolve({ ok: true }));
  expect(window.localStorage.getItem("lambchat_server_url")).toBe(
    "https://old.example.com",
  );
  expect(mocks.reload).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /change/i })).toHaveFocus();
});

test("unmounted health check cannot change the server", async () => {
  let resolve!: (value: { ok: boolean }) => void;
  mocks.fetch.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const { unmount } = render(<ServerUrlSection />);
  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  fireEvent.change(screen.getByLabelText(/server address/i), {
    target: { value: "https://new.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));
  unmount();
  await act(async () => resolve({ ok: true }));
  expect(window.localStorage.getItem("lambchat_server_url")).toBeNull();
  expect(mocks.reload).not.toHaveBeenCalled();
});

test("checking freezes the address and keeps focus on the connection form", async () => {
  mocks.fetch.mockImplementationOnce(() => new Promise(() => {}));
  render(<ServerUrlSection />);
  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  fireEvent.change(screen.getByLabelText(/server address/i), {
    target: { value: "https://new.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));
  expect(screen.getByLabelText(/server address/i)).toBeDisabled();
  expect(
    screen.getByRole("form", { name: /connect to your.*server/i }),
  ).toHaveFocus();
  expect(
    screen.getByRole("form", { name: /connect to your.*server/i }),
  ).toHaveAttribute("aria-busy", "true");
});

test("Escape cancels locally while composition keeps the editor open", () => {
  render(<ServerUrlSection />);
  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  const input = screen.getByLabelText(/server address/i);
  fireEvent.keyDown(input, { key: "Escape", isComposing: true });
  expect(input).toBeInTheDocument();
  fireEvent.keyDown(input, { key: "Escape" });
  expect(screen.queryByLabelText(/server address/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /change/i })).toHaveFocus();
});

test("a health failure preserves focus moved to another setting", async () => {
  let resolve!: (value: { ok: boolean; status: number }) => void;
  mocks.fetch.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(
    <>
      <ServerUrlSection />
      <button>Another setting</button>
    </>,
  );
  fireEvent.click(screen.getByRole("button", { name: /change/i }));
  fireEvent.change(screen.getByLabelText(/server address/i), {
    target: { value: "https://new.example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));
  const other = screen.getByRole("button", { name: "Another setting" });
  other.focus();
  await act(async () => resolve({ ok: false, status: 503 }));
  expect(screen.getByRole("alert")).toBeVisible();
  expect(other).toHaveFocus();
});
