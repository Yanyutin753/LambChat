import JSZip from "jszip";
import * as XLSX from "xlsx";

export interface ExcelImageFixtureOptions {
  sheetIndex?: 0 | 1;
  anchorXml?: string;
  relationshipTarget?: string;
  targetMode?: "External";
  mediaPath?: string;
  mediaBytes?: Uint8Array;
  pictureName?: string;
  pictureDescription?: string;
  includeMalformedSibling?: boolean;
}

export const ONE_CELL_ANCHOR_XML = `
  <xdr:oneCellAnchor>
    <xdr:from><xdr:col>1</xdr:col><xdr:colOff>9525</xdr:colOff><xdr:row>2</xdr:row><xdr:rowOff>19050</xdr:rowOff></xdr:from>
    <xdr:ext cx="914400" cy="457200"/>
    <xdr:pic>
      <xdr:nvPicPr><xdr:cNvPr id="2" name="Fixture picture" descr="Fixture description"/><xdr:cNvPicPr/></xdr:nvPicPr>
      <xdr:blipFill><a:blip r:embed="rIdImage1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
      <xdr:spPr/>
    </xdr:pic>
    <xdr:clientData/>
  </xdr:oneCellAnchor>`;

function xmlAttribute(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderAnchor(options: ExcelImageFixtureOptions): string {
  const anchor = options.anchorXml ?? ONE_CELL_ANCHOR_XML;
  return anchor
    .replace(
      "Fixture picture",
      xmlAttribute(options.pictureName ?? "Fixture picture"),
    )
    .replace(
      "Fixture description",
      xmlAttribute(options.pictureDescription ?? "Fixture description"),
    );
}

export async function buildExcelImageWorkbook(
  options: ExcelImageFixtureOptions = {},
): Promise<ArrayBuffer> {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.aoa_to_sheet([["first"], ["value"]]),
    "Summary",
  );
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.aoa_to_sheet([["second"], ["value"]]),
    "Details",
  );

  const bytes = XLSX.write(workbook, { type: "array", bookType: "xlsx" });
  const zip = await JSZip.loadAsync(bytes);
  const sheetNumber = (options.sheetIndex ?? 0) + 1;
  const sheetPath = `xl/worksheets/sheet${sheetNumber}.xml`;
  const sheetEntry = zip.file(sheetPath);
  if (!sheetEntry) throw new Error(`Missing fixture worksheet ${sheetPath}`);
  const sheetXml = await sheetEntry.async("string");
  zip.file(
    sheetPath,
    sheetXml.replace(
      "</worksheet>",
      '<drawing r:id="rIdDrawing1"/></worksheet>',
    ),
  );
  zip.file(
    `xl/worksheets/_rels/sheet${sheetNumber}.xml.rels`,
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rIdDrawing1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
      </Relationships>`,
  );

  const malformedSibling = options.includeMalformedSibling
    ? "<xdr:oneCellAnchor><xdr:pic><xdr:blipFill><a:blip/></xdr:blipFill></xdr:pic></xdr:oneCellAnchor>"
    : "";
  zip.file(
    "xl/drawings/drawing1.xml",
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
        xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        ${malformedSibling}${renderAnchor(options)}
      </xdr:wsDr>`,
  );
  const targetMode = options.targetMode
    ? ` TargetMode="${options.targetMode}"`
    : "";
  zip.file(
    "xl/drawings/_rels/drawing1.xml.rels",
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="${xmlAttribute(
          options.relationshipTarget ?? "../media/image1.png",
        )}"${targetMode}/>
      </Relationships>`,
  );
  zip.file(
    options.mediaPath ?? "xl/media/image1.png",
    options.mediaBytes ?? new Uint8Array([137, 80, 78, 71]),
  );

  return zip.generateAsync({ type: "arraybuffer" });
}
