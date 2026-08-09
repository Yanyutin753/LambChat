# Excel Embedded Image Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display pictures embedded in modern OOXML Excel workbooks at their authored worksheet anchors without changing legacy `.xls` cell preview behavior.

**Architecture:** Keep SheetJS responsible for workbook cells and add an independent JSZip-based OOXML drawing extractor. Normalize pictures into sheet-scoped anchor records, calculate their rendered rectangles with pure layout helpers, and let `ExcelPreview` own Blob URL creation, cleanup, active-sheet filtering, and overlay rendering.

**Tech Stack:** React 19, TypeScript 5.6, SheetJS 0.18, JSZip 3.10, Vitest 4, Testing Library, jsdom.

## Global Constraints

- Support embedded pictures only for ZIP-based OOXML formats already handled by the preview: `.xlsx`, `.xlsm`, `.xltx`, and `.xlam`.
- Keep `.xls`, `.csv`, `.ods`, `.xlsb`, and other non-OOXML formats on the existing cell-only path.
- Support `xdr:oneCellAnchor` and `xdr:twoCellAnchor`; do not add charts, SmartArt, OLE, controls, linked external pictures, or backgrounds.
- Never fetch external relationship targets or resolve a package target outside the workbook root.
- A missing, malformed, or unsupported picture must not fail SheetJS cell preview.
- Use Blob URLs and revoke every URL when the workbook changes or the component unmounts.
- Preserve existing sheet tabs, formula bar, cell hover, two-axis scrolling, sticky headers, and status bar behavior.
- Do not modify or stage unrelated dirty-worktree files.

---

## File Structure

- Create `frontend/src/components/documents/previews/excelEmbeddedImages.ts`: OOXML package traversal, relationship validation, MIME filtering, and drawing-anchor normalization.
- Create `frontend/src/components/documents/previews/excelImageLayout.ts`: pure visible-grid extent and picture-rectangle calculations.
- Modify `frontend/src/components/documents/previews/ExcelPreview.tsx`: optional image enrichment, Blob URL lifecycle, DOM measurement, active-sheet overlay, and blank-grid extension.
- Create `frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts`: real in-memory OOXML fixture builder shared by parser and component tests.
- Create `frontend/src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts`: parser behavior and safety boundaries.
- Create `frontend/src/components/documents/previews/__tests__/excelImageLayout.test.ts`: grid extent and anchor geometry.
- Create `frontend/src/components/documents/previews/__tests__/ExcelPreviewImages.test.tsx`: user-visible sheet switching and URL cleanup.

---

### Task 1: Extract OOXML worksheet pictures and anchors

**Files:**
- Create: `frontend/src/components/documents/previews/excelEmbeddedImages.ts`
- Create: `frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts`
- Create: `frontend/src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts`

**Interfaces:**
- Consumes: an Excel `ArrayBuffer`, its file name, browser `DOMParser`, and JSZip.
- Produces: `extractExcelEmbeddedImages(arrayBuffer: ArrayBuffer, fileName: string): Promise<Map<string, ExcelEmbeddedImage[]>>`.
- Produces: exported `ExcelImageAnchorPoint`, `ExcelImageExtent`, and `ExcelEmbeddedImage` types for layout and React integration.

- [ ] **Step 1: Add a real OOXML fixture builder**

Create `excelImageWorkbookFixture.ts`. Generate a valid two-sheet workbook with SheetJS, reopen it with JSZip, append a worksheet drawing relationship, and add drawing XML, drawing relationships, and literal PNG bytes. Expose options that let tests choose the sheet, anchor XML, relationship target, target mode, media path, media bytes, and picture metadata.

