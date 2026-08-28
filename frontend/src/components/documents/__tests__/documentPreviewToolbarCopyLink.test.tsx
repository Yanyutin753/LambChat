/** @vitest-environment jsdom */

import { createRef, type ComponentProps } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { vi } from "vitest";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import { getFileTypeInfo } from "../utils";

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn() },
}));

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  writeText.mockClear();
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

function renderCopyLinkButton(
  overrides: Partial<ComponentProps<typeof DocumentPreviewToolbar>> = {},
) {
  const fileName = "2d1d8bc2b6d44047.docx";
  const fileInfo = getFileTypeInfo(fileName);
  const props = {
    t: ((key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key) as ComponentProps<
      typeof DocumentPreviewToolbar
    >["t"],
    data: { content: "", path: fileName },
    copied: false,
    viewSource: false,
    isSidebar: true,
    isFullscreen: false,
    markdownFile: false,
    codeFile: false,
    hasTextContent: false,
    displaySize: 0,
    fileSize: 279347,
    fileName,
    language: "",
    fileInfo,
    Icon: fileInfo.icon,
    s3Key: `document/6999be7275bdd6b1d868075b/${fileName}`,
    signedUrl: undefined,
    externalImageUrl: undefined,
    resolvedUrl: null,
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
    ...overrides,
  } satisfies ComponentProps<typeof DocumentPreviewToolbar>;

  render(<DocumentPreviewToolbar {...props} />);
  return screen.getByTitle("Copy link");
}

test("copy link writes an absolute URL when resolvedUrl is a relative upload path", async () => {
  const relativePath =
    "/api/upload/file/document/6999be7275bdd6b1d868075b/2d1d8bc2b6d44047.docx";
  const button = renderCopyLinkButton({ resolvedUrl: relativePath });

  await act(async () => {
    fireEvent.click(button);
  });

  expect(writeText).toHaveBeenCalledWith(
    `${window.location.origin}${relativePath}`,
  );
});

test("copy link keeps absolute URLs unchanged", async () => {
  const button = renderCopyLinkButton({
    resolvedUrl: "https://example.test/file.docx",
  });

  await act(async () => {
    fireEvent.click(button);
  });

  expect(writeText).toHaveBeenCalledWith("https://example.test/file.docx");
});
