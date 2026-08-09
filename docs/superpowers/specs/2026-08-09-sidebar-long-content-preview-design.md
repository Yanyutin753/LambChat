# Sidebar Long-Content Preview Design

## Goal

Make the performance-safe long-content preview in the sidebar look consistent with normally rendered Markdown while preserving its lightweight plain-text rendering.

The change applies to both thinking content and subagent process content because both use `SidebarMarkdownContent`.

## Scope

- Style only the lightweight preview state used while content is streaming or exceeds the sidebar preview limit.
- Give the preview text normal reading-area horizontal padding, vertical breathing room, and typography aligned with sidebar Markdown.
- Keep the existing bottom fade and expand action, with clear spacing between the text and action.
- Reuse one shared implementation for thinking and subagent panels.

## Non-goals

- Do not change preview thresholds or truncation behavior.
- Do not render full Markdown in the lightweight state.
- Do not change normal Markdown rendering, sidebar panel structure, or chat-stream cards.
- Do not alter the expand interaction.

## Implementation Direction

Update the lightweight branch in `SidebarMarkdownContent` so its plain-text reading surface uses the same visual rhythm as normal sidebar content. Keep the existing `whitespace-pre-wrap` behavior and bounded scrolling so text remains cheap to render.

`SubagentPanelContent` will continue to delegate its process preview to `SidebarMarkdownContent`; it should not introduce a separate text-surface style.

## Testing

Add a focused regression test that verifies the shared lightweight preview includes intentional horizontal padding and Markdown-aligned typography, and that subagent process previews still use the shared component. Run the focused Vitest file, then the relevant frontend test suite.
