/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import type { MessagePart } from "../../../../types";

const mocks = vi.hoisted(() => ({
  exportProjectZip: vi.fn(),
  openPersistentToolPanel: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("../items/persistentToolPanelState", () => ({
  openPersistentToolPanel: mocks.openPersistentToolPanel,
}));
vi.mock("../../../../utils/exportProjectZip", () => ({
  exportProjectZip: mocks.exportProjectZip,
}));
vi.mock("react-hot-toast", () => ({
  default: { error: mocks.toastError },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string | Record<string, unknown>) => {
      const translations: Record<string, string> = {
        "chat.message.allFiles": "All files",
        "chat.message.fileDirectory": "File directory",
        "chat.message.artifactsSubtitleFiles": "1 file",
        "chat.message.copy": "Copy",
        "chat.message.downloadAll": "Download all",
        "chat.message.downloadFailed": "Download failed",
        "chat.message.files": "Files",
        "common.collapse": "Collapse",
        "common.expand": "Expand",
        "project.exportZip": "Export ZIP",
        "project.preview": "Preview",
      };
      return (
        translations[key] ?? (typeof fallback === "string" ? fallback : key)
      );
    },
  }),
}));
vi.mock("../../../common", () => ({ ImageViewer: () => null }));
vi.mock("../ImageWithSkeleton", () => ({
  ImageWithSkeleton: ({ alt }: { alt: string }) => <span>{alt}</span>,
}));

import { RevealArtifactsSummary } from "../RevealArtifactsSummary";

function filePart(input: {
  id: string;
  name: string;
  path: string;
  signedUrl?: string;
}): MessagePart {
  return {
    type: "artifact",
    success: true,
    artifact: {
      kind: "file",
      id: input.id,
      name: input.name,
      path: input.path,
      preview: {
        kind: "file",
        previewKey: input.id,
        filePath: input.path,
        signedUrl: input.signedUrl,
      },
    },
  };
}

const panelProjects: MessagePart[] = Array.from({ length: 3 }, (_, index) => ({
  type: "artifact",
  success: true,
  artifact: {
    kind: "project",
    id: `project:${index}`,
    name: `Project ${index}`,
    mode: "folder",
    fileCount: 0,
    template: "static",
    preview: {
      kind: "project",
      previewKey: `project:${index}`,
      project: {
        version: 1,
        name: `Project ${index}`,
        mode: "folder",
        path: `/project-${index}`,
        template: "static",
        fileCount: 0,
        files: {},
      },
    },
  },
}));

function openAllFilesPanel(parts: MessagePart[]): void {
  const view = render(
    <RevealArtifactsSummary parts={[...parts, ...panelProjects]} />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "All files", exact: true }),
  );
  const panel = mocks.openPersistentToolPanel.mock.calls.at(-1)?.[0] as
    | { children: ReactNode; customHeader?: ReactNode }
    | undefined;
  if (!panel) throw new Error("All files panel did not open");
  view.unmount();
  render(
    <>
      {panel.customHeader}
      {panel.children}
    </>,
  );
}

test("all-files panel uses its tab title and keeps batch download in the toolbar", () => {
  openAllFilesPanel([
    filePart({
      id: "report",
      name: "report.pdf",
      path: "/workspace/report.pdf",
      signedUrl: "/report.pdf",
    }),
  ]);
  const panel = mocks.openPersistentToolPanel.mock.calls.at(-1)![0];
  expect(panel.title).toBe("All files");
  expect(panel.customHeader).toBeTruthy();
  expect(
    screen.getByText("File directory").closest(".tool-console-header"),
  ).toBeTruthy();
  expect(
    screen
      .getByRole("button", { name: "Download all" })
      .closest(".tool-console-header"),
  ).toBeTruthy();
});

