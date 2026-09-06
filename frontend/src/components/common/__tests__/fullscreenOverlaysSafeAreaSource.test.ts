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
  {
    name: "SelectorModal bottom sheet pads landscape insets",
    path: "../../selectors/shared/SelectorModal.tsx",
    pattern: /safe-area-x safe-area-viewport-padding fixed z-\[301\]/,
  },
  {
    name: "MobileMoreMenuSheet pads landscape insets",
    path: "../../panels/SidebarParts/MobileMoreMenuSheet.tsx",
    pattern: /safe-area-x safe-area-viewport-padding fixed bottom-0/,
  },
  {
    name: "SessionMenu bottom sheet pads landscape insets",
    path: "../../sidebar/SessionMenu.tsx",
    pattern: /safe-area-x safe-area-viewport-padding fixed bottom-0/,
  },
];

for (const { name, path, pattern } of overlayExpectations) {
  test(name, () => {
    const source = readSource(path);
    expect(source).not.toBe("");
    expect(source).toMatch(pattern);
  });
}