```ts
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
  const anchorXml = (options.anchorXml ?? ONE_CELL_ANCHOR_XML)
    .replace("Fixture picture", options.pictureName ?? "Fixture picture")
    .replace(
      "Fixture description",
      options.pictureDescription ?? "Fixture description",
    );
  zip.file(
    "xl/drawings/drawing1.xml",
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
        xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        ${anchorXml}
      </xdr:wsDr>`,
  );
  const targetMode = options.targetMode
    ? ` TargetMode="${options.targetMode}"`
    : "";
  zip.file(
    "xl/drawings/_rels/drawing1.xml.rels",
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="${options.relationshipTarget ?? "../media/image1.png"}"${targetMode}/>
      </Relationships>`,
  );
  zip.file(
    options.mediaPath ?? "xl/media/image1.png",
    options.mediaBytes ?? new Uint8Array([137, 80, 78, 71]),
  );
  return zip.generateAsync({ type: "arraybuffer" });
}
```

The production change this fixture enables tests to catch is a broken relationship hop between workbook, worksheet, drawing, and media parts.

- [ ] **Step 2: Write the failing happy-path parser tests**

Create `excelEmbeddedImages.test.ts` with `/** @vitest-environment jsdom */`. Assert literal normalized values for both anchor forms and the source Blob bytes.

```ts
/** @vitest-environment jsdom */
import { buildExcelImageWorkbook, ONE_CELL_ANCHOR_XML } from "./excelImageWorkbookFixture";
import { extractExcelEmbeddedImages } from "../excelEmbeddedImages";

test("assigns an embedded picture to its worksheet and preserves a one-cell anchor", async () => {
  const buffer = await buildExcelImageWorkbook({ sheetIndex: 1 });

  const pictures = await extractExcelEmbeddedImages(buffer, "report.xlsx");
  const picture = pictures.get("Details")?.[0];

  expect([...pictures.keys()]).toEqual(["Details"]);
  expect(picture && {
    id: picture.id,
    name: picture.name,
    description: picture.description,
    mimeType: picture.mimeType,
    from: picture.from,
    extent: picture.extent,
    to: picture.to,
    order: picture.order,
  }).toEqual({
    id: "xl/drawings/drawing1.xml:rIdImage1:0",
    name: "Fixture picture",
    description: "Fixture description",
    mimeType: "image/png",
    from: { col: 1, row: 2, colOffsetEmu: 9525, rowOffsetEmu: 19050 },
    extent: { widthEmu: 914400, heightEmu: 457200 },
    to: undefined,
    order: 0,
  });
  expect([...new Uint8Array(await picture!.blob.arrayBuffer())]).toEqual([137, 80, 78, 71]);
});

test("normalizes a two-cell picture anchor", async () => {
  const anchorXml = ONE_CELL_ANCHOR_XML
    .replace("oneCellAnchor", "twoCellAnchor")
    .replace("oneCellAnchor", "twoCellAnchor")
    .replace('<xdr:ext cx="914400" cy="457200"/>', '<xdr:to><xdr:col>4</xdr:col><xdr:colOff>28575</xdr:colOff><xdr:row>6</xdr:row><xdr:rowOff>38100</xdr:rowOff></xdr:to>');
  const buffer = await buildExcelImageWorkbook({ anchorXml });

  const picture = (await extractExcelEmbeddedImages(buffer, "report.xlsm")).get("Summary")?.[0];

  expect(picture?.to).toEqual({ col: 4, row: 6, colOffsetEmu: 28575, rowOffsetEmu: 38100 });
  expect(picture?.extent).toBeUndefined();
});
```

- [ ] **Step 3: Run the tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts
```

Expected: FAIL because `excelEmbeddedImages.ts` and `extractExcelEmbeddedImages` do not exist.

- [ ] **Step 4: Implement the minimal OOXML extractor**

In `excelEmbeddedImages.ts`, define the normalized types and implement these exact boundaries:

```ts
import JSZip, { type JSZipObject } from "jszip";

export interface ExcelImageAnchorPoint {
  col: number;
  row: number;
  colOffsetEmu: number;
  rowOffsetEmu: number;
}

export interface ExcelImageExtent {
  widthEmu: number;
  heightEmu: number;
}

export interface ExcelEmbeddedImage {
  id: string;
  name: string;
  description: string;
  mimeType: string;
  blob: Blob;
  from: ExcelImageAnchorPoint;
  to?: ExcelImageAnchorPoint;
  extent?: ExcelImageExtent;
  order: number;
}

const OOXML_EXTENSIONS = new Set(["xlsx", "xlsm", "xltx", "xlam"]);
const MIME_BY_EXTENSION: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  bmp: "image/bmp",
  svg: "image/svg+xml",
};