test("file-only panel does not repeat the file count as a section heading", () => {
  const parts = Array.from({ length: 4 }, (_, index) =>
    filePart({
      id: `file:${index}`,
      name: `report-${index}.md`,
      path: `/workspace/report-${index}.md`,
    }),
  );
  const view = render(<RevealArtifactsSummary parts={parts} />);
  fireEvent.click(
    screen.getByRole("button", { name: "All files", exact: true }),
  );
  const panel = mocks.openPersistentToolPanel.mock.calls.at(-1)![0];
  view.unmount();
  const { container } = render(<>{panel.children}</>);
  expect(container.textContent).not.toContain("Files");
  expect(screen.getByRole("button", { name: "workspace" })).toBeInTheDocument();
});

afterEach(() => {
  vi.resetAllMocks();
});

test("download-all state lives in the mounted panel and blocks duplicate clicks", async () => {
  let finishDownload: (() => void) | undefined;
  mocks.exportProjectZip.mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        finishDownload = resolve;
      }),
  );
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/report.pdf",
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  const downloadAll = screen.getByRole("button", { name: "Download all" });
  fireEvent.click(downloadAll);

  expect(mocks.exportProjectZip).toHaveBeenCalledTimes(1);
  expect(downloadAll).toBeDisabled();
  fireEvent.click(downloadAll);
  expect(mocks.exportProjectZip).toHaveBeenCalledTimes(1);

  await act(async () => finishDownload?.());
  expect(downloadAll).toBeEnabled();
});

test("folder downloads are real buttons and do not toggle the folder", () => {
  mocks.exportProjectZip.mockResolvedValue(undefined);
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/folder/report.pdf",
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  const folderDownload = screen.getByRole("button", {
    name: "Export ZIP: folder",
  });
  expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();

  fireEvent.click(folderDownload);

  expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();
  expect(mocks.exportProjectZip).toHaveBeenCalledTimes(1);
});

test("folder rows use the shared monochrome folder icon", () => {
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/folder/report.pdf",
    }),
  ]);

  const icon = screen
    .getByRole("button", { name: "workspace" })
    .querySelector("svg");
  expect(icon).toHaveAttribute("viewBox", "0 0 24 24");
  expect(icon).toHaveAttribute("width", "16");
  expect(icon).toHaveClass("lucide-folder");
  expect(icon).toHaveAttribute("fill", "none");
});

test("folder download appears immediately before the expansion chevron", () => {
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/folder/report.pdf",
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  const folderButton = screen.getByRole("button", { name: "folder" });
  const folderDownload = screen.getByRole("button", {
    name: "Export ZIP: folder",
  });
  const folderChevron = screen.getByRole("button", {
    name: "Expand: folder",
  });

  // Tooltip 在按钮外包了一层 display:contents 的 span（不影响布局），
  // 顺序断言走到包装层：展开按钮 → 下载包装 → 折叠箭头包装
  const downloadWrapper = folderDownload.parentElement!;
  const chevronWrapper = folderChevron.parentElement!;

  expect(folderButton.nextElementSibling).toBe(downloadWrapper);
  expect(downloadWrapper.nextElementSibling).toBe(chevronWrapper);
});

test("keeps long nested folder rows inside the panel width boundary", () => {
  const longFolderName = "3cd5f740-c3d3-4556-b1d7-5bb3b601e20a";
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: `/workspace/${longFolderName}/LambChat/report.pdf`,
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  const folderButton = screen.getByRole("button", { name: longFolderName });
  const folderRow = folderButton.parentElement;
  const folderNode = folderRow?.parentElement;
  const panelScroller = folderRow?.closest(".overflow-y-auto");

  expect(folderButton).toHaveClass("!min-w-0", "flex-1");
  expect(panelScroller).toHaveClass(
    "min-w-0",
    "max-w-full",
    "overflow-x-hidden",
  );
  expect(folderNode).toHaveClass("min-w-0", "max-w-full");
  expect(folderRow).toHaveClass("min-w-0", "max-w-full", "overflow-hidden");

  fireEvent.click(folderButton);
  expect(folderRow?.nextElementSibling).toHaveClass("min-w-0", "max-w-full");
  expect(
    screen.getByRole("button", { name: `Export ZIP: ${longFolderName}` }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: `Collapse: ${longFolderName}` }),
  ).toBeInTheDocument();
});

