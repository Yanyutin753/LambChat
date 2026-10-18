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

test("mobile tool panels use a full workspace without swipe-to-close", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const sidebarPanelHookSource = readFileSync(
    new URL("../../../../../hooks/useSidebarPanel.ts", import.meta.url),
    "utf8",
  );

  expect(sidebarPanelHookSource).not.toMatch(/useSwipeToClose/);
  expect(componentSource).not.toMatch(/ref=\{dragHandleRef\}/);
  expect(componentSource).toMatch(/isMobile\s*\?\s*"h-full min-h-full/);
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
    /useSidebarPanel\(\{\s*open: entry\.active,\s*onClose: handleUserClose,/s,
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

test("tab closure delegates to handleUserClose for panel dismissal", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /const handleUserClose = useCallback\(\(\) => \{\s*onUserClose\?\.\(\);\s*clearSidebarHistory\(\);\s*onClose\(\);/s,
  );
  expect(componentSource).toMatch(
    /useRightPanelEntry\(\{[\s\S]*?onClose: handleUserClose,/,
  );
  expect(componentSource).toMatch(/handleUserClose\(\)/);
});

test("all tool result headers keep title and context on one baseline with full text available", () => {
  const source = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toMatch(
    /tool-console-title-row flex items-baseline gap-2 min-w-0 flex-1/,
  );
  expect(source).toMatch(/tool-console-title min-w-0 max-w-full truncate/);
  expect(source).toMatch(
    /tool-console-subtitle-pill min-w-0 max-w-full truncate/,
  );
  expect(source).toMatch(/tool-console-subtitle-pill[^"\n]*font-normal/);
  expect(source).toMatch(/title=\{title\}/);
  expect(source).not.toContain("subtitle.split");
  expect(source).not.toContain("max-w-[40%]");
  expect(source).not.toContain("max-w-[45vw]");
  expect(source).toMatch(/title=\{subtitle\}\s*>\s*\{subtitle\}\s*<\/span>/s);
});

test("tool result header icons have no background or border decoration", () => {
  const source = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  const iconClasses = source.match(
    /className=.[^\n]*tool-console-header-icon[^\n]*/,
  )?.[0];
  expect(iconClasses).toBeTruthy();
  expect(iconClasses).not.toMatch(/rounded|cfg\.bg|border|bg-/);
  expect(css).not.toMatch(/\.tool-console-header-icon\s*\{/);
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
    /\.tool-console-panel\[data-tool-panel-mode="sidebar"\]\[data-sidebar-panel\]\s*\{[\s\S]*width:\s*calc\(var\(--sidebar-preview-width, 40%\) - 1\.5rem\) !important;[\s\S]*max-width:\s*calc\(var\(--sidebar-preview-width, 40%\) - 1\.5rem\) !important;/,
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
  expect(componentSource).toMatch(/<RightPanelTabs\s+viewControls=/);
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
    /\.tool-console-resize-handle__rail\s*\{[\s\S]*?box-shadow:/,
  );
  expect(componentsSource).toMatch(
    /\.tool-console-body__loading\s*\{[\s\S]*?color-mix\(in srgb, var\(--theme-bg\) 92%, transparent\);/,
  );
});

test("tool result actions share a non-wrapping toolbar with touch-sized controls", () => {
  const tabs = readFileSync(
    new URL("../../../../common/RightPanelTabs.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(
    new URL("../../../../common/rightPanelTabs.css", import.meta.url),
    "utf8",
  );
  expect(tabs).toContain('className="right-panel-tab-actions"');
  expect(css).toMatch(
    /\.right-panel-tab-actions\s*\{[^}]*display: flex;[^}]*flex: 0 0 auto;/,
  );
  expect(css).toMatch(
    /\.right-panel-view-action[^{}]*\{[^}]*width: 2\.25rem;[^}]*height: 2\.25rem;/,
  );
  expect(css).toMatch(
    /@media \(pointer: coarse\), \(max-width: 639px\)\s*\{[\s\S]*?\.right-panel-view-action\s*\{[^}]*width: 2\.25rem;[^}]*height: 2\.25rem;/,
  );
});
test("tool result panel masks rich content until snapshot restoration settles", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /const \[contentReady, setContentReady\] = useState\(false\)/,
  );
  expect(componentSource).toMatch(/restorePendingSidebarPanelSnapshot/);
  expect(componentSource).toMatch(
    /if \(!restored\) await waitForInitialPaint\(\);\s*if \(!cancelled\) setContentReady\(true\);/s,
  );
  expect(componentSource).toMatch(/aria-busy=\{!contentReady\}/);
  expect(componentSource).toMatch(
    /className=\{`tool-console-body__content tool-readable h-full min-h-full[\s\S]*?\$\{\s*contentReady \? "opacity-100" : "opacity-0"/,
  );
  expect(componentSource).toMatch(/tool-console-body__loading/s);
});

test("tool result panel resets first-paint state for a new registry panel but not streamed content", () => {
  const componentSource = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );

  expect(componentSource).toMatch(
    /useEffect\(\(\) => \{[\s\S]*?setContentReady\(false\)[\s\S]*?\}, \[open, panelRef, registryKey\]\);/,
  );
  expect(componentSource).not.toMatch(/\}, \[open, children\]\);/);
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

test("tool detail text stays within its parent and uses slightly smaller body typography", () => {
  const css = readFileSync(
    new URL("../../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  const source = readFileSync(
    new URL("../ToolResultPanel.tsx", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.tool-readable\s*\{[^}]*font-family: var\(--chat-font-family\);[^}]*font-size: var\(--tool-font-size\);/,
  );
  expect(css).toMatch(
    /\.tool-readable :is\(\.text-12, \.text-13\)\s*\{[^}]*font-size: var\(--tool-font-size\);/,
  );
  expect(css).toMatch(
    /\.tool-readable \.tool-detail-section__title\s*\{[^}]*font-family: inherit;/,
  );
  expect(css).toMatch(
    /\.tool-readable :is\(\.markdown-preview, \.sidebar-reasoning-preview__scroll\)\s*\{[^}]*font-size: var\(--tool-font-size\);/,
  );
  expect(source).not.toMatch(/tool-readable font-serif/);
  expect(css).toMatch(
    /\.tool-detail-section\s*\{[^}]*min-width: 0;[^}]*max-width: 100%;/,
  );
  expect(css).toMatch(
    /\.tool-detail-section__body\s*\{[^}]*overflow-wrap: anywhere;/,
  );
});