export async function extractExcelEmbeddedImages(
  arrayBuffer: ArrayBuffer,
  fileName: string,
): Promise<Map<string, ExcelEmbeddedImage[]>> {
  if (!OOXML_EXTENSIONS.has(fileName.split(".").pop()?.toLowerCase() ?? "")) {
    return new Map();
  }
  const zip = await JSZip.loadAsync(arrayBuffer);
  const workbook = await readXml(zip, "xl/workbook.xml");
  const workbookRelationships = await readXml(
    zip,
    relationshipPartPath("xl/workbook.xml"),
  );
  if (!workbook || !workbookRelationships) return new Map();

  const sheets = new Map<string, ExcelEmbeddedImage[]>();
  const workbookRels = parseRelationships(workbookRelationships);
  for (const sheet of elements(workbook, "sheet")) {
    const name = sheet.getAttribute("name") ?? "";
    const sheetRelationshipId = relationshipId(sheet);
    const sheetRelationship = workbookRels.get(sheetRelationshipId);
    if (!name || !sheetRelationship || sheetRelationship.external) continue;
    const worksheetPath = resolvePackageTarget(
      "xl/workbook.xml",
      sheetRelationship.target,
    );
    if (!worksheetPath) continue;
    const worksheet = await readXml(zip, worksheetPath);
    const worksheetRelationships = await readXml(
      zip,
      relationshipPartPath(worksheetPath),
    );
    if (!worksheet || !worksheetRelationships) continue;
    const drawing = elements(worksheet, "drawing")[0];
    const drawingRelationship = parseRelationships(
      worksheetRelationships,
    ).get(relationshipId(drawing));
    if (!drawingRelationship || drawingRelationship.external) continue;
    const drawingPath = resolvePackageTarget(
      worksheetPath,
      drawingRelationship.target,
    );
    if (!drawingPath) continue;
    const drawingDocument = await readXml(zip, drawingPath);
    const drawingRelationships = await readXml(
      zip,
      relationshipPartPath(drawingPath),
    );
    if (!drawingDocument || !drawingRelationships) continue;
    const drawingRels = parseRelationships(drawingRelationships);
    const pictures: ExcelEmbeddedImage[] = [];
    const anchors = pictureAnchors(drawingDocument);
    for (const [order, anchor] of anchors.entries()) {
      const parsed = parsePictureAnchor(anchor, drawingPath, order);
      if (!parsed) continue;
      const mediaRelationship = drawingRels.get(parsed.relationshipId);
      if (
        !mediaRelationship ||
        mediaRelationship.external ||
        !mediaRelationship.type.endsWith("/image")
      ) continue;
      const mediaPath = resolvePackageTarget(
        drawingPath,
        mediaRelationship.target,
      );
      const extension = mediaPath?.split(".").pop()?.toLowerCase() ?? "";
      const mimeType = MIME_BY_EXTENSION[extension];
      const mediaEntry = mediaPath ? zip.file(mediaPath) : null;
      if (!mimeType || !mediaEntry) continue;
      const { relationshipId: _relationshipId, ...picture } = parsed;
      pictures.push({
        ...picture,
        mimeType,
        blob: await readBlob(mediaEntry, mimeType),
      });
    }
    if (pictures.length > 0) sheets.set(name, pictures);
  }
  return sheets;
}
```

Implement small private helpers with concrete contracts:

```ts
function parseXml(xml: string): XMLDocument;
function elements(parent: Document | Element, localName: string): Element[];
function pictureAnchors(document: XMLDocument): Element[];
function relationshipId(element: Element | undefined): string;
function relationshipPartPath(sourcePart: string): string;
function resolvePackageTarget(sourcePart: string, target: string): string | null;
function parseRelationships(doc: XMLDocument): Map<string, { target: string; external: boolean; type: string }>;
function parseAnchorPoint(parent: Element, localName: "from" | "to"): ExcelImageAnchorPoint | null;
function parsePictureAnchor(anchor: Element, drawingPath: string, order: number): Omit<ExcelEmbeddedImage, "blob" | "mimeType"> & { relationshipId: string } | null;
async function readXml(zip: JSZip, path: string): Promise<XMLDocument | null>;
async function readBlob(entry: JSZipObject, mimeType: string): Promise<Blob>;
```

Use `getElementsByTagNameNS("*", localName)` and `getAttributeNS` with the Office relationship namespace, falling back to prefixed attributes for jsdom interoperability. Treat any XML document containing `parsererror` as malformed.

- [ ] **Step 5: Run the parser tests and verify GREEN**

Run the Task 1 Vitest command again. Expected: 2 tests pass with no warning or unhandled rejection.

- [ ] **Step 6: Commit the extractor slice**

```bash
git add frontend/src/components/documents/previews/excelEmbeddedImages.ts frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts frontend/src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts
git commit -m "feat(preview): extract OOXML worksheet images"
```

---

### Task 2: Contain unsafe and malformed drawing data

**Files:**
- Modify: `frontend/src/components/documents/previews/excelEmbeddedImages.ts`
- Modify: `frontend/src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts`
- Modify: `frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts`

**Interfaces:**
- Consumes: the Task 1 `extractExcelEmbeddedImages` API.
- Produces: the same API with non-OOXML bypass, external-target rejection, package-root containment, supported MIME filtering, and per-picture failure isolation.

- [ ] **Step 1: Write failing safety and fallback tests**

Add tests with literal outcomes:

```ts
test("bypasses drawing extraction for legacy XLS before reading the package", async () => {
  const result = await extractExcelEmbeddedImages(new Uint8Array([1, 2, 3]).buffer, "legacy.xls");
  expect(result.size).toBe(0);
});

