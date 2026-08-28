import { useState } from "react";
import { clsx } from "clsx";
import { Play } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getFullUrl } from "../../../services/api";
import type { FileCardPreview as FileCardPreviewModel } from "../utils";
import { pickDocFontSize } from "../utils";
import {
  buildImageThumbUrl,
  buildProxyCoverUrl,
  buildVideoThumbChain,
  tokenizeCodeLine,
} from "../coverTheme";
import { ExcalidrawCardPreview } from "../../documents/previews/ExcalidrawCardPreview";

interface FileCardPreviewProps {
  preview: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
}

/* ═══════════════════════════════════════════════════════
   Paper covers — Feishu-style document previews. The 16:9
   area reads as a page of the file itself (doc lines, mini
   editor, data table) on a quiet paper canvas that follows
   the app theme; type color stays confined to small icons.
   ═══════════════════════════════════════════════════════ */

/* ── Smart thumbnail with fallback chain ─────────────── */

function SmartThumb({
  sources,
  alt,
  className,
  fallback,
}: {
  sources: string[];
  alt: string;
  className?: string;
  fallback?: React.ReactNode;
}) {
  const [idx, setIdx] = useState(0);

  if (idx >= sources.length) {
    return <>{fallback}</>;
  }

  return (
    <img
      src={sources[idx]}
      alt={alt}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setIdx((i) => i + 1)}
      className={className}
    />
  );
}

/* ── Per-type icon tint (compact + fallbacks) ────────── */

const ICON_TINT: Record<string, string> = {
  amber: "text-amber-500 dark:text-amber-400",
  blue: "text-blue-500 dark:text-blue-400",
  cyan: "text-cyan-500 dark:text-cyan-400",
  emerald: "text-emerald-500 dark:text-emerald-400",
  green: "text-green-500 dark:text-green-400",
  indigo: "text-indigo-500 dark:text-indigo-400",
  lime: "text-lime-500 dark:text-lime-400",
  orange: "text-orange-500 dark:text-orange-400",
  pink: "text-pink-500 dark:text-pink-400",
  purple: "text-purple-500 dark:text-purple-400",
  red: "text-red-500 dark:text-red-400",
  rose: "text-rose-500 dark:text-rose-400",
  sky: "text-sky-500 dark:text-sky-400",
  slate: "text-slate-500 dark:text-slate-400",
  stone: "text-stone-500 dark:text-stone-400",
  teal: "text-teal-500 dark:text-teal-400",
  violet: "text-violet-500 dark:text-violet-400",
  yellow: "text-yellow-500 dark:text-yellow-400",
  zinc: "text-zinc-500 dark:text-zinc-400",
};

/* ── Shared paper canvas ─────────────────────────────── */

