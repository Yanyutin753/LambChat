import { existsSync, readFileSync } from "node:fs";

function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

interface OverlayExpectation {
  name: string;
  path: string;
  pattern: RegExp;
}

// 全屏浮层的可见 chrome（顶栏/关闭按钮/底部操作行）不允许顶到系统栏下面：
// 顶/底 inset 走 safe-area-viewport-padding（或 calc 变量），横屏刘海走 safe-area-x。
const overlayExpectations: OverlayExpectation[] = [
  {
    name: "ToolResultPanel keeps safe-area padding in fullscreen mode",
    path: "../../chat/ChatMessage/items/ToolResultPanel.tsx",
    pattern:
      /fixed inset-0 z-\[200\] flex flex-col safe-area-viewport-padding safe-area-x/,
  },
  {
    name: "DocumentPreviewToolbar fullscreen exit button offsets below the status bar",
    path: "../../documents/DocumentPreviewToolbar.tsx",
    pattern:
      /top: "calc\(1rem \+ var\(--app-safe-area-top-active, var\(--app-safe-area-top, 0px\)\)\)"/,
  },
  {
    name: "NotificationBanner detail dialog delegates to the safe-area padded selector portal",
    path: "../../notification/NotificationBanner.tsx",
    pattern: /<SelectorModalPortal open onClose=\{closeSelectedNotification\}>/,
  },
  {
    name: "SkillPreviewModal wrapper respects viewport insets",
    path: "../../panels/MarketplacePanel/SkillPreviewModal.tsx",
    pattern: /safe-area-viewport-padding fixed inset-0 z-\[1200\]/,
  },
  {
    name: "ImageViewer fullscreen wrapper pads landscape insets",
    path: "../ImageViewer.tsx",
    pattern: /safe-area-x fixed inset-0 z-\[300\] flex flex-col/,
  },
  {
    name: "VideoViewer fullscreen wrapper pads landscape insets",
    path: "../VideoViewer.tsx",
    pattern: /safe-area-x fixed inset-0 z-\[300\] flex flex-col/,
  },
  {
    name: "MermaidDiagram fullscreen wrapper pads landscape insets",
    path: "../../chat/ChatMessage/MermaidDiagram.tsx",
    pattern: /safe-area-x fixed inset-0 z-\[300\] flex flex-col/,
  },
  {
    name: "ExcalidrawPreview fullscreen wrapper pads landscape insets",
    path: "../../documents/previews/ExcalidrawPreview.tsx",
    pattern: /safe-area-x fixed inset-0 z-\[300\] flex flex-col/,
  },
];

// 底部弹层：外层容器只避让顶部系统栏（safe-area-viewport-padding-top），
// 不允许再用 padding-bottom 把 sheet 整体顶离屏幕底边——否则遮罩会在
// home indicator 区域露出一条缝隙。底部 inset 必须由 sheet 表面自己承担
// （safe-area-bottom，背景随 padding 铺满到物理底边）。
const bottomSheetWrapperExpectations: OverlayExpectation[] = [
  {
    name: "ProfileModal wrapper only avoids the status bar",
    path: "../../profile/ProfileModal.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[300\] flex items-end/,
  },
  {
    name: "ShareDialog wrapper only avoids the status bar",
    path: "../../share/ShareDialog.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[300\] flex items-end/,
  },
  {
    name: "ShareProjectDialog wrapper only avoids the status bar",
    path: "../../share/ShareProjectDialog.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[300\] flex items-end/,
  },
  {
    name: "FeedbackDialog wrapper only avoids the status bar",
    path: "../../chat/ChatMessage/FeedbackDialog.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[300\] flex items-end/,
  },
  {
    name: "SessionPreviewDialog wrapper only avoids the status bar",
    path: "../../sidebar/SessionPreviewDialog.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[300\] flex items-end/,
  },
  {
    name: "FeedbackPanel wrapper only avoids the status bar",
    path: "../../panels/FeedbackPanel.tsx",
    pattern: /safe-area-viewport-padding-top fixed inset-0 z-50 flex items-end/,
  },
  {
    name: "TeamPickerModal wrapper only avoids the status bar",
    path: "../../team/TeamPickerModal.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[290\] flex items-end/,
  },
  {
    name: "PersonaPresetSelector wrapper only avoids the status bar",
    path: "../../persona/PersonaPresetSelector.tsx",
    pattern:
      /safe-area-viewport-padding-top fixed inset-0 z-\[290\] flex items-end/,
  },
  {
    name: "PublishDialog wrapper only avoids the status bar",
    path: "../../panels/SkillsPanel/PublishDialog.tsx",
    pattern: /safe-area-viewport-padding-top fixed inset-0 z-50 flex items-end/,
  },
  {
    name: "AgentOptionButton fullscreen sheet wrapper only avoids the status bar",
    path: "../../chat/AgentOptionButton.tsx",
    pattern:
      /safe-area-viewport-padding-top sm:hidden fixed inset-0 z-\[9999\] flex flex-col justify-end/,
  },
  {
    name: "SelectorModal container no longer lifts children off the bottom edge",
    path: "../../selectors/shared/SelectorModal.tsx",
    pattern:
      /safe-area-x fixed z-\[301\] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0/,
  },
  {
    name: "AgentOptionButton dropdown container no longer lifts children off the bottom edge",
    path: "../../chat/AgentOptionButton.tsx",
    pattern: /className="fixed z-\[301\] sm:inset-0/,
  },
  {
    name: "MobileMoreMenuSheet pads only the bottom inset",
    path: "../../panels/SidebarParts/MobileMoreMenuSheet.tsx",
    pattern: /safe-area-x safe-area-bottom fixed bottom-0/,
  },
  {
    name: "SessionMenu pads only the bottom inset",
    path: "../../sidebar/SessionMenu.tsx",
    pattern: /safe-area-x safe-area-bottom fixed bottom-0/,
  },
  {
    name: "UserMenu sheet pads only the bottom inset",
    path: "../../layout/UserMenu.tsx",
    pattern: /safe-area-bottom fixed inset-x-0 bottom-0 z-\[101\]/,
  },
  {
    name: "ProjectMenu sheet pads only the bottom inset",
    path: "../../sidebar/ProjectMenu.tsx",
    pattern: /safe-area-bottom fixed bottom-0 left-0 right-0 z-50/,
  },
];