test.each([
  { name: "external target", target: "https://example.com/image.png", mode: "External" as const, mediaPath: "xl/media/image1.png" },
  { name: "path escaping package root", target: "../../../outside.png", mode: undefined, mediaPath: "outside.png" },
  { name: "missing package entry", target: "../media/missing.png", mode: undefined, mediaPath: "xl/media/different.png" },
  { name: "unsupported WMF", target: "../media/image1.wmf", mode: undefined, mediaPath: "xl/media/image1.wmf" },
])("ignores $name without failing worksheet extraction", async ({ target, mode, mediaPath }) => {
  const buffer = await buildExcelImageWorkbook({ relationshipTarget: target, targetMode: mode, mediaPath });
  const result = await extractExcelEmbeddedImages(buffer, "report.xlsx");
  expect(result.size).toBe(0);
});

test("keeps valid pictures when a sibling anchor is malformed", async () => {
  const buffer = await buildExcelImageWorkbook({ includeMalformedSibling: true });
  const result = await extractExcelEmbeddedImages(buffer, "report.xlsx");
  expect(result.get("Summary")?.map((picture) => picture.name)).toEqual(["Fixture picture"]);
});
```

Extend `ExcelImageFixtureOptions` with `includeMalformedSibling?: boolean` and prepend an anchor with no valid `from` or `r:embed` when requested.

- [ ] **Step 2: Run the safety tests and verify RED**

Run the Task 1 Vitest command. Expected: at least the external/path-escaping/unsupported or malformed-sibling case fails against the happy-path-only implementation.

- [ ] **Step 3: Implement strict local-target and per-picture filtering**

Make `resolvePackageTarget` reject URL schemes, absolute paths, empty targets, and any `..` segment that would pop past package root. Check `TargetMode="External"`, relationship type suffix `/image`, supported extension, and entry existence before reading bytes. Parse anchors independently so one invalid anchor is skipped without dropping the drawing or worksheet.

```ts
function resolvePackageTarget(sourcePart: string, target: string): string | null {
  if (!target || /^[a-z][a-z\d+.-]*:/i.test(target) || target.startsWith("/")) return null;
  const parts = sourcePart.split("/").slice(0, -1);
  for (const segment of target.replace(/\\/g, "/").split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (parts.length === 0) return null;
      parts.pop();
    } else {
      parts.push(segment);
    }
  }
  return parts.join("/");
}
```

- [ ] **Step 4: Run the parser test file and verify GREEN**

Run the Task 1 Vitest command. Expected: all parser tests pass.

- [ ] **Step 5: Commit the safety slice**

```bash
git add frontend/src/components/documents/previews/excelEmbeddedImages.ts frontend/src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts
git commit -m "fix(preview): contain malformed Excel drawings"
```

---

### Task 3: Calculate visible grid bounds and picture rectangles

**Files:**
- Create: `frontend/src/components/documents/previews/excelImageLayout.ts`
- Create: `frontend/src/components/documents/previews/__tests__/excelImageLayout.test.ts`

**Interfaces:**
- Consumes: `ExcelEmbeddedImage` anchors from Task 1.
- Produces: `getExcelGridExtent(rows: string[][], images: readonly ExcelEmbeddedImage[]): { rows: number; cols: number }`.
- Produces: `resolveExcelImageRect(image: ExcelEmbeddedImage, metrics: ExcelGridMetrics): ExcelImageRect | null`.

- [ ] **Step 1: Write failing pure layout tests**

```ts
import { getExcelGridExtent, resolveExcelImageRect } from "../excelImageLayout";
import type { ExcelEmbeddedImage } from "../excelEmbeddedImages";

