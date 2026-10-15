export const NAVIGATION_WIDTH_CHANGED_EVENT = "navigation-width-changed";

export const WIDTH_STORAGE_KEY = "lambchat_desktop_sidebar_width";
export const MIN_WIDTH = 260;
export const MAX_WIDTH_CAP = 480;
const MAX_WIDTH_RATIO = 0.5;

export function clampWidth(value: number): number {
  const cap = Math.min(
    typeof window === "undefined"
      ? MAX_WIDTH_CAP
      : window.innerWidth * MAX_WIDTH_RATIO,
    MAX_WIDTH_CAP,
  );
  return Math.round(Math.min(cap, Math.max(MIN_WIDTH, value)));
}

export function readStoredWidth(): number {
  const viewport = typeof window === "undefined" ? 1280 : window.innerWidth;
  const defaultWidth = viewport >= 1280 ? 320 : viewport >= 1024 ? 288 : 260;
  try {
    const saved = Number(localStorage.getItem(WIDTH_STORAGE_KEY));
    return Number.isFinite(saved) && saved > 0
      ? clampWidth(saved)
      : clampWidth(defaultWidth);
  } catch {
    return clampWidth(defaultWidth);
  }
}

