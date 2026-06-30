import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("mobile tool result panel slide-in keeps the sheet opaque", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const animationsSource = readFileSync(
    new URL("../../../../../styles/animations.css", import.meta.url),
    "utf8",
  );
  const slideUpAnimation = animationsSource.match(
    /@keyframes\s+slide-up-fullscreen\s*\{(?<body>[\s\S]*?)\n\}/,
  )?.groups?.body;

  assert.ok(slideUpAnimation, "slide-up-fullscreen animation should exist");
  assert.doesNotMatch(
    slideUpAnimation,
    /\bopacity\s*:/,
    "sliding the mobile sheet should not reveal content underneath",
  );
  assert.doesNotMatch(
    componentSource,
    /transform:\s*"translateY\(100%\)"\s*,\s*opacity:\s*0/,
    "pre-animation mobile sheet state should keep its opaque background",
  );
});

test("mobile swipe-to-close is limited to the explicit drag handle", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const swipeHookSource = readFileSync(
    new URL("../../../../../hooks/useSwipeToClose.ts", import.meta.url),
    "utf8",
  );
  const sidebarPanelHookSource = readFileSync(
    new URL("../../../../../hooks/useSidebarPanel.ts", import.meta.url),
    "utf8",
  );

  assert.match(
    swipeHookSource,
    /dragHandleRef\?: RefObject<HTMLElement \| null>/,
    "swipe hook should support an explicit drag handle ref",
  );
  assert.match(
    sidebarPanelHookSource,
    /dragHandleRef,\s*\}\);/,
    "sidebar panel hook should pass its drag handle into the swipe hook",
  );
  assert.match(
    componentSource,
    /ref=\{dragHandleRef\}/,
    "tool result panel should attach the swipe handle ref to the visible mobile handle",
  );
});

