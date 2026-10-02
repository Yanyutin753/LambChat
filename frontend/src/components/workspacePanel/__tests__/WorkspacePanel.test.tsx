/** @vitest-environment jsdom */
import {
  render as rtlRender,
  screen,
  fireEvent,
  cleanup,
  act,
  waitFor,
} from "@testing-library/react";
import { expect, test, vi, afterEach } from "vitest";
import { WorkspacePanel } from "../WorkspacePanel";
import {
  sandboxFsApi,
  sandboxCloudFsApi,
} from "../../../services/api/sandboxFs";
import { type ReactNode } from "react";
import { RevealPreviewHost } from "../../chat/ChatMessage/items/RevealPreviewHost";
import {
  clearRevealPreviewTabs,
  getRevealPreviewTabs,
  setActiveRevealPreviewState,
} from "../../chat/ChatMessage/items/activeRevealPreviewStore";
import { RightPanelActiveContext } from "../../common/useRightPanelEntry";
const render: typeof rtlRender = (ui, options) =>
  rtlRender(ui, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <>
        {children}
        <RevealPreviewHost
          preview={null}
          onClose={() => setActiveRevealPreviewState(null)}
        />
      </>
    ),
    ...options,
  });
afterEach(() => {
  cleanup();
  clearRevealPreviewTabs();
  vi.useRealTimers();
});
const status = vi.hoisted(() => ({ online: true }));
const read = vi.hoisted(() => vi.fn());
const cloudStatus = vi.hoisted(() =>
  vi.fn(async () => ({ state: "disabled" })),
);
const treeHook = vi.hoisted(() => vi.fn());
const tree = vi.hoisted(() => ({
  root: [] as { path: string; name: string; isDir: boolean }[],
  state: "ready",
  error: null,
  expandedPaths: new Set(),
  refresh: vi.fn(),
}));
vi.mock("../../documents/LazyDocumentPreview", () => ({
  LazyDocumentPreview: ({
    content,
    onClose,
    signedUrl,
    footer,
  }: {
    content: string;
    signedUrl?: string;
    footer?: ReactNode;
    onClose?: () => void;
  }) => (
    <div>
      {content || signedUrl}
      {footer}
      {onClose && <button onClick={onClose}>Back to files</button>}
    </div>
  ),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../hooks/useSandboxStatus", () => ({
  useSandboxStatus: () => ({
    machines: [],
    currentMachineId: "mac",
    online: status.online,
  }),
}));
vi.mock("../../../hooks/useWorkspaceTree", () => ({
  useWorkspaceTree: (...args: unknown[]) => {
    treeHook(...args);
    return tree;
  },
}));
vi.mock("../../../services/api/sandboxFs", () => ({
  sandboxFsApi: { read },
  sandboxCloudFsApi: { read },
  sandboxFsCloudStatusApi: { status: cloudStatus },
}));

