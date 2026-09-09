/**
 * 动态 import chunk 加载失败的自愈恢复。
 *
 * 桌面端 updater 更新重启后，WebView2 可能仍从磁盘缓存返回旧版
 * index.html，其中引用的旧 hash chunk（如 RichChatComposer-xxx.js）
 * 在新安装目录里已不存在，React.lazy 的动态 import 随即 404 报
 * "Failed to fetch dynamically imported module"。没有恢复路径时用户
 * 只能重装。Vite 生产构建的所有动态 import 都经 __vitePreload 包裹，
 * 失败时派发可取消的 vite:preloadError 事件：这里吞掉错误并带
 * cache-bust 参数 replace 一次（换 URL 绕过文档缓存拿新 index.html），
 * 冷却期内只允许一次，避免真坏掉时无限重载。
 */

const CHUNK_LOAD_ERROR_PATTERNS = [
  // Chromium / WebView2
  "Failed to fetch dynamically imported module",
  // Firefox
  "Importing a module script failed",
  // WebKit
  "error loading dynamically imported module",
  // Vite __vitePreload 的 CSS 依赖预载失败
  "Unable to preload CSS for",
];

export const CHUNK_RELOAD_STORAGE_KEY = "lambchat:chunk-reload-at";
export const CHUNK_RELOAD_COOLDOWN_MS = 30_000;

export function isChunkLoadError(error: unknown): boolean {
  if (!error) return false;
  const message = error instanceof Error ? error.message : String(error);
  return CHUNK_LOAD_ERROR_PATTERNS.some((pattern) =>
    message.includes(pattern),
  );
}

/** 同一 URL 加上/更新 chunk_reload 随机数，强制 webview 重新拉取文档 */
export function buildCacheBustedUrl(href: string, nonce: number): string {
  const url = new URL(href);
  url.searchParams.set("chunk_reload", String(nonce));
  return url.toString();
}

export function shouldReloadAfterChunkError(
  lastReloadAt: number | null,
  now: number,
  cooldownMs: number = CHUNK_RELOAD_COOLDOWN_MS,
): boolean {
  if (lastReloadAt === null) return true;
  return now - lastReloadAt >= cooldownMs;
}

interface ChunkLoadRecoveryWindow {
  addEventListener(type: string, listener: (event: Event) => void): void;
  sessionStorage: Pick<Storage, "getItem" | "setItem">;
  location: { href: string; replace(url: string): void };
}

interface InstallOptions {
  /** 可注入时钟，便于测试冷却期 */
  now?: () => number;
}

/** 带缓存参数 replace 一次（冷却期内拒绝）：vite:preloadError 入口与
 * ErrorBoundary 兜底共用同一自愈路径，返回是否真的触发了导航。 */
export function attemptChunkReload(
  win: ChunkLoadRecoveryWindow = window as typeof window,
  { now = Date.now }: InstallOptions = {},
): boolean {
  const at = now();
  const storedAt = Number(win.sessionStorage.getItem(CHUNK_RELOAD_STORAGE_KEY));
  if (!shouldReloadAfterChunkError(Number.isFinite(storedAt) ? storedAt : null, at)) {
    return false;
  }
  win.sessionStorage.setItem(CHUNK_RELOAD_STORAGE_KEY, String(at));
  win.location.replace(buildCacheBustedUrl(win.location.href, at));
  return true;
}

export function installChunkLoadRecovery(
  win: ChunkLoadRecoveryWindow = window as typeof window,
  { now = Date.now }: InstallOptions = {},
): void {
  win.addEventListener("vite:preloadError", (event) => {
    const payload = (event as Event & { payload?: unknown }).payload;
    if (!isChunkLoadError(payload)) return;

    // 吞掉错误，避免它冒泡到 React lazy 边界崩成白屏
    event.preventDefault();

    attemptChunkReload(win, { now });
  });
}