function PaperCanvas({
  children,
  className,
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "relative h-full w-full overflow-hidden bg-stone-50 dark:bg-stone-900/60",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ── Doc cover: page of text (md / pdf fallback / docs) ── */

const DOC_LINE_WIDTHS = ["w-full", "w-11/12", "w-5/6", "w-3/4", "w-5/6"];

function DocCover({ p }: { p: FileCardPreviewModel }) {
  const bodyLines = p.lines.filter(Boolean).slice(0, 5);
  const fontSize = pickDocFontSize(bodyLines.length);

  return (
    <PaperCanvas>
      <div className="flex h-full flex-col px-3.5 pb-3.5 pt-3">
        <p className="truncate text-[12px] font-semibold leading-snug text-stone-800 dark:text-stone-200">
          {p.title}
        </p>
        <div className="mt-1.5 h-px w-9 bg-stone-300 dark:bg-stone-700" />
        {/* Sparse content spreads out; dense content packs and clips. */}
        <div className="mt-1 flex flex-1 flex-col justify-evenly overflow-hidden">
          {bodyLines.map((line, i) => (
            <p
              key={i}
              style={{ fontSize }}
              className={clsx(
                "truncate leading-[1.6] text-stone-500 dark:text-stone-400",
                i === 0 &&
                  "font-medium text-stone-700 dark:text-stone-300",
                DOC_LINE_WIDTHS[i % DOC_LINE_WIDTHS.length],
              )}
            >
              {line}
            </p>
          ))}
        </div>
      </div>
    </PaperCanvas>
  );
}

/* ── Sheet cover: spreadsheet grid fills the canvas ──── */

const SHEET_COLS = ["A", "B", "C", "D"];

function SheetCover({ p }: { p: FileCardPreviewModel }) {
  const rows = 5;
  return (
    <PaperCanvas>
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-1.5 border-b border-stone-200 px-3 py-1 dark:border-stone-800">
          <span className="truncate text-[9px] font-medium text-stone-500 dark:text-stone-400">
            {p.title}
          </span>
          <span className="shrink-0 rounded bg-stone-100 px-1 text-[8px] font-semibold text-stone-400 dark:bg-stone-800 dark:text-stone-500">
            {p.badge}
          </span>
        </div>
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Column headers */}
          <div className="flex border-b border-stone-200 bg-stone-100 dark:border-stone-800 dark:bg-stone-800/60">
            {SHEET_COLS.map((col) => (
              <span
                key={col}
                className="flex-1 border-r border-stone-200 py-[3px] text-center font-mono text-[8px] font-semibold text-stone-400 last:border-r-0 dark:border-stone-800 dark:text-stone-500"
              >
                {col}
              </span>
            ))}
          </div>
          {Array.from({ length: rows }, (_, r) => (
            <div
              key={r}
              className="flex flex-1 border-b border-stone-100 last:border-b-0 dark:border-stone-800/60"
            >
              {SHEET_COLS.map((col, c) => {
                const text = r === 0 && c === 0 ? p.lines[0] : "";
                return (
                  <span
                    key={col}
                    className={clsx(
                      "flex-1 truncate border-r border-stone-100 px-1.5 py-1 text-[8.5px] text-stone-500 last:border-r-0 dark:border-stone-800/60 dark:text-stone-400",
                      r === 0 && c === 0 && "font-medium text-stone-600 dark:text-stone-300",
                      c === 0 && "w-1/4 flex-none",
                    )}
                  >
                    {text}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </PaperCanvas>
  );
}

/* ── Code cover: quiet mini editor ───────────────────── */

function CodeCover({ p }: { p: FileCardPreviewModel }) {
  return (
    <PaperCanvas>
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-stone-200 px-3 py-1.5 dark:border-stone-800">
          <span className="flex items-center gap-1">
            <span className="h-[5px] w-[5px] rounded-full bg-stone-300 dark:bg-stone-700" />
            <span className="h-[5px] w-[5px] rounded-full bg-stone-300 dark:bg-stone-700" />
            <span className="h-[5px] w-[5px] rounded-full bg-stone-300 dark:bg-stone-700" />
          </span>
          <span className="truncate font-serif text-[9px] leading-none text-stone-500 dark:text-stone-400">
            {p.title}
          </span>
        </div>
        <div className="flex flex-1 flex-col justify-evenly overflow-hidden px-3 py-2 font-mono text-[10px] leading-[1.65]">
          {p.lines.slice(0, 4).map((line, i) => (
            <div key={i} className="flex items-baseline gap-2 overflow-hidden">
              <span className="w-2.5 shrink-0 text-right text-[9px] text-stone-300 select-none dark:text-stone-600">
                {i + 1}
              </span>
              <span className="truncate text-stone-700 dark:text-stone-300">
                {tokenizeCodeLine(line).map((tok, j) => (
                  <span
                    key={j}
                    className={clsx(
                      tok.tone === "accent" && "text-amber-700 dark:text-amber-300",
                      tok.tone === "literal" && "text-blue-700 dark:text-blue-300",
                      tok.tone === "muted" && "text-stone-400 italic dark:text-stone-500",
                    )}
                  >
                    {tok.text}
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      </div>
    </PaperCanvas>
  );
}

/* ── Data cover: quiet mini table / rows ─────────────── */

function DataCover({ p }: { p: FileCardPreviewModel }) {
  const isTable = p.badge?.toUpperCase() === "CSV" && (p.lines[0] ?? "").includes(",");

  if (isTable) {
    const header = (p.lines[0] ?? "").split(",").map((c) => c.trim());
    const rows = p.lines.slice(1, 3).map((l) => l.split(",").map((c) => c.trim()));
    return (
      <PaperCanvas>
        <div className="flex h-full flex-col px-3 pb-3 pt-3">
          <p className="mb-1.5 truncate text-[11px] font-medium text-stone-700 dark:text-stone-300">
            {p.title}
          </p>
          <div className="overflow-hidden rounded-md border border-stone-200 dark:border-stone-800">
            <div className="flex bg-stone-100 dark:bg-stone-800/60">
              {header.slice(0, 3).map((cell, i) => (
                <span
                  key={i}
                  className="flex-1 truncate px-1.5 py-1.5 text-[9px] font-semibold text-stone-600 dark:text-stone-300"
                >
                  {cell}
                </span>
              ))}
            </div>
            {rows.map((row, r) => (
              <div
                key={r}
                className="flex divide-x divide-stone-200 border-t border-stone-200 dark:divide-stone-800 dark:border-stone-800"
              >
                {Array.from({ length: Math.min(3, header.length) }, (_, c) => (
                  <span
                    key={c}
                    className="flex-1 truncate px-1.5 py-1.5 font-mono text-[9px] text-stone-500 dark:text-stone-400"
                  >
                    {row[c] ?? ""}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </PaperCanvas>
    );
  }

  return (
    <PaperCanvas>
      <div className="flex h-full flex-col justify-evenly overflow-hidden px-3.5 py-3 font-mono text-[10px] leading-[1.7]">
        {p.lines.slice(0, 5).map((line, i) => (
          <p key={i} className="truncate text-stone-600 dark:text-stone-400">
            {tokenizeCodeLine(line).map((tok, j) => (
              <span
                key={j}
                className={clsx(
                  tok.tone === "accent" && "text-amber-700 dark:text-amber-300",
                  tok.tone === "literal" && "text-blue-700 dark:text-blue-300",
                  tok.tone === "muted" && "text-stone-400 italic dark:text-stone-500",
                )}
              >
                {tok.text}
              </span>
            ))}
          </p>
        ))}
      </div>
    </PaperCanvas>
  );
}

/* ── Project cover: entry + file rows ────────────────── */

function ProjectCover({ p }: { p: FileCardPreviewModel }) {
  return (
    <PaperCanvas>
      <div className="flex h-full flex-col justify-evenly px-3.5 pb-3 pt-3 font-mono text-[10px] leading-[1.9]">
        {p.lines.slice(0, 4).map((line, i) => (
          <p
            key={i}
            className={clsx(
              "truncate",
              i === 0
                ? "text-stone-700 dark:text-stone-300"
                : "text-stone-400 dark:text-stone-500",
            )}
          >
            {line}
          </p>
        ))}
      </div>
    </PaperCanvas>
  );
}

/* ── Other cover: centered glyph ─────────────────────── */

function OtherCover({
  icon: Icon,
  colorName,
}: {
  icon: LucideIcon;
  colorName?: string;
}) {
  const tint = ICON_TINT[colorName ?? ""] ?? ICON_TINT.stone;
  return (
    <PaperCanvas className="flex items-center justify-center">
      <Icon size={38} strokeWidth={1.2} className={clsx("opacity-70", tint)} />
    </PaperCanvas>
  );
}

/* ── Media covers: real thumbnails ───────────────────── */

function badgeChip(badge?: string) {
  if (!badge) return null;
  return (
    <span className="absolute left-2.5 top-2 z-10 rounded bg-black/45 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white backdrop-blur-sm">
      {badge}
    </span>
  );
}

function ImageCover({
  p,
  icon,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
}) {
  const raw = (getFullUrl(p.imageUrl!) ?? "").trim();

  return (
    <div className="relative h-full w-full overflow-hidden bg-theme-bg-subtle">
      <SmartThumb
        sources={buildImageSources(raw)}
        alt={p.title}
        className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover/card:scale-[1.03]"
        fallback={<OtherCover icon={icon} colorName={p.colorName} />}
      />
      {badgeChip(p.badge)}
    </div>
  );
}

function VideoCover({
  p,
  icon,
}: {
  p: FileCardPreviewModel;
  icon: LucideIcon;
}) {
  const raw = (getFullUrl(p.imageUrl!) ?? "").trim();

  return (
    <div className="relative h-full w-full overflow-hidden bg-theme-bg-subtle">
      <SmartThumb
        sources={buildVideoSources(raw)}
        alt={p.title}
        className="h-full w-full object-cover"
        fallback={<OtherCover icon={icon} colorName={p.colorName} />}
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.35), transparent 40%)",
        }}
      />
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="flex h-10 w-10 items-center justify-center rounded-full border border-white/30 bg-black/40 shadow-lg backdrop-blur-sm transition-transform duration-300 group-hover/card:scale-110">
          <Play size={14} className="ml-0.5 fill-white text-white" />
        </span>
      </div>
      {badgeChip(p.badge)}
    </div>
  );
}

/* ── Compact tile (list view) ────────────────────────── */

function CompactCover({
  preview,
  icon: Icon,
}: {
  preview: FileCardPreviewModel;
  icon: LucideIcon;
}) {
  const raw = (preview.imageUrl ? getFullUrl(preview.imageUrl) : "") ?? "";
  const tint = ICON_TINT[preview.colorName] ?? ICON_TINT.stone;

  let sources: string[] = [];
  if (raw && preview.kind === "image") {
    sources = buildImageSources(raw);
  } else if (raw && preview.kind === "video") {
    sources = buildVideoSources(raw);
  }

  return (
    <SmartThumb
      sources={sources}
      alt={preview.title}
      className="h-full w-full object-cover"
      fallback={
        <div className="flex h-full w-full items-center justify-center bg-theme-bg-subtle">
          <Icon size={16} strokeWidth={1.8} className={tint} />
        </div>
      }
    />
  );
}

/* ── Source builders ─────────────────────────────────── */

/** Prefer the lightweight 16:9 cover over the original file. */
function buildImageSources(raw: string): string[] {
  if (!raw) return [];
  return [buildProxyCoverUrl(raw), buildImageThumbUrl(raw), raw].filter(
    (s): s is string => Boolean(s),
  );
}

/** Video covers try the 1s keyframe then 0s; never the raw video. */
function buildVideoSources(raw: string): string[] {
  if (!raw) return [];
  const proxy = [
    buildProxyCoverUrl(raw, { t: 1000 }),
    buildProxyCoverUrl(raw, { t: 0 }),
  ];
  const oss = buildVideoThumbChain(raw) ?? [];
  return [...proxy, ...oss].filter((s): s is string => Boolean(s));
}

/* ── Rendered covers: real content via ?cover=1 ─────── */

function RenderedCover({
  p,
  fallback,
}: {
  p: FileCardPreviewModel;
  fallback: React.ReactNode;
}) {
  const raw = (getFullUrl(p.imageUrl!) ?? "").trim();
  const sources = raw
    ? [buildProxyCoverUrl(raw)].filter((s): s is string => Boolean(s))
    : [];

  return (
    <div className="relative h-full w-full overflow-hidden bg-stone-50 dark:bg-stone-900/60">
      <SmartThumb
        sources={sources}
        alt={p.title}
        className="h-full w-full object-contain"
        fallback={fallback}
      />
    </div>
  );
}

/* ── Main ────────────────────────────────────────────── */

export function FileCardPreview({
  preview,
  icon,
  compact = false,
}: FileCardPreviewProps) {
  if (compact) {
    return <CompactCover preview={preview} icon={icon} />;
  }

  const imageUrl = preview.imageUrl ? getFullUrl(preview.imageUrl) : "";

  if (preview.kind === "image" && imageUrl) {
    return <ImageCover p={preview} icon={icon} />;
  }

  if (preview.kind === "excalidraw" && imageUrl) {
    return <ExcalidrawCardPreview url={imageUrl} />;
  }

  if (preview.kind === "video") {
    return <VideoCover p={preview} icon={icon} />;
  }

  if (preview.kind === "pdf" && imageUrl) {
    return <RenderedCover p={preview} fallback={<DocCover p={preview} />} />;
  }

  if (preview.kind === "sheet" && imageUrl) {
    return <RenderedCover p={preview} fallback={<SheetCover p={preview} />} />;
  }

  switch (preview.kind) {
    case "code":
      return <CodeCover p={preview} />;
    case "text":
      return <DataCover p={preview} />;
    case "project":
      return <ProjectCover p={preview} />;
    case "sheet":
      return <SheetCover p={preview} />;
    case "document":
    case "markdown":
      return <DocCover p={preview} />;
    default:
      return <OtherCover icon={icon} colorName={preview.colorName} />;
  }
}
