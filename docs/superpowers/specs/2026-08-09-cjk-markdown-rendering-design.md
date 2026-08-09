# CJK Markdown Rendering Compatibility Design

## Problem

LambChat renders Markdown produced by users, agents, tools, approval requests, and task notifications. The current CommonMark-compatible parser does not always recognize emphasis delimiters when they touch Chinese, Japanese, or Korean text. For example:

```md
国务院提出到**2030年经常体育锻炼人数比例达40%**左右
```

is parsed as plain text because the closing delimiter has punctuation on its inner side and a CJK character on its outer side. The same delimiter classification affects `*`/`_` emphasis and GFM `~~` strikethrough.

## Goal

All frontend Markdown rendering paths must correctly parse CJK-adjacent bold, italic, and strikethrough syntax without requiring authors or models to insert spaces. Existing Markdown behavior, styling, allowed-element restrictions, line-break handling, math rendering, and code-fence normalization must remain unchanged.

## Rendering Inventory

There are three direct `ReactMarkdown` entry points:

1. `frontend/src/components/chat/ChatMessage/MarkdownContent.tsx`
   - Used by assistant and user messages, summaries, tool results, persona previews, image/audio analysis, and expanded sidebar content.
   - Also reused by `documents/previews/MarkdownRenderer.tsx`, so document previews inherit its parser configuration.
   - Adds GFM, line breaks, math, KaTeX, code-fence normalization, and custom component rendering.
2. `frontend/src/components/layout/AppContent/TaskToastMarkdown.tsx`
   - Renders restricted inline Markdown in task notifications.
   - Adds GFM and limits allowed elements.
3. `frontend/src/components/panels/ApprovalPanel.tsx`
   - Renders approval messages.
   - Adds GFM and line breaks.

No separate change is needed for renderers that delegate to `MarkdownContent`.

## Chosen Design

Add the CJK parser extensions as direct frontend dependencies:

- `remark-cjk-friendly` for CommonMark emphasis and strong emphasis.
- `remark-cjk-friendly-gfm-strikethrough`, imported from `remark-cjk-friendly-gfm-strikethrough/parseOnly` because LambChat only parses Markdown in these components.

Create a shared module under `frontend/src/components/common/` that exports the ordered base plugin list:

1. `remarkGfm`
2. `remarkCjkFriendly`
3. `remarkCjkFriendlyGfmStrikethrough`

The strikethrough extension must follow `remarkGfm`. Each renderer will spread this shared base and append only its existing renderer-specific plugins:

- Rich chat/document renderer: base + `remarkBreaks` + `remarkMath`
- Task toast: base only
- Approval panel: base + `remarkBreaks`

This keeps parser ordering in one place while preserving the different rendering and security policies of each component. A common `ReactMarkdown` wrapper is intentionally avoided because the entry points have materially different allowed elements, component mappings, and rehype plugins.

## Compatibility Scope

The renderer must recognize CJK-adjacent:

- Strong emphasis using `**...**` and `__...__`
- Emphasis using `*...*` and `_..._`
- GFM strikethrough using `~~...~~`
- Delimiters at both leading and trailing CJK boundaries
- Content whose inner boundary contains punctuation, including the reported `%**左右` case
- Chinese, Japanese, and Korean examples

Standard CommonMark/GFM behavior outside these CJK boundary cases must remain unchanged.

## Testing

Testing follows red-green-refactor:

1. Add behavioral tests around the shared plugin configuration using `ReactMarkdown` and server-rendered HTML. The tests must fail with the current parser and prove `<strong>`, `<em>`, and `<del>` nodes are generated. The test matrix covers opening and closing CJK boundaries, inner punctuation adjacent to the closing delimiter, Chinese/Japanese/Korean text, and every supported delimiter form (`**`, `__`, `*`, `_`, and `~~`).
2. Extend the existing task-toast test with the reported no-space Chinese boundary case so an actual product entry point is covered.
3. Add a source-completeness test that scans frontend TSX sources containing direct `<ReactMarkdown` usage and requires the shared CJK base configuration. This prevents future entry points from silently reverting to plain CommonMark behavior.
4. Run the focused tests, complete frontend test suite, frontend lint, and frontend production build.

## Non-goals

- Rewriting or inserting spaces into stored Markdown.
- Changing Markdown output from the backend or prompting models to format around the parser limitation.
- Replacing `react-markdown` or changing existing HTML safety behavior.
- Refactoring renderer-specific styling or component mappings.