const baseImage: ExcelEmbeddedImage = {
  id: "picture-1",
  name: "Picture",
  description: "",
  mimeType: "image/png",
  blob: new Blob(),
  from: { col: 1, row: 2, colOffsetEmu: 9525, rowOffsetEmu: 19050 },
  extent: { widthEmu: 914400, heightEmu: 457200 },
  order: 0,
};

test("extends a blank grid through a picture's two-cell endpoint", () => {
  const image = { ...baseImage, extent: undefined, to: { col: 5, row: 8, colOffsetEmu: 0, rowOffsetEmu: 0 } };
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
  const image = { ...baseImage, extent: undefined, to: { col: 2, row: 3, colOffsetEmu: 19050, rowOffsetEmu: 9525 } };
  const rect = resolveExcelImageRect(image, {
    columnStarts: [40, 120, 200],
    rowStarts: [24, 48, 72, 96],
  });
  expect(rect).toEqual({ left: 121, top: 74, width: 81, height: 23 });
});
```

- [ ] **Step 2: Run layout tests and verify RED**

```bash
cd frontend && pnpm exec vitest run src/components/documents/previews/__tests__/excelImageLayout.test.ts
```

Expected: FAIL because `excelImageLayout.ts` does not exist.

- [ ] **Step 3: Implement the pure layout helpers**

```ts
import type { ExcelEmbeddedImage, ExcelImageAnchorPoint } from "./excelEmbeddedImages";

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

export function getExcelGridExtent(rows: string[][], images: readonly ExcelEmbeddedImage[]) {
  let rowCount = rows.length;
  let colCount = rows.reduce((maximum, row) => Math.max(maximum, row.length), 0);
  for (const image of images) {
    rowCount = Math.max(rowCount, image.from.row + 1, (image.to?.row ?? -1) + 1);
    colCount = Math.max(colCount, image.from.col + 1, (image.to?.col ?? -1) + 1);
  }
  return { rows: rowCount, cols: colCount };
}

function pointToPixels(point: ExcelImageAnchorPoint, metrics: ExcelGridMetrics) {
  const left = metrics.columnStarts[point.col];
  const top = metrics.rowStarts[point.row];
  if (left == null || top == null) return null;
  return {
    left: left + point.colOffsetEmu / EMU_PER_CSS_PIXEL,
    top: top + point.rowOffsetEmu / EMU_PER_CSS_PIXEL,
  };
}