test("files follow the conversation without local/cloud controls", () => {
  const { rerender } = render(
    <WorkspacePanel sessionId="s" sandboxMode="cloud" />,
  );
  expect(
    screen.queryByRole("button", { name: "workspacePanel.viewCloud" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "workspacePanel.viewLocal" }),
  ).toBeNull();
  expect(treeHook.mock.lastCall?.[2]).toBe(sandboxCloudFsApi);
  rerender(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  expect(treeHook.mock.lastCall?.[2]).toBe(sandboxFsApi);
});

test("a legacy view preference cannot override the conversation default", () => {
  localStorage.setItem("lambchat_workspace_view", "local");
  render(<WorkspacePanel sessionId="s" />);
  expect(treeHook.mock.lastCall?.[2]).toBe(sandboxCloudFsApi);
  localStorage.removeItem("lambchat_workspace_view");
});

test("cloud files remain visible when no local daemon is online", () => {
  status.online = false;
  render(<WorkspacePanel sessionId="s" sandboxMode="cloud" />);
  expect(screen.getByText("workspacePanel.emptyDir")).toBeVisible();
  status.online = true;
});

test("failed file reads show a visible error", async () => {
  tree.root = [{ path: "readme.md", name: "readme.md", isDir: false }];
  read.mockResolvedValue({ error: "permission_denied" });
  render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  fireEvent.click(screen.getByRole("button", { name: "readme.md" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("documents.error");
  tree.root = [];
});

test("a file read from the previous view cannot reopen a preview", async () => {
  tree.root = [{ path: "readme.md", name: "readme.md", isDir: false }];
  let finish!: (value: unknown) => void;
  read.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { rerender } = render(
    <WorkspacePanel sessionId="s" sandboxMode="local" />,
  );
  fireEvent.click(screen.getByRole("button", { name: "readme.md" }));
  rerender(<WorkspacePanel sessionId="s" sandboxMode="cloud" />);
  await act(async () =>
    finish({ encoding: "utf-8", content: "old workspace content" }),
  );
  expect(screen.queryByText("old workspace content")).toBeNull();
  tree.root = [];
});

test("cloud status polling does not reset the file tree or wake paused sandboxes", async () => {
  vi.useFakeTimers();
  cloudStatus
    .mockResolvedValueOnce({ state: "running" })
    .mockResolvedValueOnce({ state: "paused" });
  render(<WorkspacePanel sessionId="s" sandboxMode="cloud" />);
  await act(async () => {});
  const resetKey = treeHook.mock.lastCall?.[1];
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_000);
  });
  expect(treeHook.mock.lastCall?.[1]).toBe(resetKey);
  vi.useRealTimers();
});

test("file previews provide a direct return to the conversation file list", async () => {
  tree.root = [{ path: "readme.md", name: "readme.md", isDir: false }];
  read.mockResolvedValue({ encoding: "utf-8", content: "preview content" });
  render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  fireEvent.click(screen.getByRole("button", { name: "readme.md" }));
  fireEvent.click(await screen.findByRole("button", { name: "Back to files" }));
  expect(screen.queryByText("preview content")).toBeNull();
  expect(screen.getByRole("button", { name: "readme.md" })).toBeVisible();
  tree.root = [];
});

test("opening another file reuses the workspace preview without creating global tabs", async () => {
  tree.root = [
    { path: "a.txt", name: "a.txt", isDir: false },
    { path: "b.txt", name: "b.txt", isDir: false },
  ];
  read.mockImplementation(async (_session, path) => ({
    encoding: "utf-8",
    content: `content of ${path}`,
  }));
  render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  fireEvent.click(screen.getByRole("button", { name: "a.txt" }));
  await screen.findByText("content of a.txt");
  expect(screen.getByRole("button", { name: "a.txt" })).toHaveAttribute(
    "aria-current",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "b.txt" }));
  await screen.findByText("content of b.txt");
  expect(screen.queryByText("content of a.txt")).toBeNull();
  expect(getRevealPreviewTabs()).toHaveLength(0);
  tree.root = [];
});

test("hidden workspace pauses cloud polling and refreshes on return", async () => {
  vi.useFakeTimers();
  cloudStatus.mockClear();
  const { rerender } = render(
    <RightPanelActiveContext value={true}>
      <WorkspacePanel sessionId="s" />
    </RightPanelActiveContext>,
  );
  await act(async () => {});
  rerender(
    <RightPanelActiveContext value={false}>
      <WorkspacePanel sessionId="s" />
    </RightPanelActiveContext>,
  );
  const calls = cloudStatus.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(cloudStatus).toHaveBeenCalledTimes(calls);
  rerender(
    <RightPanelActiveContext value={true}>
      <WorkspacePanel sessionId="s" />
    </RightPanelActiveContext>,
  );
  await act(async () => {});
  expect(cloudStatus).toHaveBeenCalledTimes(calls + 1);
});

test("workspace refresh shares the title bar instead of adding a separate row", () => {
  const header = document.createElement("header");
  document.body.appendChild(header);
  const view = render(
    <WorkspacePanel
      sessionId="s"
      sandboxMode="local"
      headerActionsTarget={header}
    />,
  );
  const refresh = screen.getByRole("button", {
    name: "workspacePanel.refresh",
  });
  expect(header.contains(refresh)).toBe(true);
  expect(view.container.contains(refresh)).toBe(false);
  tree.refresh.mockClear();
  fireEvent.click(refresh);
  expect(tree.refresh).toHaveBeenCalledOnce();
  view.unmount();
  expect(header.childElementCount).toBe(0);
  header.remove();
});

test("binary file bytes reach the document renderer through a downloadable URL", async () => {
  tree.root = [{ path: "photo.png", name: "photo.png", isDir: false }];
  read.mockResolvedValue({ encoding: "base64", content: "aGVsbG8=" });
  render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  fireEvent.click(screen.getByRole("button", { name: "photo.png" }));
  expect(
    await screen.findByText("data:application/octet-stream;base64,aGVsbG8="),
  ).toBeVisible();
  tree.root = [];
});

