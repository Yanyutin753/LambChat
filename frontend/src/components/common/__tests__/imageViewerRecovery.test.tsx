/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ImageViewer } from "../ImageViewer";

vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(cleanup);

test("fullscreen image preview isolates an open file panel and restores it on close", async () => {
  const panel = document.createElement("div");
  panel.setAttribute("data-right-panel-root", "true");
  const opener = document.createElement("button");
  panel.append(opener);
  document.body.append(panel);
  opener.focus();
  const { unmount } = render(
    <ImageViewer src="/report.webp" isOpen onClose={() => {}} />,
  );
  try {
    expect(panel.inert).toBe(true);
    unmount();
    await Promise.resolve();
    expect(panel.inert).toBe(false);
    expect(opener).toHaveFocus();
  } finally {
    panel.remove();
  }
});

test("failed image offers retry and cannot expose unusable transform controls", () => {
  render(
    <ImageViewer
      src="/report.webp"
      alt="report.webp"
      isOpen
      onClose={() => {}}
    />,
  );
  fireEvent.error(screen.getByRole("img", { name: "report.webp" }));
  expect(screen.getByRole("alert")).toHaveTextContent("imageViewer.loadFailed");
  expect(
    screen.getByRole("button", { name: "imageViewer.download", exact: true }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "imageViewer.zoomIn" }),
  ).not.toBeInTheDocument();
  const failedImage = screen.getByAltText("report.webp");
  expect(failedImage).not.toBeVisible();
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry", exact: true }),
  );
  const retriedImage = screen.getByRole("img", { name: "report.webp" });
  expect(retriedImage).not.toBe(failedImage);
  expect(retriedImage).toHaveAttribute("src", "/report.webp");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.load(retriedImage);
  expect(
    screen.getByRole("button", { name: "imageViewer.download", exact: true }),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "imageViewer.zoomIn" }),
  ).toBeEnabled();
});

test("changing away from a failed image restores controls and resets its view", () => {
  const next = vi.fn();
  const { rerender } = render(
    <ImageViewer
      src="/first.webp"
      alt="first"
      isOpen
      onClose={() => {}}
      hasNext
      onNext={next}
    />,
  );
  fireEvent.error(screen.getByRole("img", { name: "first" }));
  expect(screen.getByRole("alert")).toBeInTheDocument();
  const nextButton = screen.getByRole("button", {
    name: "imageViewer.next",
    exact: true,
  });
  nextButton.focus();
  fireEvent.click(nextButton);
  expect(next).toHaveBeenCalledOnce();
  rerender(
    <ImageViewer src="/second.webp" alt="second" isOpen onClose={() => {}} />,
  );
  fireEvent.load(screen.getByRole("img", { name: "second" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("100%")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toHaveFocus();
  expect(screen.getByRole("dialog")).not.toHaveAttribute("data-yields-sidebar");
  expect(
    screen.getByRole("button", { name: "imageViewer.zoomIn" }),
  ).toBeEnabled();
});