export function resolveExcelImageRect(image: ExcelEmbeddedImage, metrics: ExcelGridMetrics): ExcelImageRect | null {
  const start = pointToPixels(image.from, metrics);
  if (!start) return null;
  const end = image.to ? pointToPixels(image.to, metrics) : null;
  const width = end ? end.left - start.left : (image.extent?.widthEmu ?? 0) / EMU_PER_CSS_PIXEL;
  const height = end ? end.top - start.top : (image.extent?.heightEmu ?? 0) / EMU_PER_CSS_PIXEL;
  if (width <= 0 || height <= 0) return null;
  return { left: start.left, top: start.top, width, height };
}
```

- [ ] **Step 4: Run layout tests and verify GREEN**

Run the Task 3 Vitest command. Expected: all three tests pass.

- [ ] **Step 5: Commit the layout slice**

```bash
git add frontend/src/components/documents/previews/excelImageLayout.ts frontend/src/components/documents/previews/__tests__/excelImageLayout.test.ts
git commit -m "feat(preview): position Excel worksheet images"
```

---

### Task 4: Render active-sheet pictures and own Blob URL lifecycle

**Files:**
- Modify: `frontend/src/components/documents/previews/ExcelPreview.tsx:1-406`
- Create: `frontend/src/components/documents/previews/__tests__/ExcelPreviewImages.test.tsx`
- Modify: `frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts`

**Interfaces:**
- Consumes: `extractExcelEmbeddedImages`, `getExcelGridExtent`, and `resolveExcelImageRect`.
- Produces: user-visible `<img data-excel-embedded-image>` elements only for the active sheet, with Blob URL cleanup owned by the parsing effect.

- [ ] **Step 1: Write the failing React integration test**

Use the real `ExcelPreview`, real SheetJS parsing, and a real generated OOXML package. Mock only browser APIs missing from jsdom.

```tsx
/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ExcelPreview from "../ExcelPreview";
import { buildExcelImageWorkbook } from "./excelImageWorkbookFixture";

class ResizeObserverStub {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe() { this.callback([], this as unknown as ResizeObserver); }
  disconnect() {}
  unobserve() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn((blob: Blob) => `blob:fixture-${blob.size}`),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => vi.unstubAllGlobals());

test("shows only the active worksheet picture and revokes its Blob URL", async () => {
  const buffer = await buildExcelImageWorkbook({
    pictures: [
      { sheetIndex: 0, pictureName: "Summary picture", mediaPath: "xl/media/summary.png" },
      { sheetIndex: 1, pictureName: "Details picture", mediaPath: "xl/media/details.png" },
    ],
  });
  const view = render(<ExcelPreview arrayBuffer={buffer} fileName="report.xlsx" t={(key) => key} />);

  expect(await screen.findByRole("img", { name: "Summary picture" })).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "Details picture" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  expect(await screen.findByRole("img", { name: "Details picture" })).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "Summary picture" })).not.toBeInTheDocument();

  view.unmount();
  await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2));
});
```

Extend the fixture with `pictures?: ExcelImageFixtureOptions[]` so it can attach one drawing per selected worksheet and use unique drawing relationship/media paths.

The production regressions caught are rendering every sheet's pictures at once, omitting the active picture, or leaking workbook Blob URLs.

- [ ] **Step 2: Run the React test and verify RED**

```bash
cd frontend && pnpm exec vitest run src/components/documents/previews/__tests__/ExcelPreviewImages.test.tsx
```

Expected: FAIL because the current component renders no embedded picture.

- [ ] **Step 3: Enrich parsed sheet state and clean up object URLs**

Update imports to include `useLayoutEffect` and the Task 1/3 APIs. Replace `_fileName` with `fileName`. Add a view model:

```ts
interface ExcelPreviewImage extends ExcelEmbeddedImage {
  url: string;
}

