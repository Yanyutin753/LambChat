import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

function readSource(path: string): string {
  return readFileSync(resolve(import.meta.dirname, path), "utf8");
}

test("safe-area utility classes map to native inset variables", () => {
  const tokens = readSource("../styles/tokens.css");
  const utilities = readSource("../styles/utilities.css");

  assert.match(tokens, /--app-safe-area-top-active:\s*max\(/);
  assert.match(tokens, /--app-safe-area-bottom-active:\s*max\(/);
  assert.match(
    utilities,
    /\.safe-area-top\s*\{[\s\S]*padding-top:\s*calc\(\s*var\(--app-safe-area-top-active,/,
  );
  assert.match(
    utilities,
    /\.safe-area-bottom\s*\{[\s\S]*padding-bottom:\s*calc\(\s*var\(--app-safe-area-bottom-active,/,
  );
  assert.match(utilities, /\.safe-area-y\s*\{/);
  assert.match(utilities, /\.safe-area-viewport-padding\s*\{/);
  assert.match(utilities, /\.safe-area-viewport-height\s*\{/);
});

test("the authenticated app shell reserves both status bar and home indicator areas", () => {
  const shell = readSource("../components/layout/AppContent/AppShell.tsx");

  assert.match(
    shell,
    /const appSafeAreaTop =\s*"var\(--app-safe-area-top-active,/,
  );
  assert.match(
    shell,
    /const appSafeAreaBottom =\s*"var\(--app-safe-area-bottom-active,/,
  );
  assert.match(shell, /paddingTop:\s*appSafeAreaTop/);
  assert.match(shell, /paddingBottom:\s*appSafeAreaBottom/);
  assert.match(
    shell,
    /height:\s*`calc\(var\(--app-viewport-height, 100dvh\) - \$\{appSafeAreaTop\} - \$\{appSafeAreaBottom\}\)`/,
  );
});

test("public landing page header, mobile menu, and footer use safe-area spacing", () => {
  const navbar = readSource("../components/landing/components/Navbar.tsx");
  const mobileMenu = readSource(
    "../components/landing/components/MobileMenu.tsx",
  );
  const footer = readSource("../components/landing/components/Footer.tsx");

  assert.match(navbar, /className=\{`[^`]*\bsafe-area-top\b/);
  assert.match(
    mobileMenu,
    /\btop-\[calc\(3\.5rem\+var\(--app-safe-area-top,0px\)\)\]/,
  );
  assert.match(footer, /className="[^"]*\bsafe-area-bottom\b/);
});

test("auth and shared public pages protect their fixed headers and bottom bars", () => {
  const auth = readSource("../components/auth/AuthPage.tsx");
  const shared = readSource("../components/share/SharedPage.tsx");

  assert.match(auth, /className="[^"]*\bsafe-area-top\b/);
  assert.match(auth, /className="[^"]*\bsafe-area-bottom\b/);
  assert.match(shared, /className="[^"]*\bsafe-area-top\b/);
  assert.match(shared, /className="[^"]*\bsafe-area-bottom\b/);
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

  assert.match(
    components,
    /\.editor-sidebar--sidebar\s*\{[\s\S]*top:\s*var\(--app-safe-area-top-active,/,
  );
  assert.match(
    components,
    /\.editor-sidebar--sidebar\s*\{[\s\S]*bottom:\s*var\(\s*--app-safe-area-bottom-active,/,
  );
  assert.match(
    components,
    /\.editor-sidebar--mobile\s*\{[\s\S]*bottom:\s*var\(\s*--app-safe-area-bottom-active,/,
  );
  assert.match(
    components,
    /\.editor-sidebar-footer\s*\{[\s\S]*padding-bottom:\s*max\([\s\S]*var\(--app-safe-area-bottom-active,/,
  );

  assert.match(sessionSidebar, /top:\s*"var\(--app-safe-area-top-active,/);
  assert.match(
    sessionSidebar,
    /paddingBottom:\s*"var\(--app-safe-area-bottom-active,/,
  );

  assert.match(skillForm, /skill-form--fullscreen safe-area-viewport-padding/);
  assert.match(
    skillFullscreen,
    /top:\s*"calc\(1rem \+ var\(--app-safe-area-top-active,/,
  );

  assert.match(viewerTopBar, /className=\{clsx\("safe-area-top\b/);
  assert.match(imageViewer, /<ViewerTopBar[\s>]/);
  assert.match(imageViewer, /className="safe-area-bottom\b/);
  assert.match(videoViewer, /<ViewerTopBar[\s>]/);
  assert.match(videoViewer, /className="safe-area-bottom\b/);
  assert.match(excalidrawThumbnail, /safe-area-viewport-padding/);
  assert.match(toolResultPanel, /safe-area-viewport-padding fixed inset-0/);
  assert.match(excalidrawPreview, /<ViewerTopBar[\s>]/);
  assert.match(excalidrawPreview, /className="safe-area-bottom\b/);
  assert.match(
    excalidrawDirectViewer,
    /safe-area-viewport-padding fixed inset-0/,
  );
  assert.match(mermaidViewer, /<ViewerTopBar[\s>]/);
  assert.match(mermaidViewer, /className="safe-area-bottom\b/);
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
    "../plugins/feedback/FeedbackDialog.tsx",
    "../components/sidebar/SessionPreviewDialog.tsx",
    "../components/chat/ChatInputShortcuts.tsx",
    "../components/profile/tabs/ProfilePreferencesTab.tsx",
    "../components/documents/LazyDocumentPreview.tsx",
    "../components/panels/NotificationPanel.tsx",
    "../plugins/feedback/FeedbackPanel.tsx",
    "../components/layout/AppContent/ChatAppContent.tsx",
    "../components/selectors/AgentModeSelector.tsx",
    "../components/selectors/SkillSelector.tsx",
    "../components/selectors/ToolSelector.tsx",
    "../components/chat/AgentOptionButton.tsx",
    "../components/layout/UserMenu.tsx",
    "../components/sidebar/ProjectMenu.tsx",
    "../components/sidebar/SessionMenu.tsx",
    "../components/panels/SidebarParts/MobileMoreMenuSheet.tsx",
  ];

  for (const path of safeViewportFiles) {
    assert.match(
      readSource(path),
      /safe-area-viewport-padding/,
      `${path} should use safe-area viewport padding`,
    );
  }
});

test("profile mobile sheet relies on the portal viewport safe area only", () => {
  const profileModal = readSource("../components/profile/ProfileModal.tsx");

  assert.match(
    profileModal,
    /className="safe-area-viewport-padding fixed inset-0 z-\[300\] flex items-end/,
  );
  assert.doesNotMatch(
    profileModal,
    /renderFooter\(\s*"[^"]*\bsafe-area-bottom\b/,
  );
  assert.doesNotMatch(
    profileModal,
    /renderFooter\(\s*"[^"]*--safe-area-bottom-extra/,
  );
});

test("standalone full-page fallback surfaces use safe-area spacing", () => {
  const oauth = readSource("../components/auth/OAuthCallback.tsx");
  const protectedRoute = readSource("../components/auth/ProtectedRoute.tsx");
  const notFound = readSource("../components/common/NotFoundPage.tsx");
  const errorBoundary = readSource("../components/common/ErrorBoundary.tsx");
  const welcome = readSource("../styles/welcome.css");

  assert.match(oauth, /safe-area-viewport-padding/);
  assert.match(protectedRoute, /safe-area-viewport-padding/);
  assert.match(notFound, /safe-area-viewport-padding/);
  assert.match(errorBoundary, /safe-area-viewport-padding/);
  assert.match(welcome, /--app-safe-area-top-active/);
  assert.match(welcome, /--app-safe-area-bottom-active/);
});
