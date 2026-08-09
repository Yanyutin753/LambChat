# Flat Mobile Tool Console Actions Design

## Goal

Make the tool result panel's action buttons visually identical on mobile and desktop. The center/sidebar toggle, fullscreen toggle, and close action should render as independent compact icon buttons instead of a bordered capsule.

## Scope

- Change only the action group rendered by `ToolResultPanel`.
- Keep the shared `ToolbarIconButton` defaults unchanged so other mobile toolbars retain their existing 44 px touch targets.
- Apply the same treatment to the three-action group and the close-only group.
- Preserve all click handlers, titles, accessible labels, pressed state, icons, translations, and focus/hover/active behavior.

## Visual Rules

- Use 32 px square buttons at every breakpoint.
- Use 4 px spacing between adjacent action buttons at every breakpoint.
- The action group itself has no padding, background, border-like inset shadow, or capsule treatment.
- Buttons remain transparent at rest. Existing button-level hover, active, and focus-visible styles provide interaction feedback.

## Implementation Boundary

`ToolResultPanel` will use one consistent action-group gap. Component-scoped CSS under `.tool-console-actions` will override the shared button minimum dimensions for direct child buttons. This avoids changing `ToolbarIconButton` behavior elsewhere.

## Testing

Extend the existing `ToolResultPanel` source tests to assert:

- both tool-console action groups use the breakpoint-independent compact gap;
- `.tool-console-actions` has no capsule background, inset shadow, or padding;
- direct child buttons receive 32 px width and height with their shared mobile minimum dimensions reset;
- the global `ToolbarIconButton` implementation is not changed.

Run the focused Vitest file first, then the relevant frontend test suite and build if the focused test passes.
