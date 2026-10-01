/** @vitest-environment jsdom */

import { createRef, type ComponentProps } from "react";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import { vi } from "vitest";
import toast from "react-hot-toast";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import { getFileTypeInfo } from "../utils";

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  vi.clearAllMocks();
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

function renderCopyLinkButton(
  overrides: Partial<ComponentProps<typeof DocumentPreviewToolbar>> = {},
  openMenu = true,
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
    copying: false,
    copyFailed: false,
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
  if (!openMenu) return screen.getByRole("button", { name: "nav.more" });
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  return screen.getByRole("menuitem", { name: "Copy link" });
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

test("compact file actions stay available in the menu and Escape returns focus", () => {
  renderCopyLinkButton(
    { resolvedUrl: "https://example.test/file.docx" },
    false,
  );
  const trigger = screen.getByRole("button", { name: "nav.more" });
  fireEvent.click(trigger);
  expect(
    screen.getByRole("menuitem", { name: "Copy link" }),
  ).toBeInTheDocument();
  const closePanel = vi.fn();
  document.addEventListener("keydown", closePanel);
  fireEvent.keyDown(document, { key: "Escape" });
  document.removeEventListener("keydown", closePanel);
  expect(closePanel).not.toHaveBeenCalled();
  expect(screen.queryByRole("menu")).toBeNull();
  expect(trigger).toHaveFocus();
});

test("preview menu is named, focuses its first action and supports arrow navigation", () => {
  renderCopyLinkButton({ resolvedUrl: "https://example.test/file.docx" });
  expect(screen.getByRole("menu", { name: "nav.more" })).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Center view" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
  expect(
    screen.getByRole("menuitem", { name: "documents.fullscreen" }),
  ).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "End" });
  expect(screen.getByRole("menuitem", { name: "Copy link" })).toHaveFocus();
});

test("copy link cannot be repeated while its clipboard request is pending", async () => {
  let complete!: () => void;
  writeText.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  fireEvent.click(
    renderCopyLinkButton({ resolvedUrl: "https://example.test/file.docx" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  expect(screen.getByRole("menuitem", { name: "Copy link" })).toBeDisabled();
  await act(async () => complete());
  expect(screen.getByRole("menuitem", { name: "Copy link" })).toBeEnabled();
});

test("copy link reports rejection and retries the same absolute URL", async () => {
  writeText
    .mockRejectedValueOnce(new Error("Permission denied"))
    .mockResolvedValueOnce(undefined);
  fireEvent.click(
    renderCopyLinkButton({ resolvedUrl: "https://example.test/file.docx" }),
  );
  await waitFor(() => expect(toast.error).toHaveBeenCalledOnce());
  expect(toast.success).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "nav.more" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Copy link" }));
  await waitFor(() => expect(toast.success).toHaveBeenCalledOnce());
  expect(writeText).toHaveBeenLastCalledWith("https://example.test/file.docx");
});
