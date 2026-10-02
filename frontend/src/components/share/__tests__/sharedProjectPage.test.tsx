/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import i18n from "../../../i18n";
import type {
  SharedContentResponse,
  SharedProjectContentResponse,
} from "../../../types";
import { SharedProjectPage } from "../SharedProjectPage";
import { LanguagePreferenceProvider } from "../../../hooks/useLanguagePreference";

const api = vi.hoisted(() => ({
  getSharedContent: vi.fn(),
  getSessionContentInProject: vi.fn(),
  updateMetadata: vi.fn(),
}));
vi.mock("../../../services/api/share", () => ({ shareApi: api }));
vi.mock("../../../services/api", () => ({
  authApi: { updateMetadata: api.updateMetadata },
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "viewer" } }),
}));
const manifest: SharedProjectContentResponse = {
  share_scope: "project",
  share_type: "full",
  visibility: "public",
  project: { id: "project", name: "Research project", icon: "Folder" },
  owner: { username: "Demo" },
  sessions: [
    { id: "first", name: "First conversation" },
    { id: "second", name: "Second conversation" },
  ],
  sessions_total: 3,
  has_more: true,
};
const content: SharedContentResponse = {
  share_scope: "session",
  share_type: "full",
  owner: { username: "Demo" },
  session: { id: "first", name: "First conversation", agent_id: "fast" },
  events: [],
};
function renderProject(data = manifest) {
  return render(
    <MemoryRouter initialEntries={["/shared/project-link"]}>
      <LanguagePreferenceProvider>
        <Routes>
          <Route
            path="/shared/:shareId"
            element={<SharedProjectPage initialManifest={data} />}
          />
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
afterEach(cleanup);

test("project visitors can change language locally and return focus from the menu", async () => {
  renderProject();
  fireEvent.click(screen.getByRole("button", { name: "Language" }));
  const menu = screen.getByRole("menu", { name: "Language" });
  expect(
    within(menu).getByRole("menuitemradio", { name: "English" }),
  ).toHaveAttribute("aria-checked", "true");
  fireEvent.click(within(menu).getByRole("menuitemradio", { name: "中文" }));
  expect(await screen.findByText("分享的项目")).toBeVisible();
  expect(screen.queryByRole("menu")).toBeNull();
  expect(screen.getByRole("button", { name: "语言" })).toHaveFocus();
  expect(api.updateMetadata).not.toHaveBeenCalled();
});

test("finishing the last page moves owned focus to the first newly added conversation", async () => {
  api.getSharedContent.mockResolvedValueOnce({
    ...manifest,
    sessions: [{ id: "third", name: "Third conversation" }],
    has_more: false,
  });
  renderProject();
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(
    await screen.findByRole("button", { name: "Third conversation" }),
  ).toHaveFocus();
});

test("a pending conversation announces loading and can collapse and reopen without a duplicate read", async () => {
  let finish!: (value: SharedContentResponse) => void;
  api.getSessionContentInProject.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  renderProject();
  const trigger = screen.getByRole("button", { name: "First conversation" });
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  const panel = screen.getByRole("region", { name: "First conversation" });
  expect(within(panel).getByRole("status")).toHaveTextContent(/loading/i);
  expect(trigger).toHaveAttribute("aria-controls", panel.id);
  fireEvent.click(trigger);
  expect(
    screen.queryByRole("region", { name: "First conversation" }),
  ).toBeNull();
  fireEvent.click(trigger);
  expect(api.getSessionContentInProject.mock.calls).toEqual([
    ["project-link", "first"],
  ]);
  await act(async () => finish(content));
  expect(
    within(
      screen.getByRole("region", { name: "First conversation" }),
    ).getByText("No messages"),
  ).toBeVisible();
});

test("an expanded conversation failure has a local retry and keeps its content after collapse", async () => {
  api.getSessionContentInProject.mockRejectedValueOnce(new Error("Offline"));
  let recover!: (value: SharedContentResponse) => void;
  api.getSessionContentInProject.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        recover = resolve;
      }),
  );
  renderProject();
  const trigger = screen.getByRole("button", { name: "First conversation" });
  fireEvent.click(trigger);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Failed to load shared content",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  const panel = screen.getByRole("region", { name: "First conversation" });
  expect(panel).toHaveFocus();
  expect(within(panel).getByRole("status")).toHaveTextContent(/loading/i);
  await act(async () => recover(content));
  expect(within(panel).getByText("No messages")).toBeVisible();
  fireEvent.click(trigger);
  fireEvent.click(trigger);
  expect(
    within(
      screen.getByRole("region", { name: "First conversation" }),
    ).getByText("No messages"),
  ).toBeVisible();
  expect(api.getSessionContentInProject).toHaveBeenCalledTimes(2);
});

test("a late conversation response stays collapsed while a sibling can load independently", async () => {
  let finish!: (value: SharedContentResponse) => void;
  api.getSessionContentInProject.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  api.getSessionContentInProject.mockResolvedValueOnce({
    ...content,
    session: { ...content.session, id: "second" },
  });
  renderProject();
  const first = screen.getByRole("button", { name: "First conversation" });
  fireEvent.click(first);
  fireEvent.click(first);
  fireEvent.click(screen.getByRole("button", { name: "Second conversation" }));
  expect(
    await within(
      screen.getByRole("region", { name: "Second conversation" }),
    ).findByText("No messages"),
  ).toBeVisible();
  await act(async () => finish(content));
  expect(first).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.queryByRole("region", { name: "First conversation" }),
  ).toBeNull();
});

test.each(["offline", "changed-scope"])(
  "pagination failure (%s) keeps the existing list and retries the same page",
  async (failure) => {
    if (failure === "offline")
      api.getSharedContent.mockRejectedValueOnce(new Error("Offline"));
    else api.getSharedContent.mockResolvedValueOnce(content);
    let finish!: (value: SharedProjectContentResponse) => void;
    api.getSharedContent.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    renderProject();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Failed to load shared content",
    );
    expect(
      screen.getByRole("button", { name: "First conversation" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
    expect(screen.getByRole("button", { name: "Load more" })).toBeDisabled();
    await act(async () =>
      finish({
        ...manifest,
        sessions: [{ id: "third", name: "Third conversation" }],
        has_more: false,
      }),
    );
    expect(
      screen.getByRole("button", { name: "Third conversation" }),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
    expect(api.getSharedContent.mock.calls).toEqual([
      ["project-link", { sessionSkip: 2, sessionLimit: 50 }],
      ["project-link", { sessionSkip: 2, sessionLimit: 50 }],
    ]);
    expect(document.activeElement).not.toBe(document.body);
  },
);
