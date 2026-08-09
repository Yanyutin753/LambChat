# Standard DOCX Preview Design

## Problem

The Word preview currently places all rendered content inside a fixed `816px` by
`1056px` card while also disabling `docx-preview`'s wrapper and original page
width. This mixes a simulated paper card with reflowed document content: the
preview surface does not fill its viewport, and the result does not preserve a
normal DOCX page layout.

## Goal

Render valid DOCX files like a conventional document reader:

- the preview surface fills the available viewport;
- document pages retain their original width, height, margins, pagination,
  headers, and footers;
- pages are centered on a neutral canvas with a visible gap and subtle shadow;
- narrow viewports scroll horizontally instead of reflowing or shrinking the
  document into unreadable text;
- light and dark themes keep the document page white while adapting the canvas.

Mammoth and plain-text fallback output remains readable, but it is not required
to reproduce Word pagination.

## Design

`docx-preview` will render with its wrapper enabled and with document width and
height preserved. The component will no longer wrap successful DOCX output in a
fixed synthetic paper card. Instead, the scroll container becomes the full-size
preview canvas, and `docx-preview` owns each page's paper dimensions.

Component styles will only adjust the wrapper canvas spacing and page shadow;
they will not override generated page width, minimum height, or page padding.
The document pages remain white in both themes because this matches Word and
keeps authored colors legible.

For Mammoth or extracted-text fallback output, the existing constrained reading
card remains. It will use a responsive maximum width and a minimum viewport
height without pretending to be a paginated Word page.

## Responsive Behavior

- Desktop: pages are centered with comfortable canvas padding.
- Narrow viewport: canvas padding is reduced and the natural page width is
  retained; the existing preview scroller exposes horizontal scrolling.
- Multi-page document: every generated page retains its own shadow and vertical
  separation.

No zoom controls or automatic fit-to-width behavior are added in this change.

## Testing

Add focused tests that fail against the current configuration and verify that:

- the renderer enables the DOCX wrapper;
- original document width and height are preserved;
- the successful DOCX branch does not add the fixed synthetic paper card;
- fallback HTML still renders inside the constrained reading card.

Run the focused Vitest tests, the relevant frontend test suite, lint, and build.
