/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import i18n from "../../../i18n";
import type { SharedContentResponse } from "../../../types";
import { SharedEntry } from "../SharedEntry";
import { LanguagePreferenceProvider } from "../../../hooks/useLanguagePreference";

const api = vi.hoisted(() => ({ getSharedContent: vi.fn() }));
vi.mock("../../../services/api/share", () => ({ shareApi: api }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: undefined }),
}));

const content = (name: string): SharedContentResponse => ({
  session: { id: name, name, agent_id: "fast" },
  events: [],
  owner: { username: "Demo" },
  share_type: "full",
  share_scope: "session",
});
function renderEntry() {
  return render(
    <MemoryRouter initialEntries={["/shared/first"]}>
      <LanguagePreferenceProvider>
        <Link to="/shared/second">Other share</Link>
        <Routes>
          <Route path="/shared/:shareId" element={<SharedEntry />} />
        </Routes>
      </LanguagePreferenceProvider>
    </MemoryRouter>,
  );
}
beforeEach(async () => {
  vi.resetAllMocks();
  localStorage.clear();
  await i18n.changeLanguage("en");
});
afterEach(() => {
  cleanup();
  document.getElementById("shared-server-preview")?.remove();
});

test("share loading is announced while its content is unavailable", () => {
  api.getSharedContent.mockReturnValue(new Promise(() => {}));
  renderEntry();
  expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
});

test("page scrolling remains enabled through loading, errors and recovery, and is released on exit", async () => {
  let fail!: (reason: Error) => void;
  api.getSharedContent.mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        fail = reject;
      }),
  );
  api.getSharedContent.mockResolvedValueOnce(content("Recovered share"));
  const { unmount } = renderEntry();
  expect(document.documentElement).toHaveClass("allow-scroll");
  await act(async () => fail(new Error("Offline")));
  await screen.findByRole("alert");
  expect(document.documentElement).toHaveClass("allow-scroll");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByRole("heading", { name: "Recovered share" });
  expect(document.documentElement).toHaveClass("allow-scroll");
  unmount();
  expect(document.documentElement).not.toHaveClass("allow-scroll");
});

test("a failed client load removes the server preview instead of displaying stale content above the error", async () => {
  const preview = document.createElement("div");
  preview.id = "shared-server-preview";
  preview.textContent = "Server-rendered content";
  document.body.append(preview);
  api.getSharedContent.mockRejectedValue(new Error("Offline"));
  renderEntry();
  await screen.findByRole("alert");
  expect(document.getElementById("shared-server-preview")).toBeNull();
});

test("a transient share error remains retryable without requesting it twice automatically", async () => {
  api.getSharedContent.mockRejectedValueOnce(
    Object.assign(new Error("Service unavailable"), { status: 503 }),
  );
  let recover!: (value: SharedContentResponse) => void;
  api.getSharedContent.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        recover = resolve;
      }),
  );
  const { container } = renderEntry();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Failed to load shared content",
  );
  expect(screen.queryByText("Share Not Found")).toBeNull();
  expect(api.getSharedContent).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
  expect(container.querySelector("[data-shared-entry]")).toHaveFocus();
  await waitFor(() => expect(recover).toBeDefined());
  await act(async () => recover(content("Recovered share")));
  expect(
    await screen.findByRole("heading", { name: "Recovered share" }),
  ).toBeVisible();
  expect(api.getSharedContent.mock.calls).toEqual([["first"], ["first"]]);
});

test.each([
  [401, "Login Required", "Login now", "/auth/login"],
  [404, "Share Not Found", "Back to Home", "/"],
])(
  "HTTP %s uses the response status rather than parsing translated error text",
  async (status, heading, action, href) => {
    api.getSharedContent.mockRejectedValue(
      Object.assign(new Error("服务端已翻译错误"), { status }),
    );
    renderEntry();
    expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
    expect(screen.getByRole("link", { name: action })).toHaveAttribute(
      "href",
      href,
    );
    expect(api.getSharedContent).toHaveBeenCalledTimes(1);
  },
);

test("changing the public link hides previous content while the next share loads", async () => {
  api.getSharedContent.mockResolvedValueOnce(content("Previous share"));
  let finish!: (value: SharedContentResponse) => void;
  api.getSharedContent.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  renderEntry();
  await screen.findByRole("heading", { name: "Previous share" });
  fireEvent.click(screen.getByRole("link", { name: "Other share" }));
  expect(screen.queryByRole("heading", { name: "Previous share" })).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
  await waitFor(() => expect(finish).toBeDefined());
  await act(async () => finish(content("Current share")));
  expect(
    await screen.findByRole("heading", { name: "Current share" }),
  ).toBeVisible();
});