test("explicit close button reports a user close before closing the panel", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    componentSource,
    /onUserClose\?: \(\) => void/,
    "tool result panel should expose an explicit user-close callback",
  );
  assert.match(
    componentSource,
    /const handleUserClose = useCallback\(\(\) => \{\s*onUserClose\?\.\(\);\s*clearSidebarHistory\(\);\s*onClose\(\);/s,
    "close button should notify user-close handlers before closing",
  );
  assert.match(
    componentSource,
    /useSidebarPanel\(\{\s*open,\s*onClose: handleUserClose,/s,
    "keyboard and swipe close paths should use the same user-close handler",
  );
});

test("tool result overlay reserves vertical safe-area spacing", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    componentSource,
    /className=\{`safe-area-viewport-padding fixed inset-0 z-\[200\] flex flex-col/,
    "tool result overlay should keep sidebar, center, and fullscreen panels inside vertical safe areas",
  );
});

test("floating center overlay close button is labelled as cancel fullscreen", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    componentSource,
    /aria-label=\{t\("documents\.cancelFullscreen", "取消全屏"\)\}/,
    "center overlay floating X should announce that it cancels fullscreen",
  );
  assert.match(
    componentSource,
    /const handleCancelFullscreen = useCallback\(\(\) => \{/,
    "center overlay floating X should have a dedicated cancel-fullscreen handler",
  );
  assert.match(
    componentSource,
    /onViewModeChange\?\.\("sidebar"\);/,
    "cancel fullscreen should restore externally controlled panels to sidebar mode",
  );
  assert.match(
    componentSource,
    /setInternalViewMode\("sidebar"\);/,
    "cancel fullscreen should restore internally controlled panels to sidebar mode",
  );
  assert.match(
    componentSource,
    /handleCancelFullscreen\(\);/,
    "floating X should cancel fullscreen instead of closing the panel",
  );
  assert.doesNotMatch(
    componentSource,
    /aria-label=\{t\("documents\.cancelFullscreen", "取消全屏"\)\}[\s\S]{0,160}handleUserClose\(\);/,
    "cancel fullscreen button should not invoke the close flow",
  );
});

test("tool result header truncates long titles and subtitles on narrow screens", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    componentSource,
    /className="tool-console-title-row flex items-end gap-2 min-w-0 flex-1 overflow-hidden"/,
    "title row should bottom-align titles and subtitles while clipping overflowing text",
  );
  assert.match(
    componentSource,
    /className="tool-console-title min-w-0 max-w-\[40%\] truncate font-medium text-sm text-theme-text"/,
    "title should not expand beyond its content, but should still shrink and truncate",
  );
  assert.match(
    componentSource,
    /className="tool-console-subtitle-pill inline-flex h-5 min-w-0 max-w-\[45vw\] sm:max-w-\[min\(32rem,52%\)\] items-end overflow-hidden px-0 pb-\[1px\] text-xs font-normal leading-none text-theme-text-tertiary"/,
    "single subtitles should use a readable plain bottom-aligned treatment that shrinks, caps responsive width, and truncates long prompt text",
  );
  assert.match(
    componentSource,
    /<span className="block min-w-0 truncate">\s*\{subtitle\}\s*<\/span>/s,
    "subtitle text should use the same font family as the title and truncate cleanly",
  );
  assert.match(
    componentSource,
    /className="tool-console-subtitle-list inline-flex items-end gap-1 min-w-0 max-w-\[45vw\] sm:max-w-\[min\(32rem,52%\)\] overflow-hidden"/,
    "tag subtitles should share the same responsive width behavior and bottom alignment as command subtitles",
  );
  assert.match(
    componentSource,
    /className="tool-console-subtitle-chip inline-flex items-end shrink-0 max-w-full px-0 h-5 pb-\[1px\] text-xs font-normal leading-none text-theme-text-tertiary"/,
    "individual subtitle tags should expose the readable bottom-aligned chip styling hook",
  );
  assert.match(
    componentSource,
    /className="tool-console-subtitle-overflow inline-flex items-end shrink-0 h-5 pb-\[1px\] text-xs font-normal leading-none text-theme-text-tertiary tabular-nums"/,
    "subtitle overflow count should align to the same baseline as visible tags",
  );
  assert.doesNotMatch(
    componentSource,
    /tool-console-command-pill|tool-console-command-text/,
    "subtitle should not use command-specific font or presentation hooks",
  );
  assert.doesNotMatch(
    readFileSync(
      new URL("../../../../../styles/components.css", import.meta.url),
      "utf8",
    ),
    /tool-console-subtitle(?:-pill|-chip)\s*\{[\s\S]*?border-bottom:/,
    "subtitle styling should not render underline rules",
  );
});

test("tool result panel exposes console chrome styling hooks", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const componentsSource = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    componentSource,
    /className=\{`tool-console-panel w-full flex flex-col bg-theme-bg-card pointer-events-auto/,
    "panel root should expose a stable console chrome class",
  );
  assert.match(
    componentSource,
    /data-tool-panel-mode=\{panelMode\}/,
    "panel root should expose the current presentation mode for styling",
  );
  assert.match(
    componentsSource,
    /\.tool-console-panel\[data-tool-panel-mode="sidebar"\]/,
    "sidebar mode should receive dedicated console panel styling",
  );
  assert.match(
    componentsSource,
    /\.tool-console-panel\[data-tool-panel-mode="sidebar"\]\s*\{[\s\S]*height:\s*calc\(100% - 1\.5rem\);[\s\S]*margin:\s*0\.75rem;/,
    "desktop sidebar mode should leave breathing room instead of filling the viewport",
  );
  assert.match(
    componentsSource,
    /\.tool-console-panel\[data-tool-panel-mode="sidebar"\]\[data-sidebar-panel\]\s*\{[\s\S]*width:\s*calc\(var\(--sidebar-preview-width, 60%\) - 1\.5rem\) !important;[\s\S]*max-width:\s*calc\(var\(--sidebar-preview-width, 60%\) - 1\.5rem\) !important;/,
    "floating sidebar width should subtract horizontal margins so its border is not clipped",
  );
  assert.doesNotMatch(
    componentSource,
    /data-tool-panel-status=\{status\}/,
    "panel root should not expose unused status styling hooks",
  );
  assert.doesNotMatch(
    componentsSource,
    /\.tool-console-header-icon::after/,
    "header icon should not render an extra corner status dot",
  );
});

test("tool result panel masks rich content until the first panel paint settles", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    componentSource,
    /const \[contentReady, setContentReady\] = useState\(false\)/,
    "panel should track whether rich content is ready to reveal",
  );
  assert.match(
    componentSource,
    /requestAnimationFrame\(\(\) => \{\s*frameIds\.push\(\s*requestAnimationFrame\(\(\) => \{/s,
    "panel should wait for two animation frames so lazy markdown and code viewers can settle",
  );
  assert.match(
    componentSource,
    /aria-busy=\{!contentReady\}/,
    "body should expose busy state while the reveal mask is active",
  );
  assert.match(
    componentSource,
    /className=\{`tool-console-body__content h-full min-h-full[\s\S]*?\$\{\s*contentReady \? "opacity-100" : "opacity-0"/,
    "rich content should keep a full-height parent while visually hidden until ready",
  );
  assert.match(
    componentSource,
    /tool-console-body__loading/s,
    "panel should show a loading overlay while rich content is hidden",
  );
});

test("tool detail sections keep visible separation in light mode", () => {
  const componentsSource = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    componentsSource,
    /\.tool-detail-section\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?box-shadow:/,
    "detail sections should use a card surface and shadow so light mode blocks do not blend into the page background",
  );
  assert.match(
    componentsSource,
    /\.tool-detail-section\.is-expanded\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?0 8px 24px -18px/,
    "expanded detail sections should keep a stronger but restrained light-mode elevation",
  );
  assert.match(
    componentsSource,
    /\.dark \.tool-detail-section\s*\{[\s\S]*?background:\s*color-mix\(in srgb, var\(--theme-bg\) 35%, transparent\);/,
    "dark mode should retain its existing lower-contrast dark surface treatment",
  );
});