interface SheetData {
  name: string;
  data: string[][];
  images: ExcelPreviewImage[];
}
```

Inside the workbook effect:

1. set loading and reset the active sheet;
2. parse cells with SheetJS;
3. call `extractExcelEmbeddedImages` in its own `try/catch`, falling back to an empty map;
4. create one object URL per returned Blob and attach images by exact sheet name;
5. on cancellation or effect cleanup, revoke every URL created by that effect;
6. keep SheetJS parse failures on the existing error path.

Do not log picture data, relationship paths, Blob contents, or exception bodies.

- [ ] **Step 4: Extend the grid and measure rendered anchors**

Use `getExcelGridExtent(currentSheet.data, currentSheet.images)` for rendered row and column counts while retaining populated row counts in the status bar. Wrap the table in a `relative w-max min-w-full` surface with a ref. Mark the existing column headers and row-number cells:

```tsx
data-excel-column-index={i}
data-excel-row-index={rawRowIndex}
```

In a `useLayoutEffect`, measure each marked element's `offsetLeft` or `offsetTop`, call `resolveExcelImageRect`, and store a `Map<string, ExcelImageRect>`. Recompute on active-sheet changes and with a `ResizeObserver` attached to the grid surface.

- [ ] **Step 5: Render the active worksheet overlay**

Render the image layer after the table inside the shared surface:

```tsx
<div className="absolute inset-0 z-[5] pointer-events-none" aria-label="Worksheet images">
  {currentSheet.images.map((image) => {
    const rect = imageRects.get(image.id);
    if (!rect) return null;
    return (
      <img
        key={image.id}
        data-excel-embedded-image
        src={image.url}
        alt={image.description || image.name}
        className="absolute max-w-none select-none"
        style={{
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height,
          objectFit: "fill",
          zIndex: image.order,
        }}
        draggable={false}
      />
    );
  })}
</div>
```

The image layer's stacking context stays below the existing sticky row/column headers and does not capture pointer or scroll input.

- [ ] **Step 6: Run React and focused Excel tests and verify GREEN**

```bash
cd frontend && pnpm exec vitest run \
  src/components/documents/previews/__tests__/ExcelPreviewImages.test.tsx \
  src/components/documents/previews/__tests__/excelEmbeddedImages.test.ts \
  src/components/documents/previews/__tests__/excelImageLayout.test.ts \
  src/components/documents/previews/__tests__/excelPreviewData.test.ts
```

Expected: all tests pass without act warnings, unhandled rejections, or leaked object URLs.

- [ ] **Step 7: Commit the React integration slice**

```bash
git add frontend/src/components/documents/previews/ExcelPreview.tsx frontend/src/components/documents/previews/__tests__/ExcelPreviewImages.test.tsx frontend/src/components/documents/previews/__tests__/excelImageWorkbookFixture.ts
git commit -m "feat(preview): display embedded Excel images"
```

---

### Task 5: Regression verification

**Files:**
- Modify only files from Tasks 1-4 if verification exposes a feature regression.

**Interfaces:**
- Consumes: completed Excel image preview.
- Produces: evidence that focused behavior, document previews, lint, and production build remain valid.

- [ ] **Step 1: Run all document preview tests**

```bash
cd frontend && pnpm exec vitest run src/components/documents/previews/__tests__ src/components/documents/__tests__
```

Expected: all tests pass. If an unrelated existing test fails, rerun that test unchanged and report it separately rather than changing unrelated production code.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && pnpm run lint
```

Expected: exit code 0. Fix only findings in files changed by this plan.

- [ ] **Step 3: Run the frontend production build**

```bash
cd frontend && pnpm run build
```

Expected: TypeScript and Vite build exit code 0. Do not commit generated build artifacts.

- [ ] **Step 4: Inspect the final diff and scope**

```bash
git status --short
git diff --check 099510db..HEAD
git diff --stat 099510db..HEAD
```

Expected: only the planned preview implementation/tests plus the already committed design and plan documents belong to this feature; the user's unrelated worktree edits remain unstaged and unchanged.

- [ ] **Step 5: Commit any verification-only corrections**

If Tasks 1-3 required no final correction, skip this commit. Otherwise stage only the exact preview files corrected and commit:

```bash
git add frontend/src/components/documents/previews/ExcelPreview.tsx frontend/src/components/documents/previews/excelEmbeddedImages.ts frontend/src/components/documents/previews/excelImageLayout.ts frontend/src/components/documents/previews/__tests__
git commit -m "test(preview): complete Excel image coverage"
```
