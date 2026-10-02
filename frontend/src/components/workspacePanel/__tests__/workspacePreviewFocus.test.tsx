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

const api = vi.hoisted(() => ({ list: vi.fn(), read: vi.fn() }));
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
beforeEach(() => {
  api.list.mockResolvedValue({
    entries: [
      { path: "notes.txt", is_dir: false },
      { path: "other.txt", is_dir: false },
    ],
  });
  api.read.mockResolvedValue({ encoding: "utf-8", content: "preview text" });
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
