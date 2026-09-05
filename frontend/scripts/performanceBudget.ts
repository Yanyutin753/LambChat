import { posix, resolve } from "node:path";
import { gzipSync } from "node:zlib";

export interface ViteManifestChunk {
  file: string;
  isEntry?: boolean;
  imports?: string[];
  dynamicImports?: string[];
  css?: string[];
  assets?: string[];
}

export type ViteManifest = Record<string, ViteManifestChunk>;

export interface PrecacheEntry {
  url: string;
  revision?: string | null;
  integrity?: string;
  size?: number;
}

export interface SizedPrecacheEntry extends PrecacheEntry {
  size: number;
}

export type ReadAsset = (url: string) => Uint8Array;

function normalizeUrl(value: string): string {
  const clean = value.split(/[?#]/, 1)[0].replace(/^\/+/, "");
  const normalized = posix.normalize(clean);
  if (
    !normalized ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../")
  ) {
    throw new Error(`unsafe artifact URL: ${value}`);
  }
  return normalized;
}

function readAttribute(tag: string, name: string): string | undefined {
  const match = tag.match(new RegExp(`\\b${name}=["']([^"']+)["']`, "i"));
  return match?.[1];
}

export function extractEagerJavaScriptUrls(html: string): string[] {
  const urls: string[] = [];
  const seen = new Set<string>();
  const tags = html.match(/<(?:script|link)\b[^>]*>/gi) ?? [];

  for (const tag of tags) {
    const isModuleScript =
      /^<script\b/i.test(tag) && readAttribute(tag, "type") === "module";
    const isModulePreload =
      /^<link\b/i.test(tag) && readAttribute(tag, "rel") === "modulepreload";
    if (!isModuleScript && !isModulePreload) continue;

    const value = readAttribute(tag, isModuleScript ? "src" : "href");
    if (!value) continue;
    const normalized = normalizeUrl(value);
    if (!/\.m?js$/i.test(normalized) || seen.has(normalized)) continue;
    seen.add(normalized);
    urls.push(normalized);
  }

  return urls;
}

export function collectRouteShellUrls(
  manifest: ViteManifest,
  entryKey: string,
): Set<string> {
  const urls = new Set<string>();

  const getChunk = (key: string): ViteManifestChunk => {
    const chunk = manifest[key];
    if (!chunk) throw new Error(`missing Vite manifest entry: ${key}`);
    return chunk;
  };

  const addChunkFiles = (chunk: ViteManifestChunk): void => {
    for (const value of [
      chunk.file,
      ...(chunk.css ?? []),
      ...(chunk.assets ?? []),
    ]) {
      urls.add(normalizeUrl(value));
    }
  };

  const addStaticClosure = (key: string, visited: Set<string>): void => {
    if (visited.has(key)) return;
    visited.add(key);
    const chunk = getChunk(key);
    addChunkFiles(chunk);
    for (const importedKey of chunk.imports ?? []) {
      addStaticClosure(importedKey, visited);
    }
  };

  const entry = getChunk(entryKey);
  const visited = new Set<string>();
  addStaticClosure(entryKey, visited);
  for (const routeKey of entry.dynamicImports ?? []) {
    addStaticClosure(routeKey, visited);
  }

  return urls;
}

function uniqueNormalizedUrls(urls: Iterable<string>): string[] {
  return [...new Set([...urls].map(normalizeUrl))];
}

export function sumRawBytes(urls: Iterable<string>, read: ReadAsset): number {
  return uniqueNormalizedUrls(urls).reduce(
    (total, url) => total + read(url).byteLength,
    0,
  );
}

export function sumGzipBytes(urls: Iterable<string>, read: ReadAsset): number {
  return uniqueNormalizedUrls(urls).reduce(
    (total, url) => total + gzipSync(read(url), { level: 9 }).byteLength,
    0,
  );
}

export function filterPrecacheEntries<T extends PrecacheEntry>(
  entries: T[],
  allowedUrls: Set<string>,
): T[] {
  const normalizedAllowed = new Set([...allowedUrls].map(normalizeUrl));
  const seen = new Set<string>();
  return entries.filter((entry) => {
    const normalized = normalizeUrl(entry.url);
    if (!normalizedAllowed.has(normalized) || seen.has(normalized))
      return false;
    seen.add(normalized);
    return true;
  });
}

export function combinePrecacheBudgetEntries(
  filtered: PrecacheEntry[],
  additionalEntries: PrecacheEntry[],
): PrecacheEntry[] {
  const seen = new Set<string>();
  return [...filtered, ...additionalEntries].filter((entry) => {
    const normalized = normalizeUrl(entry.url);
    if (seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

// 502KB：500KB 基线 + 打包壳运行时服务器配置（serverConfig 网络改写 +
// 首启设置引导的五语文案），见 feat 分发安装包（装完仅需填 base_url）。
export const EAGER_JAVASCRIPT_BUDGET_BYTES = 502 * 1024;
export const PRECACHE_BUDGET_BYTES = 5 * 1024 * 1024;
export const PRECACHE_ADDITIONAL_ENTRIES: PrecacheEntry[] = [];

export interface PerformanceManifestTransformOptions {
  distDir: string;
  readText: (path: string) => string;
  readBytes: (path: string) => Uint8Array;
  log: (message: string) => void;
  eagerJavaScriptBudgetBytes?: number;
  precacheBudgetBytes?: number;
}

function findManifestEntryKey(manifest: ViteManifest): string {
  if (manifest["index.html"]) return "index.html";
  const entryKeys = Object.entries(manifest)
    .filter(([, chunk]) => chunk.isEntry === true)
    .map(([key]) => key);
  if (entryKeys.length !== 1) {
    throw new Error(
      `expected one Vite manifest entry, found ${entryKeys.length}`,
    );
  }
  return entryKeys[0];
}

function collectWebManifestIconUrls(value: unknown): string[] {
  if (!value || typeof value !== "object") return [];
  const manifest = value as {
    icons?: Array<{ src?: unknown }>;
    shortcuts?: Array<{ icons?: Array<{ src?: unknown }> }>;
  };
  const icons = [
    ...(Array.isArray(manifest.icons) ? manifest.icons : []),
    ...(Array.isArray(manifest.shortcuts)
      ? manifest.shortcuts.flatMap((shortcut) =>
          Array.isArray(shortcut?.icons) ? shortcut.icons : [],
        )
      : []),
  ];
  return icons.flatMap((icon) =>
    typeof icon?.src === "string" ? [normalizeUrl(icon.src)] : [],
  );
}

export function createPerformanceManifestTransform({
  distDir,
  readText,
  readBytes,
  log,
  eagerJavaScriptBudgetBytes = EAGER_JAVASCRIPT_BUDGET_BYTES,
  precacheBudgetBytes = PRECACHE_BUDGET_BYTES,
}: PerformanceManifestTransformOptions): (
  entries: SizedPrecacheEntry[],
) => Promise<{ manifest: SizedPrecacheEntry[]; warnings: string[] }> {
  const readDistAsset = (url: string): Uint8Array =>
    readBytes(resolve(distDir, normalizeUrl(url)));

  return async (entries) => {
    const html = readText(resolve(distDir, "index.html"));
    const manifest = JSON.parse(
      readText(resolve(distDir, ".vite/manifest.json")),
    ) as ViteManifest;
    const entryKey = findManifestEntryKey(manifest);
    const allowedUrls = collectRouteShellUrls(manifest, entryKey);
    for (const url of allowedUrls) {
      if (/\.woff2?$/i.test(url)) allowedUrls.delete(url);
    }
    for (const shellUrl of [
      "index.html",
      "offline.html",
      "manifest.json",
      "favicon.ico",
    ]) {
      allowedUrls.add(shellUrl);
    }
    const webManifest = JSON.parse(
      readText(resolve(distDir, "manifest.json")),
    ) as unknown;
    for (const iconUrl of collectWebManifestIconUrls(webManifest)) {
      allowedUrls.add(iconUrl);
    }

    const filteredEntries = filterPrecacheEntries(entries, allowedUrls);
    const budgetEntries = combinePrecacheBudgetEntries(
      filteredEntries,
      PRECACHE_ADDITIONAL_ENTRIES,
    );
    const eagerBytes = sumGzipBytes(
      extractEagerJavaScriptUrls(html),
      readDistAsset,
    );
    const precacheBytes = sumRawBytes(
      budgetEntries.map((entry) => entry.url),
      readDistAsset,
    );

    if (eagerBytes > eagerJavaScriptBudgetBytes) {
      throw new Error(
        `eager JavaScript budget exceeded: ${eagerBytes} > ${eagerJavaScriptBudgetBytes} bytes`,
      );
    }
    if (precacheBytes > precacheBudgetBytes) {
      throw new Error(
        `precache budget exceeded: ${precacheBytes} > ${precacheBudgetBytes} bytes`,
      );
    }

    log(
      `[performance-budget] eager JavaScript: ${eagerBytes}/${eagerJavaScriptBudgetBytes} bytes; precache: ${budgetEntries.length} entries, ${precacheBytes}/${precacheBudgetBytes} bytes`,
    );
    return { manifest: filteredEntries, warnings: [] };
  };
}