test("a paginated text read clearly identifies its partial preview", async () => {
  tree.root = [{ path: "large.py", name: "large.py", isDir: false }];
  read.mockResolvedValue({
    encoding: "utf-8",
    content: "first page",
    next_offset: 2000,
  });
  render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  fireEvent.click(screen.getByRole("button", { name: "large.py" }));
  expect(await screen.findByText("documents.fileTooLargeLines")).toBeVisible();
  tree.root = [];
});

test("the workspace root collapses the file tree", () => {
  tree.root = [{ path: "notes.txt", name: "notes.txt", isDir: false }];
  render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
  fireEvent.click(screen.getByRole("button", { name: "workspacePanel.root" }));
  expect(
    screen.getByRole("button", { name: "notes.txt", hidden: true }),
  ).not.toBeVisible();
  tree.root = [];
});

const clipboard = vi.hoisted(() => ({
  copy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("../../../utils/clipboard", () => ({
  copyToClipboard: clipboard.copy,
}));
vi.mock("react-hot-toast", () => ({
  default: { success: clipboard.success, error: clipboard.error },
}));

test("file action Escape returns focus to its actual trigger and ignores IME", () => {
  tree.root = [{ path: "notes.txt", name: "notes.txt", isDir: false }];
  try {
    render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
    const trigger = screen.getByRole("button", { name: "notes.txt" });
    fireEvent.contextMenu(trigger);
    const item = screen.getByRole("menuitem", {
      name: "workspacePanel.copyPath",
    });
    fireEvent.keyDown(item, { key: "Escape", isComposing: true });
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(item, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveFocus();
  } finally {
    tree.root = [];
  }
});

test("pending path copy survives menu dismissal and reports confirmed success", async () => {
  clipboard.copy.mockClear();
  clipboard.success.mockClear();
  let complete!: () => void;
  clipboard.copy.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  tree.root = [{ path: "notes.txt", name: "notes.txt", isDir: false }];
  try {
    render(<WorkspacePanel sessionId="s" sandboxMode="local" />);
    const trigger = screen.getByRole("button", { name: "notes.txt" });
    fireEvent.contextMenu(trigger);
    fireEvent.click(
      screen.getByRole("menuitem", { name: "workspacePanel.copyPath" }),
    );
    fireEvent.contextMenu(trigger);
    expect(
      screen.getByRole("menuitem", { name: "workspacePanel.copyPath" }),
    ).toBeDisabled();
    expect(clipboard.success).not.toHaveBeenCalled();
    await act(async () => complete());
    await waitFor(() => expect(clipboard.success).toHaveBeenCalledOnce());
    expect(clipboard.copy).toHaveBeenCalledWith("notes.txt");
    expect(
      screen.getByRole("menuitem", { name: "workspacePanel.copyPath" }),
    ).toBeEnabled();
  } finally {
    tree.root = [];
  }
});

test("cloud file paths copy directly without opening a single-action menu", async () => {
  tree.root = [{ path: "readme.md", name: "readme.md", isDir: false }];
  clipboard.copy.mockReset().mockResolvedValue(undefined);
  try {
    render(<WorkspacePanel sessionId="s" sandboxMode="cloud" />);
    expect(
      screen.queryByRole("button", { name: "workspacePanel.fileActions" }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "workspacePanel.copyPath" }),
    );
    await waitFor(() =>
      expect(clipboard.copy).toHaveBeenCalledExactlyOnceWith("readme.md"),
    );
    expect(screen.queryByRole("menu")).toBeNull();
  } finally {
    tree.root = [];
  }
});

test.each(["success", "error"])(
  "direct path copy preserves %s feedback when its row disappears",
  async (outcome) => {
    clipboard.copy.mockReset();
    clipboard.success.mockClear();
    clipboard.error.mockClear();
    let finish!: () => void;
    clipboard.copy.mockImplementationOnce(
      () =>
        new Promise<void>((resolve, reject) => {
          finish = () =>
            outcome === "success"
              ? resolve()
              : reject(new Error("Permission denied"));
        }),
    );
    tree.root = [{ path: "notes.txt", name: "notes.txt", isDir: false }];
    try {
      render(<WorkspacePanel sessionId="s" sandboxMode="cloud" />);
      fireEvent.click(
        screen.getByRole("button", { name: "workspacePanel.copyPath" }),
      );
      fireEvent.change(screen.getByRole("textbox"), {
        target: { value: "different-file" },
      });
      expect(
        screen.queryByRole("button", { name: "workspacePanel.copyPath" }),
      ).toBeNull();
      await act(async () => finish());
      await waitFor(() => expect(clipboard[outcome]).toHaveBeenCalledOnce());
      expect(clipboard.copy).toHaveBeenCalledWith("notes.txt");
    } finally {
      tree.root = [];
    }
  },
);
