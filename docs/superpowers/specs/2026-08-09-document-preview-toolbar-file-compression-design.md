# Document Preview Toolbar File Compression Design

## Goal

Give the document preview toolbar's right-side actions more visual room by compressing the middle file-information block. Preserve every existing action and keep file metadata available.

## Scope

- Change only the shared document preview toolbar and the file icon API needed by that toolbar.
- Do not change preview-panel width, action availability, action order, or click behavior.
- Preserve unrelated working-tree changes.

## Layout

- Render the toolbar's file icon at 32 px instead of 40 px.
- Size the file-information block with a container-relative flex basis: it may shrink on narrow toolbars, grows modestly on wider toolbars, and remains capped so it cannot dominate the header.
- Keep `min-width: 0` and truncation on the filename and metadata so long names never push or clip the action group.
- Keep the file-size/type line visible.
- Keep the action group non-shrinking and aligned to the right.
- Keep the existing action-button dimensions, including the 44 px touch targets used on narrow viewports.

## Accessibility and Behavior

- The full filename remains available through its existing `title` attribute.
- No labels, tooltips, keyboard behavior, or focus treatment change.
- The compact layout applies wherever the shared document preview toolbar appears, independent of whether it is used in a sidebar or centered preview.

## Testing

- Add a focused toolbar layout regression test before production changes.
- Verify the test fails because the toolbar still uses the default 40 px icon and uncapped `flex-1` file-information block.
- Implement the minimal layout/API change, then rerun the focused document toolbar tests.
- Run the frontend build to catch TypeScript and Tailwind integration errors.
