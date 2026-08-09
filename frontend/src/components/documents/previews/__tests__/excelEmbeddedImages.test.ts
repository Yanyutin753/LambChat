/** @vitest-environment jsdom */
import {
  buildExcelImageWorkbook,
  ONE_CELL_ANCHOR_XML,
} from "./excelImageWorkbookFixture";
import { extractExcelEmbeddedImages } from "../excelEmbeddedImages";

test("assigns an embedded picture to its worksheet and preserves a one-cell anchor", async () => {
  const buffer = await buildExcelImageWorkbook({ sheetIndex: 1 });

  const pictures = await extractExcelEmbeddedImages(buffer, "report.xlsx");
  const picture = pictures.get("Details")?.[0];

  expect([...pictures.keys()]).toEqual(["Details"]);
  expect(
    picture && {
      id: picture.id,
      name: picture.name,
      description: picture.description,
      mimeType: picture.mimeType,
      from: picture.from,
      extent: picture.extent,
      to: picture.to,
      order: picture.order,
    },
  ).toEqual({
    id: "xl/drawings/drawing1.xml:rIdImage1:0",
    name: "Fixture picture",
    description: "Fixture description",
    mimeType: "image/png",
    from: {
      col: 1,
      row: 2,
      colOffsetEmu: 9525,
      rowOffsetEmu: 19050,
    },
    extent: { widthEmu: 914400, heightEmu: 457200 },
    to: undefined,
    order: 0,
  });
  expect([...new Uint8Array(await picture!.blob.arrayBuffer())]).toEqual([
    137, 80, 78, 71,
  ]);
});

test("normalizes a two-cell picture anchor", async () => {
  const anchorXml = ONE_CELL_ANCHOR_XML.replaceAll(
    "oneCellAnchor",
    "twoCellAnchor",
  ).replace(
    '<xdr:ext cx="914400" cy="457200"/>',
    "<xdr:to><xdr:col>4</xdr:col><xdr:colOff>28575</xdr:colOff><xdr:row>6</xdr:row><xdr:rowOff>38100</xdr:rowOff></xdr:to>",
  );
  const buffer = await buildExcelImageWorkbook({ anchorXml });

  const picture = (await extractExcelEmbeddedImages(buffer, "report.xlsm")).get(
    "Summary",
  )?.[0];

  expect(picture?.to).toEqual({
    col: 4,
    row: 6,
    colOffsetEmu: 28575,
    rowOffsetEmu: 38100,
  });
  expect(picture?.extent).toBeUndefined();
});
