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
        "chat.message.artifactsSubtitleFiles": "1 file",
        "chat.message.copy": "Copy",
        "chat.message.downloadAll": "Download all",
        "chat.message.downloadFailed": "Download failed",
        "chat.message.files": "Files",
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

function openAllFilesPanel(parts: MessagePart[]): void {
  render(<RevealArtifactsSummary parts={parts} />);
  fireEvent.click(screen.getByText("All files").closest('[role="button"]')!);
  const panel = mocks.openPersistentToolPanel.mock.calls.at(-1)?.[0] as
    | { children: ReactNode }
    | undefined;
  if (!panel) throw new Error("All files panel did not open");
  render(<>{panel.children}</>);
}

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