test("folder expansion chevron toggles the folder", () => {
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/folder/report.pdf",
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  fireEvent.click(
    screen.getByRole("button", {
      name: "Expand: folder",
    }),
  );

  expect(screen.getByText("report.pdf")).toBeInTheDocument();
  expect(
    screen.getByRole("button", {
      name: "Collapse: folder",
    }),
  ).toHaveAttribute("aria-expanded", "true");
});

test("does not offer ZIP actions when revealed files have no signed URL", () => {
  openAllFilesPanel([
    filePart({
      id: "file:missing",
      name: "missing.txt",
      path: "/workspace/folder/missing.txt",
    }),
  ]);

  expect(
    screen.queryByRole("button", { name: "Download all" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "workspace" }));
  expect(
    screen.queryByRole("button", { name: "Export ZIP: folder" }),
  ).not.toBeInTheDocument();
});

test("reports ZIP download failures and restores the action", async () => {
  mocks.exportProjectZip.mockRejectedValue(new Error("expired signed URL"));
  openAllFilesPanel([
    filePart({
      id: "file:report",
      name: "report.pdf",
      path: "/workspace/report.pdf",
      signedUrl: "/api/upload/file/report",
    }),
  ]);

  const downloadAll = screen.getByRole("button", { name: "Download all" });
  fireEvent.click(downloadAll);

  await waitFor(() => {
    expect(mocks.toastError).toHaveBeenCalledWith(
      "Download failed: expired signed URL",
    );
  });
  expect(mocks.exportProjectZip).toHaveBeenCalledWith(
    {},
    "All files",
    { "workspace/report.pdf": "/api/upload/file/report" },
    { failOnBinaryError: true },
  );
  expect(downloadAll).toBeEnabled();
});

test("does not silently create a partial ZIP when one signed URL is missing", async () => {
  openAllFilesPanel([
    filePart({
      id: "file:available",
      name: "available.txt",
      path: "/workspace/available.txt",
      signedUrl: "/api/upload/file/available",
    }),
    filePart({
      id: "file:missing",
      name: "missing.txt",
      path: "/workspace/missing.txt",
    }),
  ]);

  fireEvent.click(screen.getByRole("button", { name: "Download all" }));

  await waitFor(() => {
    expect(mocks.toastError).toHaveBeenCalledWith(
      "Download failed: /workspace/missing.txt",
    );
  });
  expect(mocks.exportProjectZip).not.toHaveBeenCalled();
});

test.each([1, 2, 3])(
  "previews %i files inline without an all-files card",
  (count) => {
    const open = vi.fn();
    const parts = Array.from({ length: count }, (_, index) =>
      filePart({
        id: `file:${index}`,
        name: `report-${index}.md`,
        path: `/workspace/report-${index}.md`,
        signedUrl: `/report-${index}.md`,
      }),
    );
    const view = render(
      <RevealArtifactsSummary parts={parts} onOpenPreview={open} />,
    );
    if (count > 1)
      fireEvent.click(view.container.querySelector("button[aria-controls]")!);
    expect(screen.queryByText("All files")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "report-0.md", exact: true }),
    );
    expect(open).toHaveBeenCalledWith(
      expect.objectContaining({ filePath: "/workspace/report-0.md" }),
      "manual",
    );
    expect(
      screen.getAllByRole("button", { name: /documents.downloadFile:/ }),
    ).toHaveLength(count);
  },
);

test("four files open the side panel directly without expanding inline", () => {
  const parts = Array.from({ length: 4 }, (_, index) =>
    filePart({
      id: `file:${index}`,
      name: `report-${index}.md`,
      path: `/workspace/report-${index}.md`,
    }),
  );
  const view = render(<RevealArtifactsSummary parts={parts} />);
  expect(view.container.querySelector("button[aria-controls]")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "report-0.md", exact: true }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "All files", exact: true }),
  );
  expect(mocks.openPersistentToolPanel).toHaveBeenCalledOnce();
});

