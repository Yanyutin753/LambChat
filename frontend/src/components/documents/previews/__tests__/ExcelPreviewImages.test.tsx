/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ExcelPreview from "../ExcelPreview";
import { buildExcelImageWorkbook } from "./excelImageWorkbookFixture";

class ResizeObserverStub implements ResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}

  observe(): void {
    this.callback([], this);
  }

  disconnect(): void {}

  unobserve(): void {}
}

const createObjectURL = vi.fn((blob: Blob) => `blob:fixture-${blob.size}`);
const revokeObjectURL = vi.fn();

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectURL,
  });
});

afterEach(() => {
  createObjectURL.mockReset();
  revokeObjectURL.mockReset();
  vi.unstubAllGlobals();
});

test("shows only the active worksheet picture and revokes its Blob URL", async () => {
  const buffer = await buildExcelImageWorkbook({
    pictures: [
      {
        sheetIndex: 0,
        pictureName: "Summary picture",
        mediaPath: "xl/media/summary.png",
      },
      {
        sheetIndex: 1,
        pictureName: "Details picture",
        mediaPath: "xl/media/details.png",
      },
    ],
  });
  const view = render(
    <ExcelPreview
      arrayBuffer={buffer}
      fileName="report.xlsx"
      t={(key) => key}
    />,
  );

  expect(
    await screen.findByRole("img", { name: "Summary picture" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("img", { name: "Details picture" }),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  expect(
    await screen.findByRole("img", { name: "Details picture" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("img", { name: "Summary picture" }),
  ).not.toBeInTheDocument();

  view.unmount();
  await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledTimes(2));
});
