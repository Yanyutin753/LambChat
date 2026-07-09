import { readFileSync } from "node:fs";
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

  expect(slideUpAnimation).toBeTruthy();
  expect(slideUpAnimation).not.toMatch(/\bopacity\s*:/);
  expect(componentSource).not.toMatch(
    /transform:\s*"translateY\(100%\)"\s*,\s*opacity:\s*0/,
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

  expect(swipeHookSource).toMatch(
    /dragHandleRef\?: RefObject<HTMLElement \| null>/,
  );
  expect(sidebarPanelHookSource).toMatch(/dragHandleRef,\s*\}\);/);
  expect(componentSource).toMatch(/ref=\{dragHandleRef\}/);
});

test("explicit close button reports a user close before closing the panel", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(/onUserClose\?: \(\) => void/);
  expect(componentSource).toMatch(
    /const handleUserClose = useCallback\(\(\) => \{\s*onUserClose\?\.\(\);\s*clearSidebarHistory\(\);\s*onClose\(\);/s,
  );
  expect(componentSource).toMatch(
    /useSidebarPanel\(\{\s*open,\s*onClose: handleUserClose,/s,
  );
});

test("tool result overlay reserves vertical safe-area spacing", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /className=\{`fixed inset-0 z-\[200\] flex flex-col/,
  );
  expect(componentSource).toMatch(/safe-area-viewport-padding/);
});

test("close button delegates to handleUserClose for panel dismissal", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /const handleUserClose = useCallback\(\(\) => \{\s*onUserClose\?\.\(\);\s*clearSidebarHistory\(\);\s*onClose\(\);/s,
  );
  expect(componentSource).toMatch(/aria-label=\{t\("common\.close"\)\}/);
  expect(componentSource).toMatch(/handleUserClose\(\)/);
});

test("tool result header truncates long titles and subtitles on narrow screens", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /className="tool-console-title-row flex items-end gap-2 min-w-0 flex-1 overflow-hidden"/,
  );
  expect(componentSource).toMatch(
    /className="tool-console-title min-w-0 max-w-\[40%\] truncate font-medium text-sm text-theme-text"/,
  );
  expect(componentSource).toMatch(
    /className="tool-console-subtitle-pill inline-flex h-5 min-w-0 max-w-\[45vw\] sm:max-w-\[min\(32rem,52%\)\] items-end overflow-hidden px-0 pb-\[1px\] text-xs font-normal leading-none text-theme-text-tertiary"/,
  );
  expect(componentSource).toMatch(
    /<span className="block min-w-0 truncate">\s*\{subtitle\}\s*<\/span>/s,
  );
  expect(componentSource).toMatch(
    /className="tool-console-subtitle-list inline-flex items-end gap-1 min-w-0 max-w-\[45vw\] sm:max-w-\[min\(32rem,52%\)\] overflow-hidden"/,
  );
  expect(componentSource).toMatch(
    /className="tool-console-subtitle-chip inline-flex items-end shrink-0 max-w-full px-0 h-5 pb-\[1px\] text-xs font-normal leading-none text-theme-text-tertiary"/,
  );
  expect(componentSource).toMatch(
    /className="tool-console-subtitle-overflow inline-flex items-end shrink-0 h-5 pb-\[1px\] text-xs font-normal leading-none text-theme-text-tertiary tabular-nums"/,
  );
  expect(componentSource).not.toMatch(
    /tool-console-command-pill|tool-console-command-text/,
  );
  expect(
    readFileSync(
      new URL("../../../../../styles/components.css", import.meta.url),
      "utf8",
    ),
  ).not.toMatch(
    /tool-console-subtitle(?:-pill|-chip)\s*\{[\s\S]*?border-bottom:/,
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

  expect(componentSource).toMatch(
    /className=\{`tool-console-panel w-full flex flex-col bg-theme-bg-card pointer-events-auto/,
  );
  expect(componentSource).toMatch(/data-tool-panel-mode=\{panelMode\}/);
  expect(componentsSource).toMatch(
    /\.tool-console-panel\[data-tool-panel-mode="sidebar"\]/,
  );
  expect(componentsSource).toMatch(
    /:where\(\s*\.editor-sidebar--sidebar\s*,\s*\.tool-console-panel\[data-tool-panel-mode="sidebar"\]\s*\)\s*\{[\s\S]*height:\s*var\(--right-sidebar-height, calc\(100% - 1\.5rem\)\);[\s\S]*margin:\s*0\.75rem;/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-panel\[data-tool-panel-mode="sidebar"\]\[data-sidebar-panel\]\s*\{[\s\S]*width:\s*calc\(var\(--sidebar-preview-width, 60%\) - 1\.5rem\) !important;[\s\S]*max-width:\s*calc\(var\(--sidebar-preview-width, 60%\) - 1\.5rem\) !important;/,
  );
  expect(componentSource).not.toMatch(/data-tool-panel-status=\{status\}/);
  expect(componentsSource).not.toMatch(/\.tool-console-header-icon::after/);
});

test("tool result panel uses refined professional chrome treatment", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const componentsSource = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(/tool-console-resize-handle/);
  expect(componentSource).toMatch(/tool-console-actions/);
  expect(componentSource).toMatch(/tool-console-body__loading/);
  expect(componentsSource).toMatch(
    /\.tool-console-panel\s*\{[\s\S]*?--tool-console-surface-glow:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-panel\[data-tool-panel-mode="center"\]\s*\{[\s\S]*?box-shadow:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-header\s*\{[\s\S]*?padding-inline:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-actions\s*\{[\s\S]*?background:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-resize-handle__rail\s*\{[\s\S]*?box-shadow:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-body__loading\s*\{[\s\S]*?color-mix\(in srgb, var\(--theme-bg\) 92%, transparent\);/,
  );
});

test("tool result panel masks rich content until the first panel paint settles", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /const \[contentReady, setContentReady\] = useState\(false\)/,
  );
  expect(componentSource).toMatch(
    /requestAnimationFrame\(\(\) => \{\s*frameIds\.push\(\s*requestAnimationFrame\(\(\) => \{/s,
  );
  expect(componentSource).toMatch(/aria-busy=\{!contentReady\}/);
  expect(componentSource).toMatch(
    /className=\{`tool-console-body__content h-full min-h-full[\s\S]*?\$\{\s*contentReady \? "opacity-100" : "opacity-0"/,
  );
  expect(componentSource).toMatch(/tool-console-body__loading/s);
});

test("tool detail sections keep visible separation in light mode", () => {
  const componentsSource = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  expect(componentsSource).toMatch(
    /\.tool-detail-section\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?box-shadow:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-detail-section\.is-expanded\s*\{[\s\S]*?background:\s*var\(--theme-bg-card\);[\s\S]*?0 8px 24px -18px/,
  );
  expect(componentsSource).toMatch(
    /\.dark \.tool-detail-section\s*\{[\s\S]*?background:\s*color-mix\(in srgb, var\(--theme-bg\) 35%, transparent\);/,
  );
});
