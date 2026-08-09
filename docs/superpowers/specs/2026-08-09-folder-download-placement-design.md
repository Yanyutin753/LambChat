# Folder Download Placement Design

## Goal

Place each folder's ZIP download action immediately to the left of its expand/collapse chevron in the revealed-artifacts file tree.

## Design

Update only `TreeDirRow` in `RevealArtifactsSummary.tsx`. The row will contain three sibling controls in this visual and DOM order:

1. A flexible folder-information button that toggles expansion.
2. The existing ZIP download button.
3. A compact chevron button that also toggles expansion.

Keeping the controls as siblings avoids invalid nested buttons. Clicking the download action must continue to export the folder without changing its expanded state. Clicking either the folder information or the chevron must toggle the same `expanded` state. Existing loading, disabled, hover, dark-mode, and download-error behavior remains unchanged.

## Accessibility

Both expansion controls expose `aria-expanded`. The chevron control receives a localized accessible label that identifies the folder and whether the action will expand or collapse it. The decorative chevron SVG remains hidden from assistive technology through Lucide's existing icon behavior.

## Testing

Add a focused component regression test that renders a downloadable folder and verifies the folder row's DOM order is folder-information control, ZIP download control, then chevron control. Keep the existing test proving that clicking download does not toggle expansion.

Run the focused Vitest file first, then the full `RevealArtifactsSummary`-related tests and the frontend build.
