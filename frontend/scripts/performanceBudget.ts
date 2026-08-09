import { posix } from "node:path";
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

export function filterPrecacheEntries(
  entries: PrecacheEntry[],
  allowedUrls: Set<string>,
): PrecacheEntry[] {
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
