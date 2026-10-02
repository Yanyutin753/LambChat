/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import appI18n from "../../../i18n";
import { WorkspacePanel } from "../WorkspacePanel";
import type { SandboxFsReadResult } from "../../../services/api/sandboxFs";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  read: vi.fn(),
  reveal: vi.fn(),
}));
vi.mock("../../../services/api/sandboxFs", () => ({
  sandboxFsApi: api,
  sandboxCloudFsApi: api,
  sandboxFsCloudStatusApi: {
    status: vi.fn(async () => ({ state: "running" })),
  },
}));
vi.mock("../../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({
    machines: [],
    online: true,
    currentMachineId: "mac",
  }),
}));
vi.mock("../../../services/tauri/sandboxShell", async (original) => ({
  ...(await original<typeof import("../../../services/tauri/sandboxShell")>()),
  revealWorkspacePath: api.reveal,
}));
beforeEach(() => {
  api.reveal.mockReset().mockResolvedValue(undefined);
  api.list.mockReset().mockResolvedValue({
    entries: [
      { path: "notes.txt", is_dir: false },
      { path: "other.txt", is_dir: false },
    ],
  });
  api.read
    .mockReset()
    .mockResolvedValue({ encoding: "utf-8", content: "preview text" });
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function showWorkspace(narrow = true) {
  return render(
    <I18nextProvider i18n={appI18n.cloneInstance({ lng: "en" })}>
      {narrow && (
        <style>{`.workspace-panel[data-preview="true"][data-show-files="false"] .workspace-explorer { display: none; }`}</style>
      )}
      <button>Another task</button>
      <WorkspacePanel sessionId="session" sandboxMode="local" />
    </I18nextProvider>,
  );
}

async function openNotes() {
  const opener = await screen.findByRole("button", {
    name: "notes.txt",
    exact: true,
  });
  act(() => opener.focus());
  fireEvent.click(opener);
  await screen.findByRole("heading", { name: "notes.txt", exact: true });
  return opener;
}

test("opening a file moves focus out of the hidden mobile explorer into its preview", async () => {
  showWorkspace();
  await openNotes();
  expect(
    screen.getByRole("region", { name: "Preview", exact: true }),
  ).toHaveFocus();
});

test.each(["Back", "Close"])(
  "%s returns focus to the file that opened the preview",
  async (action) => {
    showWorkspace();
    const opener = await openNotes();
    const preview = screen.getByRole("region", {
      name: "Preview",
      exact: true,
    });
    const button = within(preview).getByRole("button", {
      name: action,
      exact: true,
    });
    act(() => button.focus());
    fireEvent.click(button);
    await waitFor(() => expect(opener).toHaveFocus());
  },
);

test("a delayed read does not steal focus from another task", async () => {
  let finish!: (result: SandboxFsReadResult) => void;
  api.read.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  showWorkspace();
  const opener = await screen.findByRole("button", {
    name: "notes.txt",
    exact: true,
  });
  fireEvent.click(opener);
  const other = screen.getByRole("button", { name: "Another task" });
  act(() => other.focus());
  await act(async () => finish({ encoding: "utf-8", content: "preview text" }));
  await screen.findByRole("heading", { name: "notes.txt", exact: true });
  expect(other).toHaveFocus();
});

test("closing an existing preview cancels a later file read without reopening it", async () => {
  showWorkspace(false);
  await openNotes();
  let finish!: (result: SandboxFsReadResult) => void;
  api.read.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "other.txt", exact: true }),
  );
  const preview = screen.getByRole("region", { name: "Preview", exact: true });
  fireEvent.click(
    within(preview).getByRole("button", { name: "Close", exact: true }),
  );
  await act(async () => finish({ encoding: "utf-8", content: "late content" }));
  expect(
    screen.queryByRole("heading", { name: "other.txt", exact: true }),
  ).toBeNull();
  expect(
    screen.getByRole("button", { name: "other.txt", exact: true }),
  ).toHaveAttribute("aria-busy", "false");
});

