/** @vitest-environment jsdom */

import { createRef, type ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import { getFileTypeInfo } from "../utils";

test("document preview toolbar gives the file title flexible space and groups actions with dividers", () => {
  const fileName = "人工智能对大学生的影响（80页）.docx";
  const fileInfo = getFileTypeInfo(fileName);
  const props = {
    t: ((key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key) as ComponentProps<
      typeof DocumentPreviewToolbar
    >["t"],
    data: { content: "preview content", path: fileName },
    copied: false,
    copying: false,
    copyFailed: false,
    viewSource: false,
    isSidebar: true,
    isFullscreen: false,
    markdownFile: true,
    codeFile: false,
    hasTextContent: false,
    displaySize: 0,
    fileSize: 279347,
    fileName,
    language: "",
    fileInfo,
    Icon: fileInfo.icon,
    s3Key: "documents/file.docx",
    signedUrl: undefined,
    externalImageUrl: undefined,
    resolvedUrl: "https://example.test/file.docx",
    unsupportedPreviewFile: false,
    onUserInteraction: undefined,
    onClose: vi.fn(),
    effectiveOnBack: vi.fn(),
    handleCopy: vi.fn(),
    handleDownload: vi.fn(),
    toolbarRef: createRef<HTMLDivElement>(),
    panelRef: createRef<HTMLDivElement>(),
    setViewSource: vi.fn(),
    setViewMode: vi.fn(),
    handleFullscreenToggle: vi.fn(),
    exitFullscreen: vi.fn(),
  } satisfies ComponentProps<typeof DocumentPreviewToolbar>;

  render(<DocumentPreviewToolbar {...props} />);

  const title = screen.getByTitle(fileName);
  const toolbar = title.closest(".document-preview-toolbar");
  const fileInfoBlock = title.parentElement;
  const fileIcon = fileInfoBlock?.previousElementSibling;
  const actionGroup = fileInfoBlock?.nextElementSibling;

  expect(toolbar).toBeInTheDocument();
  expect(toolbar).not.toHaveClass(
    "[&_button>svg]:size-5",
    "sm:[&_button>svg]:size-4",
  );
  expect(fileIcon).toHaveClass("document-preview-header-icon", props.fileInfo.color);
  expect(fileIcon).toHaveAttribute("width", "16");
  expect(fileIcon).toHaveAttribute("height", "16");
  expect(fileInfoBlock).toHaveClass(
    "document-preview-file-info",
    "flex-1",
    "min-w-0",
    "overflow-hidden",
  );
  expect(fileInfoBlock).not.toHaveClass("flex-[0_1_clamp(7rem,28%,12rem)]");
  // Meta line keeps a single stable size instead of a tiny mobile-only scale.
  expect(fileInfoBlock?.querySelector(".text-10")).toBeNull();
  expect(actionGroup).toHaveClass(
    "document-preview-toolbar-actions",
    "ml-auto",
    "gap-1",
    "shrink-0",
  );
  expect(actionGroup?.querySelectorAll("button")).toHaveLength(3);
  expect(screen.queryByTitle("Copy link")).toBeNull();
  expect(
    screen.getByRole("button", { name: "documents.source" }),
  ).toHaveTextContent(/^$/);
  fireEvent.click(screen.getByRole("button", { name: "documents.source" }));
  expect(props.setViewSource).toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByTitle("documents.download"));
  expect(props.handleDownload).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Center view" }));
  expect(props.setViewMode).toHaveBeenCalledWith("center");
  expect(screen.queryByRole("menu")).toBeNull();
});
