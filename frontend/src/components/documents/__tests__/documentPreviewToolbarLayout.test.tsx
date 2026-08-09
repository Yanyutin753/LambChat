/** @vitest-environment jsdom */

import { createRef, type ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import { getFileTypeInfo } from "../utils";

test("document preview toolbar enlarges mobile actions beside compressible file info", () => {
  const fileName = "人工智能对大学生的影响（80页）.docx";
  const fileInfo = getFileTypeInfo(fileName);
  const props = {
    t: ((key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key) as ComponentProps<
      typeof DocumentPreviewToolbar
    >["t"],
    data: { content: "preview content", path: fileName },
    copied: false,
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
  const toolbarIcons = toolbar?.querySelectorAll("button svg") ?? [];

  expect(toolbar).toBeInTheDocument();
  expect(toolbar).not.toHaveClass(
    "[&_button>svg]:size-5",
    "sm:[&_button>svg]:size-4",
  );
  expect(fileIcon).toHaveClass("size-8");
  expect(fileInfoBlock).toHaveClass(
    "flex-[0_1_clamp(7rem,28%,12rem)]",
    "min-w-0",
    "overflow-hidden",
  );
  expect(fileInfoBlock).not.toHaveClass("flex-1");
  expect(actionGroup).toHaveClass(
    "document-preview-toolbar-actions",
    "ml-auto",
    "gap-2.5",
    "sm:gap-1",
    "shrink-0",
  );
  expect(toolbarIcons).toHaveLength(8);
  toolbarIcons.forEach((icon) => {
    expect(icon).toHaveAttribute("width", "16");
    expect(icon).toHaveAttribute("height", "16");
  });
});
