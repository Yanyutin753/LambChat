import { readFileSync } from "node:fs";
import { resolve } from "node:path";
function readSource(path: string): string {
  return readFileSync(resolve(import.meta.dirname, path), "utf8");
}

test("safe-area utility classes map to native inset variables", () => {
  const tokens = readSource("../styles/tokens.css");
  const utilities = readSource("../styles/utilities.css");

  expect(tokens).toMatch(/--app-safe-area-top-active:\s*max\(/);
  expect(tokens).toMatch(/--app-safe-area-bottom-active:\s*max\(/);
  expect(utilities).toMatch(
    /\.safe-area-top\s*\{[\s\S]*padding-top:\s*calc\(\s*var\(--app-safe-area-top-active,/,
  );
  expect(utilities).toMatch(
    /\.safe-area-bottom\s*\{[\s\S]*padding-bottom:\s*calc\(\s*var\(--app-safe-area-bottom-active,/,
  );
  expect(utilities).toMatch(/\.safe-area-y\s*\{/);
  expect(utilities).toMatch(/\.safe-area-viewport-padding\s*\{/);
  expect(utilities).toMatch(/\.safe-area-viewport-height\s*\{/);
});

test("the authenticated app shell reserves both status bar and home indicator areas", () => {
  const shell = readSource("../components/layout/AppContent/AppShell.tsx");

  expect(shell).toMatch(
    /const appSafeAreaTop =\s*"var\(--app-safe-area-top-active,/,
  );
  expect(shell).toMatch(
    /const appSafeAreaBottom =\s*"var\(--app-safe-area-bottom-active,/,
  );
  expect(shell).toMatch(/paddingTop:\s*appSafeAreaTop/);
  expect(shell).toMatch(/paddingBottom:\s*appSafeAreaBottom/);
  expect(shell).toMatch(
    /height:\s*`calc\(var\(--app-viewport-height, 100dvh\) - \$\{appSafeAreaTop\} - \$\{appSafeAreaBottom\}\)`/,
  );
});

test("public landing page header, mobile menu, and footer use safe-area spacing", () => {
  const navbar = readSource("../components/landing/components/Navbar.tsx");
  const mobileMenu = readSource(
    "../components/landing/components/MobileMenu.tsx",
  );
  const footer = readSource("../components/landing/components/Footer.tsx");

  expect(navbar).toMatch(/className=\{`[^`]*\bsafe-area-top\b/);
  expect(mobileMenu).toMatch(
    /\btop-\[calc\(3\.5rem\+var\(--app-safe-area-top,0px\)\)\]/,
  );
  expect(footer).toMatch(/className="[^"]*\bsafe-area-bottom\b/);
});

test("auth and shared public pages protect their fixed headers and bottom bars", () => {
  const auth = readSource("../components/auth/AuthPage.tsx");
  const shared = readSource("../components/share/SharedPage.tsx");

  expect(auth).toMatch(/className="[^"]*\bsafe-area-top\b/);
  expect(auth).toMatch(/className="[^"]*\bsafe-area-bottom\b/);
  expect(shared).toMatch(/className="[^"]*\bsafe-area-top\b/);
  expect(shared).toMatch(/className="[^"]*\bsafe-area-bottom\b/);
});

test("sidebars, fullscreen editors, and media viewers use vertical safe-area spacing", () => {
  const components = readSource("../styles/components.css");
  const sessionSidebar = readSource("../components/panels/SessionSidebar.tsx");
  const skillForm = readSource("../components/skill/SkillForm.tsx");
  const skillFullscreen = readSource(
    "../components/skill/SkillFormFullscreen.tsx",
  );
  const imageViewer = readSource("../components/common/ImageViewer.tsx");
  const videoViewer = readSource("../components/common/VideoViewer.tsx");
  const viewerTopBar = readSource("../components/common/ViewerTopBar.tsx");
  const excalidrawThumbnail = readSource(
    "../components/common/ExcalidrawThumbnail.tsx",
  );
  const toolResultPanel = readSource(
    "../components/chat/ChatMessage/items/ToolResultPanel.tsx",
  );
  const excalidrawPreview = readSource(
    "../components/documents/previews/ExcalidrawPreview.tsx",
  );
  const excalidrawDirectViewer = readSource(
    "../components/documents/previews/ExcalidrawDirectViewer.tsx",
  );
  const mermaidViewer = readSource(
    "../components/chat/ChatMessage/MermaidDiagram.tsx",
  );

  expect(components).toMatch(
    /\.editor-sidebar--sidebar\s*\{[\s\S]*top:\s*var\(--app-safe-area-top-active,/,
  );
  expect(components).toMatch(
    /\.editor-sidebar--sidebar\s*\{[\s\S]*bottom:\s*var\(\s*--app-safe-area-bottom-active,/,
  );
  expect(components).toMatch(
    /\.editor-sidebar--mobile\s*\{[\s\S]*bottom:\s*var\(\s*--app-safe-area-bottom-active,/,
  );
  expect(components).toMatch(
    /\.editor-sidebar-footer\s*\{[\s\S]*padding-bottom:\s*max\([\s\S]*var\(--app-safe-area-bottom-active,/,
  );

  expect(sessionSidebar).toMatch(/top:\s*"var\(--app-safe-area-top-active,/);
  expect(sessionSidebar).toMatch(
    /paddingBottom:\s*"var\(--app-safe-area-bottom-active,/,
  );

  expect(skillForm).toMatch(
    /skill-form--fullscreen safe-area-viewport-padding/,
  );
  expect(skillFullscreen).toMatch(
    /top:\s*"calc\(1rem \+ var\(--app-safe-area-top-active,/,
  );

  expect(viewerTopBar).toMatch(/className=\{clsx\("safe-area-top\b/);
  expect(imageViewer).toMatch(/<ViewerTopBar[\s>]/);
  expect(imageViewer).not.toMatch(/safe-area-bottom/);
  expect(videoViewer).toMatch(/<ViewerTopBar[\s>]/);
  expect(videoViewer).toMatch(/className="safe-area-bottom\b/);
  expect(excalidrawThumbnail).toMatch(/safe-area-viewport-padding/);
  expect(toolResultPanel).toMatch(/safe-area-viewport-padding/);
  expect(excalidrawPreview).toMatch(/<ViewerTopBar[\s>]/);
  expect(excalidrawPreview).not.toMatch(/safe-area-bottom/);
  expect(excalidrawDirectViewer).toMatch(
    /safe-area-viewport-padding fixed inset-0/,
  );
  expect(mermaidViewer).toMatch(/<ViewerTopBar[\s>]/);
  expect(mermaidViewer).not.toMatch(/safe-area-bottom/);
});

test("portal dialogs and sheets reserve safe-area spacing", () => {
  const safeViewportFiles = [
    "../components/common/AboutDialog.tsx",
    "../components/common/ConfirmDialog.tsx",
    "../components/common/ContactAdminDialog.tsx",
    "../components/common/DeleteProjectDialog.tsx",
    "../components/profile/ProfileModal.tsx",
    "../components/notification/NotificationDialog.tsx",
    "../components/team/TeamPickerModal.tsx",
    "../components/persona/PersonaPresetSelector.tsx",
    "../components/panels/SearchDialog.tsx",
    "../components/panels/NewProjectModal.tsx",
    "../components/panels/SkillsPanel/PublishDialog.tsx",
    "../components/share/ShareDialog.tsx",
    "../components/chat/ChatMessage/FeedbackDialog.tsx",
    "../components/sidebar/SessionPreviewDialog.tsx",
    "../components/chat/ChatInputShortcuts.tsx",
    // SelectRow（含 safe-area 弹层）已从 ProfilePreferencesTab 抽取为共享组件
    "../components/profile/SelectRow.tsx",
    "../components/documents/LazyDocumentPreview.tsx",
    "../components/panels/NotificationPanel.tsx",
    "../components/panels/FeedbackPanel.tsx",
    "../components/layout/AppContent/ChatAppContent.tsx",
    "../components/chat/AgentOptionButton.tsx",
    "../components/layout/UserMenu.tsx",
    "../components/sidebar/ProjectMenu.tsx",
    "../components/sidebar/SessionMenu.tsx",
    "../components/panels/SidebarParts/MobileMoreMenuSheet.tsx",
  ];

  for (const path of safeViewportFiles) {
    expect(readSource(path)).toMatch(/safe-area-viewport-padding/);
  }
});

test("profile mobile sheet relies on the portal viewport safe area only", () => {
  const profileModal = readSource("../components/profile/ProfileModal.tsx");

  expect(profileModal).toMatch(
    /className="safe-area-viewport-padding fixed inset-0 z-\[300\] flex items-end/,
  );
  expect(profileModal).not.toMatch(
    /renderFooter\(\s*"[^"]*\bsafe-area-bottom\b/,
  );
  expect(profileModal).not.toMatch(
    /renderFooter\(\s*"[^"]*--safe-area-bottom-extra/,
  );
});

test("standalone full-page fallback surfaces use safe-area spacing", () => {
  const oauth = readSource("../components/auth/OAuthCallback.tsx");
  const protectedRoute = readSource("../components/auth/ProtectedRoute.tsx");
  const notFound = readSource("../components/common/NotFoundPage.tsx");
  const errorBoundary = readSource("../components/common/ErrorBoundary.tsx");
  const welcome = readSource("../styles/welcome.css");

  expect(oauth).toMatch(/safe-area-viewport-padding/);
  expect(protectedRoute).toMatch(/safe-area-viewport-padding/);
  expect(notFound).toMatch(/safe-area-viewport-padding/);
  expect(errorBoundary).toMatch(/safe-area-viewport-padding/);
  expect(welcome).toMatch(/--app-safe-area-top-active/);
  expect(welcome).toMatch(/--app-safe-area-bottom-active/);
});