test("directory retry announces loading, keeps focus and restores the file list", async () => {
  api.list.mockResolvedValueOnce({ error: "Directory unavailable" });
  let finish!: (result: {
    entries: { path: string; is_dir: boolean }[];
  }) => void;
  api.list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  showWorkspace();
  expect(await screen.findByText("Directory unavailable")).toHaveAttribute(
    "role",
    "alert",
  );
  const retry = screen.getByRole("button", { name: "Retry", exact: true });
  act(() => retry.focus());
  fireEvent.click(retry);
  expect(
    screen.getByRole("region", { name: "Conversation files", exact: true }),
  ).toHaveFocus();
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(
    screen.queryByRole("button", { name: "Retry", exact: true }),
  ).toBeNull();
  await act(async () =>
    finish({ entries: [{ path: "notes.txt", is_dir: false }] }),
  );
  expect(
    await screen.findByRole("button", { name: "notes.txt", exact: true }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("closing a file removed by directory refresh returns focus to the explorer", async () => {
  showWorkspace(false);
  await openNotes();
  api.list.mockResolvedValueOnce({
    entries: [{ path: "other.txt", is_dir: false }],
  });
  fireEvent.click(screen.getByRole("button", { name: "Refresh", exact: true }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "notes.txt", exact: true }),
    ).toBeNull(),
  );
  const preview = screen.getByRole("region", { name: "Preview", exact: true });
  const close = within(preview).getByRole("button", {
    name: "Close",
    exact: true,
  });
  act(() => close.focus());
  fireEvent.click(close);
  await waitFor(() =>
    expect(
      screen.getByRole("region", { name: "Conversation files", exact: true }),
    ).toHaveFocus(),
  );
});

test.each(["response", "network"])(
  "a %s failure in an expanded directory is visible and retries in place",
  async (failure) => {
    api.list.mockResolvedValueOnce({
      entries: [{ path: "docs", is_dir: true }],
    });
    if (failure === "response")
      api.list.mockResolvedValueOnce({ error: "Directory unavailable" });
    else api.list.mockRejectedValueOnce(new Error("Directory unavailable"));
    let finish!: (result: {
      entries: { path: string; is_dir: boolean }[];
    }) => void;
    api.list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    showWorkspace();
    const directory = await screen.findByRole("button", {
      name: "docs",
      exact: true,
    });
    fireEvent.click(directory);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Directory unavailable",
    );
    const retry = screen.getByRole("button", {
      name: "Retry: docs",
      exact: true,
    });
    act(() => retry.focus());
    fireEvent.click(retry);
    expect(directory).toHaveFocus();
    expect(directory).toHaveAttribute("aria-expanded", "true");
    expect(directory).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("alert")).toBeNull();
    await act(async () =>
      finish({ entries: [{ path: "docs/notes.txt", is_dir: false }] }),
    );
    expect(
      await screen.findByRole("button", { name: "notes.txt", exact: true }),
    ).toBeVisible();
    expect(directory).toHaveAttribute("aria-busy", "false");
  },
);

test("a failed file read identifies its file and retries without losing the explorer", async () => {
  api.read.mockRejectedValueOnce(new Error("Read unavailable"));
  let finish!: (result: SandboxFsReadResult) => void;
  api.read.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  showWorkspace();
  const file = await screen.findByRole("button", {
    name: "notes.txt",
    exact: true,
  });
  fireEvent.click(file);
  expect(await screen.findByRole("alert")).toHaveTextContent("notes.txt");
  const retry = screen.getByRole("button", {
    name: "Retry: notes.txt",
    exact: true,
  });
  act(() => retry.focus());
  fireEvent.click(retry);
  expect(
    screen.getByRole("region", { name: "Conversation files", exact: true }),
  ).toHaveFocus();
  expect(file).toHaveAttribute("aria-busy", "true");
  expect(screen.queryByRole("alert")).toBeNull();
  await act(async () =>
    finish({ encoding: "utf-8", content: "recovered text" }),
  );
  expect(
    await screen.findByRole("heading", { name: "notes.txt", exact: true }),
  ).toBeVisible();
  expect(
    screen.getByRole("region", { name: "Preview", exact: true }),
  ).toHaveFocus();
});

