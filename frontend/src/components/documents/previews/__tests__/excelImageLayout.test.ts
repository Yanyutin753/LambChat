import type { ExcelEmbeddedImage } from "../excelEmbeddedImages";
import { getExcelGridExtent, resolveExcelImageRect } from "../excelImageLayout";

const baseImage: ExcelEmbeddedImage = {
  id: "picture-1",
  name: "Picture",
  description: "",
  mimeType: "image/png",
  blob: new Blob(),
  from: {
    col: 1,
    row: 2,
    colOffsetEmu: 9525,
    rowOffsetEmu: 19050,
  },
  extent: { widthEmu: 914400, heightEmu: 457200 },
  order: 0,
};

test("extends a blank grid through a picture's two-cell endpoint", () => {
  const image: ExcelEmbeddedImage = {
    ...baseImage,
    extent: undefined,
    to: {
      col: 5,
      row: 8,
      colOffsetEmu: 0,
      rowOffsetEmu: 0,
    },
  };

  expect(getExcelGridExtent([["A"]], [image])).toEqual({ rows: 9, cols: 6 });
});

test("converts one-cell EMU offsets and extents to a rendered rectangle", () => {
  const rect = resolveExcelImageRect(baseImage, {
    columnStarts: [40, 120, 200],
    rowStarts: [24, 48, 72, 96],
  });

  expect(rect).toEqual({ left: 121, top: 74, width: 96, height: 48 });
});

test("uses a two-cell endpoint for picture width and height", () => {
  const image: ExcelEmbeddedImage = {
    ...baseImage,
    extent: undefined,
    to: {
      col: 2,
      row: 3,
      colOffsetEmu: 19050,
      rowOffsetEmu: 9525,
    },
  };

  const rect = resolveExcelImageRect(image, {
    columnStarts: [40, 120, 200],
    rowStarts: [24, 48, 72, 96],
  });

  expect(rect).toEqual({ left: 121, top: 74, width: 81, height: 23 });
});
