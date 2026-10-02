/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { FileRevealItem } from "../FileRevealItem";

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

test("inline video controls do not open a second player; its separate fullscreen button does", () => {
  const pause = vi
    .spyOn(HTMLMediaElement.prototype, "pause")
    .mockImplementation(() => {});
  render(
    <FileRevealItem
      args={{ path: "/report.webm" }}
      result={{
        key: "report",
        url: "/report.webm",
        name: "report.webm",
        type: "video",
      }}
      success
      allowAutoPreview={false}
    />,
  );
  fireEvent.click(document.querySelector("video")!);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(pause).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "imageViewer.fullscreen" }),
  );
  expect(
    screen.getByRole("dialog", { name: "report.webm" }),
  ).toBeInTheDocument();
  expect(pause).toHaveBeenCalledOnce();
});

test("standalone revealed image has a native preview button", () => {
  render(
    <FileRevealItem
      args={{ path: "/report.webp" }}
      result={{
        key: "report",
        url: "/report.webp",
        name: "report.webp",
        type: "image",
      }}
      success
      allowAutoPreview={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "report.webp" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