for (const { name, path, pattern } of overlayExpectations) {
  test(name, () => {
    const source = readSource(path);
    expect(source).not.toBe("");
    expect(source).toMatch(pattern);
  });
}

for (const { name, path, pattern } of bottomSheetWrapperExpectations) {
  test(name, () => {
    const source = readSource(path);
    expect(source).not.toBe("");
    expect(source).toMatch(pattern);
    // 弹层容器不得用 padding-bottom 把 sheet 顶离屏幕底边（遮罩会露缝）
    expect(source).not.toMatch(/safe-area-viewport-padding fixed inset-0/);
  });
}

// 底部弹层的 sheet 表面必须自带底部 inset：背景铺满到物理底边，
// 同时保证 footer/按钮不被 home indicator 挡住。
const bottomSheetSurfaceExpectations: OverlayExpectation[] = [
  {
    name: "ProfileModal mobile sheet carries the bottom inset itself",
    path: "../../profile/ProfileModal.tsx",
    pattern: /sm:hidden relative z-10 w-full bg-white[^"]*safe-area-bottom/,
  },
  {
    name: "SessionPreviewDialog sheet carries the bottom inset itself",
    path: "../../sidebar/SessionPreviewDialog.tsx",
    pattern: /relative z-10 w-full sm:max-w-2xl[^"]*safe-area-bottom/,
  },
  {
    name: "FeedbackPanel sheet carries the bottom inset itself",
    path: "../../panels/FeedbackPanel.tsx",
    pattern: /w-full sm:max-w-lg bg-white[^"]*safe-area-bottom/,
  },
  {
    name: "TeamPickerModal sheet carries the bottom inset itself",
    path: "../../team/TeamPickerModal.tsx",
    pattern:
      /flex max-h-\[90dvh\] w-full flex-col overflow-hidden rounded-t-2xl[^"]*safe-area-bottom/,
  },
  {
    name: "PersonaPresetSelector sheet carries the bottom inset itself",
    path: "../../persona/PersonaPresetSelector.tsx",
    pattern:
      /flex max-h-\[90dvh\] w-full flex-col overflow-hidden rounded-t-2xl[^"]*safe-area-bottom/,
  },
  {
    name: "PublishDialog sheet carries the bottom inset itself",
    path: "../../panels/SkillsPanel/PublishDialog.tsx",
    pattern: /skill-theme-shell w-full max-w-lg[^"]*safe-area-bottom/,
  },
  {
    name: "AgentOptionButton dropdown surfaces keep bottom padding above the inset",
    path: "../../chat/AgentOptionButton.tsx",
    pattern: /rounded-t-2xl shadow-2xl px-4 pt-3 safe-area-bottom/,
  },
  {
    name: "AgentOptionButton fullscreen sheet surface keeps bottom padding above the inset",
    path: "../../chat/AgentOptionButton.tsx",
    pattern: /relative rounded-t-2xl px-4 pt-3 safe-area-bottom/,
  },
  {
    name: "SelectorModal shell carries the bottom inset for all selector consumers",
    path: "../../selectors/shared/SelectorModalShell.tsx",
    pattern: /SELECTOR_MODAL_SHELL_CLASS[\s\S]*safe-area-bottom/,
  },
  // 这三个弹层 sheet 根部不加 padding，footer 已内嵌 inset 避让，防止双重避让
  {
    name: "ShareDialog footer keeps its inner bottom inset",
    path: "../../share/ShareDialog.tsx",
    pattern:
      /safe-area-bottom flex items-center justify-end gap-2 px-5 pt-4 \[--safe-area-bottom-extra:1rem\]/,
  },
  {
    name: "ShareProjectDialog footer keeps its inner bottom inset",
    path: "../../share/ShareProjectDialog.tsx",
    pattern:
      /safe-area-bottom flex items-center justify-end gap-2 px-5 pt-4 \[--safe-area-bottom-extra:1rem\]/,
  },
  {
    name: "FeedbackDialog footer keeps its inner bottom inset",
    path: "../../chat/ChatMessage/FeedbackDialog.tsx",
    pattern:
      /safe-area-bottom flex items-center justify-end gap-2 px-5 pt-4 \[--safe-area-bottom-extra:1rem\]/,
  },
];

for (const { name, path, pattern } of bottomSheetSurfaceExpectations) {
  test(name, () => {
    const source = readSource(path);
    expect(source).not.toBe("");
    expect(source).toMatch(pattern);
  });
}
