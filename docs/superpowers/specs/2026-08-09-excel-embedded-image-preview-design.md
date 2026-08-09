# Excel Embedded Image Preview Design

## Problem

The Excel preview currently uses SheetJS to extract formatted cell text into an
interactive grid. SheetJS does not expose the workbook drawing layer through the
data consumed by the preview, so pictures embedded in modern Excel workbooks are
silently omitted.

Legacy binary `.xls` workbooks store pictures through BIFF and OfficeArt rather
than the ZIP-based OOXML drawing model. Supporting those files would require a
separate binary drawing parser or a server-side office conversion service.

## Goal

Display browser-renderable pictures embedded in modern OOXML Excel workbooks
while preserving the existing spreadsheet grid, sheet tabs, formula bar,
scrolling, and cell formatting behavior.

The preview must:

- associate each picture with the correct worksheet;
- place pictures over the grid using their authored cell anchors and dimensions;
- show only the pictures belonging to the active worksheet;
- extend the visible blank grid when a picture is anchored beyond populated
  cells;
- release generated object URLs when the workbook changes or the preview
  unmounts;
- fall back to the existing cell-only preview when drawing data is absent or
  malformed.

## Scope

Image extraction applies to ZIP-based OOXML spreadsheet formats handled by the
existing Excel preview, including `.xlsx`, `.xlsm`, and `.xltx`.

Legacy `.xls` remains supported for cell preview but does not gain embedded
picture support. CSV, ODS, XLSB, and other non-OOXML spreadsheet containers also
retain their current behavior.

The first implementation supports the standard worksheet drawing anchors used
for embedded pictures:

- `xdr:oneCellAnchor`, using its start cell, offsets, and explicit extent;
- `xdr:twoCellAnchor`, using its start and end cells and offsets.

Charts, SmartArt, OLE objects, form controls, external linked pictures, and
background images are outside this change.

## Architecture

Keep SheetJS as the authoritative parser for workbook sheets and formatted cell
values. Add a separate, focused OOXML image extractor that reads the same
`ArrayBuffer` with the existing JSZip dependency.

The extractor resolves the package graph in this order:

1. `xl/workbook.xml` and its relationships map workbook sheet names to worksheet
   parts.
2. Each worksheet and its relationships map the sheet's drawing reference to a
   drawing part.
3. Each drawing and its relationships map picture `r:embed` identifiers to
   files under `xl/media` or another valid package-relative target.
4. Drawing anchors produce a normalized picture model containing the worksheet
   name, layer order, image Blob, media type, accessible name, start anchor, and
   either an end anchor or an explicit size.

Relationship targets are resolved as normalized package-relative paths. Targets
that escape the package root, reference an external resource, or point to a
missing entry are ignored.

The parser returns Blobs rather than data URLs. The React component owns the
corresponding object URLs because it also owns their lifecycle.

## Preview Data Model

Each parsed sheet keeps its existing cell rows and gains a list of pictures.
Each picture contains:

- a stable identity derived from its drawing part, relationship, and order;
- its source Blob and browser MIME type;
- optional authored name or description for alt text;
- zero-based start row and column plus EMU offsets;
- either zero-based end row and column plus offsets, or explicit EMU width and
  height;
- drawing order for deterministic stacking.

The visible row and column counts are the maximum of the populated cell range
and all current-sheet picture anchors. Blank rows and columns are added only to
the rendered grid; the underlying worksheet data is not mutated.

## Rendering and Layout

The table and picture layer share one relatively positioned grid surface inside
the existing two-axis scroll container. The picture layer is absolutely
positioned above cells and below sticky row and column headers.

After the active sheet renders, the component measures rendered column widths,
row heights, and header dimensions. It converts cell anchors into coordinates
on that rendered grid. EMU offsets and explicit extents are converted to CSS
pixels. A resize observer recomputes the rectangles when the preview viewport or
responsive column widths change.

Pictures retain the rectangle authored in Excel. They use normal `<img>`
elements backed by object URLs and do not capture scrolling or cell hover input.
The active sheet controls which image elements are mounted.

Browser-renderable PNG, JPEG, GIF, WebP, BMP, and SVG resources are displayed.
Unsupported formats such as EMF and WMF are skipped without failing the sheet.
Failure to decode one image does not affect other images or cell content.

## Lifecycle and Failure Behavior

Cell parsing and picture extraction run together for a new `ArrayBuffer`, but
picture extraction is optional enrichment. A picture parsing error is contained
and leaves the successfully parsed sheets available as a cell-only preview.

The component creates object URLs only for successfully extracted pictures. It
revokes all URLs before replacing parsed workbook data and during unmount. It
does not fetch external relationship targets.

Legacy and non-OOXML workbooks bypass image extraction based on the file
extension and continue through the existing SheetJS path.

## Testing

Follow red-green-refactor with focused Vitest coverage:

- build a minimal in-memory OOXML fixture with JSZip and verify that an embedded
  image is assigned to the correct named worksheet;
- verify `oneCellAnchor` and `twoCellAnchor` normalization, relationship target
  resolution, MIME detection, and drawing order;
- verify external, missing, path-escaping, malformed, and unsupported image
  targets are ignored without rejecting the workbook;
- verify picture anchors expand the rendered blank row and column bounds;
- verify sheet switching mounts only the active sheet's pictures;
- verify object URLs are revoked when the workbook changes and on unmount;
- verify `.xls` and other non-OOXML inputs preserve the existing cell-only
  preview.

After focused tests pass, run the related document-preview tests, frontend lint,
and frontend build. Existing unrelated failures, if any, must be reproduced and
reported separately.