test("refreshing failed child directories keeps their cached files and clears the local error after recovery", async () => {
  api.list.mockResolvedValueOnce({ entries: [{ path: "docs", is_dir: true }] });
  api.list.mockResolvedValueOnce({
    entries: [{ path: "docs/notes.txt", is_dir: false }],
  });
  showWorkspace(false);
  fireEvent.click(
    await screen.findByRole("button", { name: "docs", exact: true }),
  );
  await screen.findByRole("button", { name: "notes.txt", exact: true });
  api.list.mockResolvedValueOnce({ entries: [{ path: "docs", is_dir: true }] });
  api.list.mockResolvedValueOnce({ error: "Directory unavailable" });
  fireEvent.click(screen.getByRole("button", { name: "Refresh", exact: true }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Directory unavailable",
  );
  expect(
    screen.getByRole("button", { name: "notes.txt", exact: true }),
  ).toBeVisible();
  api.list.mockResolvedValueOnce({ entries: [{ path: "docs", is_dir: true }] });
  api.list.mockResolvedValueOnce({
    entries: [{ path: "docs/updated.txt", is_dir: false }],
  });
  fireEvent.click(screen.getByRole("button", { name: "Refresh", exact: true }));
  expect(
    await screen.findByRole("button", { name: "updated.txt", exact: true }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    screen.getByRole("button", { name: "docs", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
});

test("a successful child refresh cannot erase the root directory error", async () => {
  api.list.mockResolvedValueOnce({ entries: [{ path: "docs", is_dir: true }] });
  api.list.mockResolvedValueOnce({
    entries: [{ path: "docs/notes.txt", is_dir: false }],
  });
  showWorkspace(false);
  fireEvent.click(
    await screen.findByRole("button", { name: "docs", exact: true }),
  );
  await screen.findByRole("button", { name: "notes.txt", exact: true });
  api.list.mockResolvedValueOnce({ error: "Root unavailable" });
  let finish!: (result: {
    entries: { path: string; is_dir: boolean }[];
  }) => void;
  api.list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Refresh", exact: true }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Root unavailable",
  );
  await act(async () =>
    finish({ entries: [{ path: "docs/notes.txt", is_dir: false }] }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Root unavailable");
});

test("global refresh retries an expanded directory that never loaded", async () => {
  api.list.mockResolvedValueOnce({ entries: [{ path: "docs", is_dir: true }] });
  api.list.mockResolvedValueOnce({ error: "Directory unavailable" });
  showWorkspace(false);
  fireEvent.click(
    await screen.findByRole("button", { name: "docs", exact: true }),
  );
  await screen.findByRole("alert");
  api.list.mockResolvedValueOnce({ entries: [{ path: "docs", is_dir: true }] });
  api.list.mockResolvedValueOnce({
    entries: [{ path: "docs/recovered.txt", is_dir: false }],
  });
  fireEvent.click(screen.getByRole("button", { name: "Refresh", exact: true }));
  expect(
    await screen.findByRole("button", { name: "recovered.txt", exact: true }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("file-manager failures retry the original native action without opening a preview", async () => {
  vi.stubGlobal("__TAURI__", {});
  api.reveal.mockRejectedValueOnce(new Error("Native unavailable"));
  render(
    <I18nextProvider i18n={appI18n.cloneInstance({ lng: "en" })}>
      <WorkspacePanel sessionId="session" sandboxMode="local" machineId="mac" />
    </I18nextProvider>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Actions for notes.txt" }),
  );
  fireEvent.click(
    screen.getByRole("menuitem", { name: "Reveal in file manager" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("notes.txt");
  expect(screen.getByRole("alert")).toHaveTextContent(
    appI18n.getFixedT("en")("sessionWorkspace.failed"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry: notes.txt" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(
    screen.getByRole("region", { name: "Conversation files", exact: true }),
  ).toHaveFocus();
  expect(screen.queryByRole("heading", { name: "notes.txt" })).toBeNull();
  expect(api.read).not.toHaveBeenCalled();
  expect(api.reveal).toHaveBeenLastCalledWith(
    "session",
    "notes.txt",
    undefined,
    "mac",
  );
  expect(api.reveal).toHaveBeenCalledTimes(2);
});

test("a file-manager failure from a previous workspace does not replace the new view", async () => {
  vi.stubGlobal("__TAURI__", {});
  let reject!: (error: Error) => void;
  api.reveal.mockImplementationOnce(
    () =>
      new Promise((_, failed) => {
        reject = failed;
      }),
  );
  const renderWorkspace = (sessionId: string) => (
    <I18nextProvider i18n={appI18n.cloneInstance({ lng: "en" })}>
      <WorkspacePanel
        sessionId={sessionId}
        sandboxMode="local"
        machineId="mac"
      />
    </I18nextProvider>
  );
  const { rerender } = render(renderWorkspace("old"));
  fireEvent.click(
    await screen.findByRole("button", { name: "Actions for notes.txt" }),
  );
  fireEvent.click(
    screen.getByRole("menuitem", { name: "Reveal in file manager" }),
  );
  rerender(renderWorkspace("new"));
  await act(async () => reject(new Error("Old workspace failure")));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    screen.getByRole("button", { name: "notes.txt", exact: true }),
  ).toBeVisible();
});
