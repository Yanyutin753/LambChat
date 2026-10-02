/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { VideoViewer } from "../VideoViewer";

vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (
    this: HTMLDialogElement,
  ) {
    this.open = true;
    this.focus();
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});
afterEach(() => {
  cleanup();
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  vi.restoreAllMocks();
});

test("video preview delegates internal keyboard controls to a native modal and restores its opener", async () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    { width: 44, height: 44 },
  ] as unknown as DOMRectList);
  const opener = document.createElement("button");
  document.body.append(opener);
  opener.focus();
  const close = vi.fn();
  const view = render(
    <VideoViewer
      src="/report.webm"
      title="report.webm"
      isOpen
      onClose={close}
    />,
  );
  try {
    const viewer = screen.getByRole("dialog", { name: "report.webm" });
    expect(viewer.tagName).toBe("DIALOG");
    expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledOnce();
    expect(viewer).toHaveFocus();
    expect(viewer).not.toHaveAttribute("data-yields-sidebar");
    const video = viewer.querySelector("video")!;
    expect(video.tabIndex).toBe(0);
    video.focus();
    expect(fireEvent.keyDown(video, { key: "Tab", cancelable: true })).toBe(
      true,
    );
    expect(video).toHaveFocus();
    fireEvent.keyDown(viewer, { key: "Escape", isComposing: true });
    expect(close).not.toHaveBeenCalled();
    fireEvent(viewer, new Event("cancel", { cancelable: true }));
    expect(close).toHaveBeenCalledOnce();
    view.unmount();
    expect(HTMLDialogElement.prototype.close).toHaveBeenCalledOnce();
    await Promise.resolve();
    expect(opener).toHaveFocus();
  } finally {
    opener.remove();
  }
});

test("failed video can retry the same URL and keeps a useful download action", () => {
  render(
    <VideoViewer
      src="/report.webm"
      title="report.webm"
      isOpen
      onClose={() => {}}
    />,
  );
  const video = document.querySelector("video")!;
  video.focus();
  fireEvent.error(video);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "documents.videoLoadFailed",
  );
  expect(video).not.toBeVisible();
  expect(
    screen.getByRole("button", { name: "imageViewer.download" }),
  ).toBeEnabled();
  const retry = screen.getByRole("button", { name: "common.retry" });
  retry.focus();
  fireEvent.click(retry);
  const retried = document.querySelector("video")!;
  expect(retried).not.toBe(video);
  expect(retried).toHaveAttribute("src", "/report.webm");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("dialog")).toHaveFocus();
  fireEvent.loadedData(retried);
  expect(
    screen.getByRole("button", { name: "imageViewer.download" }),
  ).toBeEnabled();
});

test("older WebViews retain a focus-contained video preview without the native dialog API", async () => {
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    { width: 44, height: 44 },
  ] as unknown as DOMRectList);
  const opener = document.createElement("button");
  document.body.append(opener);
  opener.focus();
  const close = vi.fn();
  const view = render(
    <VideoViewer src="/report.webm" isOpen onClose={close} />,
  );
  try {
    const viewer = screen.getByRole("dialog");
    expect(viewer.tagName).toBe("DIV");
    const video = viewer.querySelector("video")!;
    video.focus();
    expect(fireEvent.keyDown(video, { key: "Tab", cancelable: true })).toBe(
      true,
    );
    opener.focus();
    expect(screen.getByRole("button", { name: "common.close" })).toHaveFocus();
    video.focus();
    fireEvent.keyDown(video, { key: "Tab", shiftKey: true });
    opener.focus();
    expect(video).toHaveFocus();
    fireEvent.keyDown(viewer, { key: "Escape", isComposing: true });
    expect(close).not.toHaveBeenCalled();
    fireEvent.keyDown(viewer, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
    view.unmount();
    await Promise.resolve();
    expect(opener).toHaveFocus();
  } finally {
    opener.remove();
  }
});
