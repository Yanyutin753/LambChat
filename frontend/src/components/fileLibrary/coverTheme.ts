import type { FileCardPreviewKind } from "./utils";

/* ═══════════════════════════════════════════════════════
   Studio cover theme — pure helpers backing the 16:9 file
   covers in the revealed files library. Zero network use
   for generative covers; OSS thumbs are built here too.
   ═══════════════════════════════════════════════════════ */

/* ── Deterministic variant pick ──────────────────────── */

/** FNV-1a — stable across sessions, cheap, good spread. */
function hashSeed(seed: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function pickCoverVariant(seed: string, count = 3): number {
  if (count <= 1) return 0;
  return hashSeed(seed) % count;
}

/* ── OSS direct URL detection ────────────────────────── */

const OSS_HOST_RE = /^([a-z0-9-]+\.)*aliyuncs\.com$/i;

/** True for public Aliyun OSS URLs (virtual-hosted or path-style). */
export function isOssDirectUrl(url: string): boolean {
  try {
    const parsed = new URL(url, "https://placeholder.invalid");
    if (!/^https?:$/.test(parsed.protocol)) return false;
    if (parsed.hostname === "placeholder.invalid") return false;
    return OSS_HOST_RE.test(parsed.hostname);
  } catch {
    return false;
  }
}

/* ── OSS server-side 16:9 thumbnails ─────────────────── */

const THUMB_WIDTH = 560;
const THUMB_HEIGHT = 315;
/** Formats OSS cannot resize — load the original instead. */
const SKIP_IMAGE_THUMB = new Set(["gif", "svg", "svgz", "apng"]);

function fileExtFromUrl(url: string): string {
  try {
    const path = new URL(url).pathname;
    const dot = path.lastIndexOf(".");
    return dot >= 0 ? path.slice(dot + 1).toLowerCase() : "";
  } catch {
    return "";
  }
}

function appendProcess(url: string, process: string): string {
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}x-oss-process=${encodeURIComponent(process)}`;
}

/**
 * Server-side 16:9 crop for images on Aliyun OSS (few-KB jpg/png,
 * the grid never downloads the original). Returns null when the
 * URL is not OSS-direct or the format keeps animation/vector data.
 */
export function buildImageThumbUrl(
  url: string,
  opts: { width?: number; height?: number } = {},
): string | null {
  if (!url || !isOssDirectUrl(url)) return null;
  if (SKIP_IMAGE_THUMB.has(fileExtFromUrl(url))) return null;
  const w = opts.width ?? THUMB_WIDTH;
  const h = opts.height ?? THUMB_HEIGHT;
  const process = `image/resize,m_fill,w_${w},h_${h}`;
  return appendProcess(url, process);
}

/**
 * Video first-frame chain for Aliyun OSS: 1s keyframe first
 * (avoids black frames), 0s as a second try. null = no OSS
 * snapshot available, caller falls back to a generative cover.
 */
export function buildVideoThumbChain(
  url: string,
  opts: { width?: number; height?: number } = {},
): string[] | null {
  if (!url || !isOssDirectUrl(url)) return null;
  const w = opts.width ?? THUMB_WIDTH;
  const h = opts.height ?? THUMB_HEIGHT;
  return [1000, 0].map((t) =>
    appendProcess(url, `video/snapshot,t_${t},f_jpg,w_${w},h_${h},m_fast`),
  );
}

/* ── App proxy cover URLs (?cover=1) ─────────────────── */

/**
 * The app file proxy (`/api/upload/file/<key>`)?cover=1 serves a 16:9
 * thumbnail (OSS server-side processing or local Pillow) instead of the
 * original — file-library grids should only ever load these small images.
 */
export function isAppProxyFileUrl(url: string): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url, "https://placeholder.invalid");
    return parsed.pathname.includes("/api/upload/file/");
  } catch {
    return false;
  }
}

export function buildProxyCoverUrl(
  url: string,
  opts: { t?: number } = {},
): string | null {
  if (!isAppProxyFileUrl(url)) return null;
  const joiner = url.includes("?") ? "&" : "?";
  let out = `${url}${joiner}cover=1`;
  if (opts.t !== undefined) out += `&t=${opts.t}`;
  return out;
}

/* ── Code line tinting (lightweight, cover-only) ─────── */

export type CodeTokenTone = "default" | "muted" | "accent" | "literal";

export interface CodeToken {
  text: string;
  tone: CodeTokenTone;
}

const COMMENT_PREFIXES = ["//", "#", "--", "/*", "*", ";"];

const TOKEN_RE = /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\d+(?:\.\d+)?)/g;

/**
 * Split a source line into tinted tokens for the mini editor
 * cover: comments muted, strings accented, numbers literal.
 * Intentionally not a real tokenizer — it only needs to look good.
 */
export function tokenizeCodeLine(line: string): CodeToken[] {
  const trimmed = line.trimStart();
  if (COMMENT_PREFIXES.some((p) => trimmed.startsWith(p))) {
    return [{ text: line, tone: "muted" }];
  }
  const tokens: CodeToken[] = [];
  let last = 0;
  for (const match of line.matchAll(TOKEN_RE)) {
    const idx = match.index ?? 0;
    if (idx > last) tokens.push({ text: line.slice(last, idx), tone: "default" });
    const text = match[0];
    const tone = text.startsWith('"') || text.startsWith("'") ? "accent" : "literal";
    tokens.push({ text, tone });
    last = idx + text.length;
  }
  if (last < line.length) tokens.push({ text: line.slice(last), tone: "default" });
  return tokens.length ? tokens : [{ text: line, tone: "default" }];
}

/* ── Cover families & palettes ───────────────────────── */

export type CoverFamily =
  | "code"
  | "markdown"
  | "data"
  | "project"
  | "document"
  | "media"
  | "other";

export function familyForPreviewKind(
  kind: FileCardPreviewKind,
): CoverFamily {
  switch (kind) {
    case "code":
      return "code";
    case "markdown":
      return "markdown";
    case "text":
      return "data";
    case "project":
      return "project";
    case "document":
      return "document";
    case "image":
    case "excalidraw":
      return "media";
    default:
      return "other";
  }
}

export interface CoverTheme {
  from: string;
  to: string;
  angle: number;
}

/**
 * Curated dark-canvas gradients per family. Three variants each —
 * the seed (file key) picks one so same-type files in a grid stay
 * scannable but not identical. Covers keep their own rich canvas
 * in both light and dark app themes, like gallery thumbnails.
 */
const PALETTES: Record<CoverFamily, Array<[string, string, number]>> = {
  code: [
    ["#312e81", "#4c1d95", 135],
    ["#1e3a8a", "#312e81", 160],
    ["#4c1d95", "#701a75", 120],
  ],
  markdown: [
    ["#78350f", "#9a3412", 135],
    ["#7c2d12", "#881337", 150],
    ["#854d0e", "#7c2d12", 120],
  ],
  data: [
    ["#134e4a", "#0e7490", 135],
    ["#164e63", "#0369a1", 155],
    ["#064e3b", "#0f766e", 120],
  ],
  project: [
    ["#4c1d95", "#5b21b6", 135],
    ["#5b21b6", "#3730a3", 155],
    ["#701a75", "#4c1d95", 120],
  ],
  document: [
    ["#0c4a6e", "#1e40af", 135],
    ["#1e3a8a", "#0c4a6e", 155],
    ["#334155", "#0c4a6e", 120],
  ],
  media: [
    ["#831843", "#9d174d", 135],
    ["#86198f", "#701a75", 155],
    ["#9f1239", "#86198f", 120],
  ],
  other: [
    ["#1f2937", "#374151", 135],
    ["#292524", "#44403c", 155],
    ["#1e293b", "#334155", 120],
  ],
};

export function getCoverTheme(family: CoverFamily, seed: string): CoverTheme {
  const variants = PALETTES[family] ?? PALETTES.other;
  const [from, to, angle] = variants[pickCoverVariant(seed, variants.length)];
  return { from, to, angle };
}

