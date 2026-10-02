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
  expect(view.container.firstElementChild).toHaveClass("bg-theme-bg-card");
  expect(
    screen.getByRole("button", { name: "common.previous" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Summary" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(
    await screen.findByRole("img", { name: "Details picture" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("img", { name: "Summary picture" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Details" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  view.unmount();
  await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledTimes(2));
});

test.each(["", "\uFEFF"])(
  "renders UTF-8 CSV text with BOM prefix %j",
  async (bom) => {
    const buffer = new TextEncoder().encode(
      `${bom}月份,交付成果\n六月,"Résumé, 中文报告"\n`,
    ).buffer;
    render(
      <ExcelPreview
        arrayBuffer={buffer}
        fileName="报告.CSV"
        t={(key) => key}
      />,
    );
    expect(
      await screen.findByRole("columnheader", { name: "月份" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("cell", { name: "Résumé, 中文报告" }),
    ).toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByRole("columnheader", { name: "月份" }));
    expect(screen.getAllByText("月份")).toHaveLength(2);
    expect(screen.queryAllByText("A0")).toHaveLength(0);
  },
);

test("empty CSV shows the existing empty state", async () => {
  render(
    <ExcelPreview
      arrayBuffer={new ArrayBuffer(0)}
      fileName="empty.csv"
      t={(key) => key}
    />,
  );
  expect(await screen.findByText("documents.noData")).toBeInTheDocument();
});

test("keeps Windows-1252 CSV readable when bytes are not UTF-8", async () => {
  const buffer = new Uint8Array([
    78, 97, 109, 101, 10, 82, 233, 115, 117, 109, 233, 10,
  ]).buffer;
  render(
    <ExcelPreview
      arrayBuffer={buffer}
      fileName="legacy.csv"
      t={(key) => key}
    />,
  );
  expect(
    await screen.findByRole("cell", { name: "Résumé" }),
  ).toBeInTheDocument();
});
