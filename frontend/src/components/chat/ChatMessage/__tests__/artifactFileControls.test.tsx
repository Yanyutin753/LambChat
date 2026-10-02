/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { type ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { FileTreeView } from "../items/FileTreeView";
import { RevealArtifactsSummary } from "../RevealArtifactsSummary";
import {
  captureActiveSidebarPanelSnapshot,
  clearSidebarPanelSnapshots,
  registerActiveSidebarSnapshotTarget,
  queueSidebarPanelSnapshot,
  restorePendingSidebarPanelSnapshot,
} from "../items/sidebarPanelSnapshot";

const mocks = vi.hoisted(() => ({
  copy: vi.fn(),
  zip: vi.fn(),
  panel: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("../../../../utils/clipboard", () => ({ copyToClipboard: mocks.copy }));
vi.mock("../../../../utils/exportProjectZip", () => ({
  exportProjectZip: mocks.zip,
}));
vi.mock("../items/persistentToolPanelState", () => ({
  openPersistentToolPanel: mocks.panel,
}));
vi.mock("react-hot-toast", () => ({
  default: { success: mocks.success, error: mocks.error },
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(() => {
  cleanup();
  clearSidebarPanelSnapshots();
});

test("project text file size reports UTF-8 bytes for Chinese and emoji", () => {
  render(
    <FileTreeView
      files={{ "report.md": "你好🌱" }}
      binaryFiles={{}}
      showHeader={false}
    />,
  );
  expect(
    screen.getByRole("button", { name: "report.md", exact: true }),
  ).toHaveTextContent("10 B");
});

test.each(["project", "summary"])(
  "%s directory expansion survives panel state restoration",
  async (kind) => {
    let root: HTMLElement;
    if (kind === "project") {
      root = render(
        <FileTreeView
          files={{ "/src/report.md": "# Delivery" }}
          binaryFiles={{}}
          showHeader={false}
        />,
      ).container;
    } else {
      render(
        <RevealArtifactsSummary
          parts={[
            {
              type: "artifact",
              success: true,
              artifact: {
                kind: "file",
                id: "report",
                name: "report.md",
                path: "/src/report.md",
                preview: {
                  kind: "file",
                  previewKey: "report",
                  filePath: "/src/report.md",
                  signedUrl: "/preview-document.md",
                },
              },
            },
          ]}
        />,
      );
      fireEvent.click(
        screen.getByRole("button", { name: /chat.message.allFiles/ }),
      );
      const panel = mocks.panel.mock.calls.at(-1)?.[0] as {
        children: ReactNode;
      };
      root = render(<>{panel.children}</>).container;
    }
    registerActiveSidebarSnapshotTarget(`tree:${kind}`, root);
    const folder = screen.getByText("src").closest("button")!;
    fireEvent.click(folder);
    const snapshot = captureActiveSidebarPanelSnapshot();
    fireEvent.click(folder);
    expect(folder).toHaveAttribute("aria-expanded", "false");
    queueSidebarPanelSnapshot(snapshot);
    await act(async () => {
      await restorePendingSidebarPanelSnapshot(`tree:${kind}`, root);
    });
    expect(folder).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: "report.md", exact: true }),
    ).toBeVisible();
  },
);

function showFiles(kind: string) {
  const open = vi.fn();
  if (kind === "project") {
    render(
      <FileTreeView
        files={{ "/report.md": "# Delivery" }}
        binaryFiles={{}}
        onFileClick={open}
        showHeader={false}
      />,
    );
  } else {
    render(
      <RevealArtifactsSummary
        onOpenPreview={open}
        parts={[
          {
            type: "artifact",
            success: true,
            artifact: {
              kind: "file",
              id: "report",
              name: "report.md",
              path: "/report.md",
              preview: {
                kind: "file",
                previewKey: "report",
                filePath: "/report.md",
                signedUrl: "/preview-document.md",
              },
            },
          },
        ]}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /chat.message.allFiles/ }),
    );
    const panel = mocks.panel.mock.calls.at(-1)?.[0] as { children: ReactNode };
    render(<>{panel.children}</>);
  }
  return open;
}

test.each(["project", "summary"])(
  "%s file actions are independent native controls",
  (kind) => {
    const open = showFiles(kind);
    const preview = screen.getByRole("button", {
      name: "report.md",
      exact: true,
    });
    const download = screen.getByRole("button", {
      name: "documents.downloadFile: report.md",
    });
    const copy = screen.getByRole("button", { name: "chat.message.copy" });
    expect(download.tagName).toBe("BUTTON");
    expect(copy.tagName).toBe("BUTTON");
    expect(preview.querySelector("button,[role=button]")).toBeNull();
    expect(download.closest("button")).toBe(download);
    expect(copy.closest("button")).toBe(copy);
    mocks.copy.mockResolvedValue(undefined);
    fireEvent.click(copy);
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(preview);
    expect(open).toHaveBeenCalledOnce();
  },
);

test.each(["project", "summary"])(
  "%s file copying waits for confirmation and recovers after failure",
  async (kind) => {
    let reject!: (reason: Error) => void;
    mocks.copy.mockImplementationOnce(
      () =>
        new Promise<void>((_, fail) => {
          reject = fail;
        }),
    );
    showFiles(kind);
    const copy = screen.getByRole("button", { name: "chat.message.copy" });
    fireEvent.click(copy);
    expect(copy).toBeDisabled();
    expect(copy).toHaveAttribute("aria-busy", "true");
    expect(mocks.success).not.toHaveBeenCalled();
    await act(async () => reject(new Error("Unavailable")));
    expect(copy).toBeEnabled();
    expect(mocks.error).toHaveBeenCalledWith(
      "chat.message.copyFailed",
      expect.objectContaining({ id: expect.any(String) }),
    );
    mocks.copy.mockResolvedValueOnce(undefined);
    fireEvent.click(copy);
    await screen.findByRole("button", { name: "chat.message.copied" });
    expect(mocks.copy).toHaveBeenLastCalledWith(
      kind === "project" ? "# Delivery" : "/preview-document.md",
    );
  },
);

test("project directory ZIP waits without toggling and reports failure", async () => {
  let reject!: (reason: Error) => void;
  mocks.zip.mockImplementationOnce(
    () =>
      new Promise<void>((_, fail) => {
        reject = fail;
      }),
  );
  render(
    <FileTreeView
      files={{ "/src/report.md": "# Delivery" }}
      binaryFiles={{}}
      showHeader={false}
    />,
  );
  const folder = screen.getByRole("button", { name: "src", exact: true });
  const download = screen.getByRole("button", {
    name: "project.downloadFolder: src",
  });
  fireEvent.click(download);
  expect(folder).toHaveAttribute("aria-expanded", "false");
  expect(download).toBeDisabled();
  fireEvent.click(download);
  expect(mocks.zip).toHaveBeenCalledOnce();
  await act(async () => reject(new Error("expired URL")));
  expect(download).toBeEnabled();
  expect(mocks.error).toHaveBeenCalledWith("chat.message.downloadFailed");
  expect(mocks.zip).toHaveBeenCalledWith(
    { "/src/report.md": "# Delivery" },
    "src",
    {},
    { failOnBinaryError: true },
  );
});

test("project export waits and restores its action on failure", async () => {
  let reject!: (reason: Error) => void;
  mocks.zip.mockImplementationOnce(
    () =>
      new Promise<void>((_, fail) => {
        reject = fail;
      }),
  );
  render(
    <FileTreeView
      files={{ "/report.md": "# Delivery" }}
      binaryFiles={{}}
      projectName="Delivery"
    />,
  );
  const download = screen.getByRole("button", { name: "project.exportZip" });
  fireEvent.click(download);
  expect(download).toBeDisabled();
  await act(async () => reject(new Error("expired URL")));
  expect(download).toBeEnabled();
  expect(mocks.error).toHaveBeenCalledWith("chat.message.downloadFailed");
});

test("relative project paths retain their content and binary identity", async () => {
  mocks.copy.mockResolvedValue(undefined);
  const open = vi.fn();
  render(
    <FileTreeView
      files={{ "report.md": "# Delivery" }}
      binaryFiles={{ "logo.png": "/preview-image.png" }}
      onFileClick={open}
      showHeader={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.message.copy" }));
  await waitFor(() => expect(mocks.copy).toHaveBeenCalledWith("# Delivery"));
  fireEvent.click(
    screen.getByRole("button", { name: "logo.png", exact: true }),
  );
  expect(open).toHaveBeenLastCalledWith(
    expect.objectContaining({
      path: "logo.png",
      isBinary: true,
      url: "/preview-image.png",
    }),
  );
});

test("a relative text filename does not inherit binary identity from Object.prototype", async () => {
  mocks.copy.mockResolvedValue(undefined);
  const open = vi.fn();
  render(
    <FileTreeView
      files={{ constructor: "plain text" }}
      binaryFiles={{}}
      onFileClick={open}
      showHeader={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.message.copy" }));
  await waitFor(() => expect(mocks.copy).toHaveBeenCalledWith("plain text"));
  fireEvent.click(
    screen.getByRole("button", { name: "constructor", exact: true }),
  );
  expect(open).toHaveBeenCalledWith(
    expect.objectContaining({ path: "constructor", isBinary: false }),
  );
});

test("a file without a download URL keeps its preview and path copy available", () => {
  render(
    <RevealArtifactsSummary
      parts={[
        {
          type: "artifact",
          success: true,
          artifact: {
            kind: "file",
            id: "missing",
            name: "missing.txt",
            path: "/missing.txt",
            preview: {
              kind: "file",
              previewKey: "missing",
              filePath: "/missing.txt",
            },
          },
        },
      ]}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /chat.message.allFiles/ }),
  );
  const panel = mocks.panel.mock.calls.at(-1)?.[0] as { children: ReactNode };
  render(<>{panel.children}</>);
  expect(
    screen.getByRole("button", { name: "documents.downloadFile: missing.txt" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "chat.message.copy" }),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "missing.txt", exact: true }),
  ).toBeEnabled();
});
