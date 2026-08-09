# Document Preview Mobile Action Sizing Design

## Goal

Make the document preview header actions comfortably visible and consistently spaced on mobile without letting the action row escape the viewport.

## Root Cause

`ToolbarIconButton` declares a 44 px mobile minimum, but the later, more-specific global mobile rule `.flex button` in `markdown.css` resets that minimum to `auto`. In the document preview toolbar, each transparent action button therefore collapses to its hard-coded 16 px SVG, with only the wrapper gap separating adjacent actions.

## Scope

- Change only `DocumentPreviewToolbar`, its component-scoped CSS, and its focused regression test.
- Preserve action availability, ordering, handlers, labels, tooltips, focus treatment, and desktop behavior.
- Preserve the bounded, truncating file-information block so long names cannot push actions outside the viewport.
- Do not change the shared `ToolbarIconButton` or the global markdown mobile rules.

## Mobile Layout

- Give the back button and every right-side action a scoped 32 px square button box.
- Render every toolbar button SVG at 16 px at every breakpoint.
- Use 10 px spacing between adjacent right-side actions.
- Keep the right action group non-shrinking while the file-information block remains the element that yields space and truncates.

## Desktop Layout

- At `sm` and above, keep 32 px buttons, 16 px SVGs, and 4 px spacing.

## Testing

- Extend the real component layout test to assert the scoped toolbar/action-group hooks and responsive spacing utilities.
- Verify RED before production changes, then run all focused document toolbar tests and the frontend build.
