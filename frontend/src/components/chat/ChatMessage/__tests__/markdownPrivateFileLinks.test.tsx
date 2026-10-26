/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MarkdownContent } from "../MarkdownContent";
import {
  clearRevealPreviewTabs,
  getActiveRevealPreviewState,
} from "../items/activeRevealPreviewStore";
import { setStoredServerUrl } from "../../../../services/api/serverConfig";
vi.mock("../../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
afterEach(() => {
  cleanup();
  clearRevealPreviewTabs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

test("extensionless upload links use authenticated preview instead of raw navigation", () => {
  render(
    <MarkdownContent content="[Download](/api/upload/file/uploads/opaque-key)" />,
  );
  fireEvent.click(screen.getByRole("link", { name: "Download" }));
  expect(getActiveRevealPreviewState()?.request).toMatchObject({
    kind: "file",
    signedUrl: `${window.location.origin}/api/upload/file/uploads/opaque-key`,
  });
});

test("native backend video links use the same authenticated document preview", () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  setStoredServerUrl("https://chat.example");
  render(
    <MarkdownContent content="[Video](https://chat.example/api/upload/file/uploads/video.mp4)" />,
  );
  fireEvent.click(screen.getByRole("link", { name: "Video" }));
  expect(getActiveRevealPreviewState()?.request).toMatchObject({
    kind: "file",
    signedUrl: "https://chat.example/api/upload/file/uploads/video.mp4",
  });
});

test.each(["）", "（新增第 5 节差异说明）"])(
  "bare upload links exclude trailing Chinese prose %s from the download address",
  (suffix) => {
    const url = `${window.location.origin}/api/upload/file/revealed_files/report.md`;
    render(<MarkdownContent content={`文档：${url}${suffix}`} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveTextContent(url);
    expect(link.textContent).not.toContain("（");
    expect(link.textContent).not.toContain("）");
    expect(link.parentElement).toHaveTextContent(`文档：${url}${suffix}`);
    fireEvent.click(link);
    expect(getActiveRevealPreviewState()?.request.signedUrl).toBe(url);
  },
);

test.each([
  ["explicit", "[原文](URL（备份）)", "URL（备份）"],
  ["encoded", "URL%EF%BC%89", "URL%EF%BC%89"],
  ["filename", "URL", "URL"],
  ["query", "URL?label=（备份）", "URL?label=（备份）"],
])(
  "preserves %s upload link filenames and explicit addresses",
  (_name, content, href) => {
    const url = `${window.location.origin}/api/upload/file/revealed_files/报告（终版）.md`;
    render(<MarkdownContent content={content.replace("URL", url)} />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      new URL(href.replace("URL", url)).href,
    );
  },
);

test("does not rewrite foreign autolinks or code containing upload URLs", () => {
  const foreign =
    "https://foreign.example/api/upload/file/revealed_files/report.md）";
  const own = `${window.location.origin}/api/upload/file/revealed_files/report.md）`;
  render(<MarkdownContent content={`${foreign}\n\n\`${own}\``} />);
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link")).toHaveAttribute(
    "href",
    new URL(foreign).href,
  );
});
