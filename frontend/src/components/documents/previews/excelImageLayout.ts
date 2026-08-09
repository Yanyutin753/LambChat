import type {
  ExcelEmbeddedImage,
  ExcelImageAnchorPoint,
} from "./excelEmbeddedImages";

const EMU_PER_CSS_PIXEL = 9525;

export interface ExcelGridMetrics {
  columnStarts: number[];
  rowStarts: number[];
}

export interface ExcelImageRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function getExcelGridExtent(
  rows: string[][],
  images: readonly ExcelEmbeddedImage[],
): { rows: number; cols: number } {
  let rowCount = rows.length;
  let colCount = rows.reduce(
    (maximum, row) => Math.max(maximum, row.length),
    0,
  );

  for (const image of images) {
    rowCount = Math.max(
      rowCount,
      image.from.row + 1,
      (image.to?.row ?? -1) + 1,
    );
    colCount = Math.max(
      colCount,
      image.from.col + 1,
      (image.to?.col ?? -1) + 1,
    );
  }

  return { rows: rowCount, cols: colCount };
}

function pointToPixels(
  point: ExcelImageAnchorPoint,
  metrics: ExcelGridMetrics,
): { left: number; top: number } | null {
  const left = metrics.columnStarts[point.col];
  const top = metrics.rowStarts[point.row];
  if (left == null || top == null) return null;
  return {
    left: left + point.colOffsetEmu / EMU_PER_CSS_PIXEL,
    top: top + point.rowOffsetEmu / EMU_PER_CSS_PIXEL,
  };
}

export function resolveExcelImageRect(
  image: ExcelEmbeddedImage,
  metrics: ExcelGridMetrics,
): ExcelImageRect | null {
  const start = pointToPixels(image.from, metrics);
  if (!start) return null;

  const end = image.to ? pointToPixels(image.to, metrics) : null;
  const width = end
    ? end.left - start.left
    : (image.extent?.widthEmu ?? 0) / EMU_PER_CSS_PIXEL;
  const height = end
    ? end.top - start.top
    : (image.extent?.heightEmu ?? 0) / EMU_PER_CSS_PIXEL;
  if (width <= 0 || height <= 0) return null;

  return { left: start.left, top: start.top, width, height };
}