test("small collections preserve direct project preview", () => {
  const open = vi.fn();
  render(
    <RevealArtifactsSummary parts={[panelProjects[0]]} onOpenPreview={open} />,
  );
  expect(screen.queryByText("All files")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Project 0/ }));
  expect(open).toHaveBeenCalledWith(
    panelProjects[0].type === "artifact"
      ? panelProjects[0].artifact.preview
      : undefined,
    "manual",
  );
});

test("empty and streaming collections render no delivery controls", () => {
  const { container, rerender } = render(<RevealArtifactsSummary parts={[]} />);
  expect(container).toBeEmptyDOMElement();
  rerender(
    <RevealArtifactsSummary
      parts={[
        filePart({ id: "report", name: "report.md", path: "/report.md" }),
      ]}
      isStreaming
    />,
  );
  expect(container).toBeEmptyDOMElement();
});

test("duplicate delivery events do not inflate the summary threshold", () => {
  const part = filePart({
    id: "report",
    name: "report.md",
    path: "/report.md",
  });
  render(<RevealArtifactsSummary parts={[part, part, part, part]} />);
  expect(screen.queryByText("All files")).not.toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: "report.md", exact: true }),
  ).toHaveLength(1);
});

test("small file collections keep batch download without an all-files card", async () => {
  mocks.exportProjectZip.mockResolvedValue(undefined);
  render(
    <RevealArtifactsSummary
      parts={[
        filePart({
          id: "one",
          name: "one.md",
          path: "/one.md",
          signedUrl: "/one.md",
        }),
        filePart({
          id: "two",
          name: "two.csv",
          path: "/two.csv",
          signedUrl: "/two.csv",
        }),
      ]}
    />,
  );
  expect(screen.queryByText("All files")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "1 file", exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "Download all" }));
  await waitFor(() =>
    expect(mocks.exportProjectZip).toHaveBeenCalledWith(
      {},
      "All files",
      { "one.md": "/one.md", "two.csv": "/two.csv" },
      { failOnBinaryError: true },
    ),
  );
});

test("inline attachments show file type metadata and keep separate compact cards", () => {
  render(
    <RevealArtifactsSummary
      parts={[filePart({ id: "brief", name: "brief.md", path: "/brief.md" })]}
      isStreaming={false}
    />,
  );
  expect(screen.getByText("MD")).toBeTruthy();
  expect(
    screen
      .getByRole("button", { name: "brief.md" })
      .closest("[data-inline-attachment]"),
  ).toBeTruthy();
});

test("multiple delivered files expand downward and collapse without opening a panel", () => {
  const parts = ["first.md", "second.csv"].map((name) =>
    filePart({ id: name, name, path: `/${name}` }),
  );
  render(<RevealArtifactsSummary parts={parts} />);
  const disclosure = screen.getByRole("button", { name: "1 file" });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.queryByRole("button", { name: "first.md", exact: true }),
  ).not.toBeInTheDocument();
  fireEvent.click(disclosure);
  expect(disclosure).toHaveAttribute("aria-expanded", "true");
  expect(
    screen.getByRole("button", { name: "first.md", exact: true }),
  ).toBeInTheDocument();
  expect(mocks.openPersistentToolPanel).not.toHaveBeenCalled();
  fireEvent.click(disclosure);
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.queryByRole("button", { name: "first.md", exact: true }),
  ).not.toBeInTheDocument();
});

test("collection folder icon follows its expanded state", () => {
  const parts = [
    filePart({ id: "file:a", name: "a.md", path: "/a.md" }),
    filePart({ id: "file:b", name: "b.md", path: "/b.md" }),
  ];
  const view = render(<RevealArtifactsSummary parts={parts} />);
  const toggle = view.container.querySelector<HTMLButtonElement>(
    "button[aria-controls]",
  )!;
  expect(toggle.querySelector(".lucide-folder-open")).toBeNull();
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(toggle.querySelector(".lucide-folder-open")).not.toBeNull();
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle.querySelector(".lucide-folder-open")).toBeNull();
});
