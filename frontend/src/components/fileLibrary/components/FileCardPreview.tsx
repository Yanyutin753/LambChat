import { useState } from "react";
import { clsx } from "clsx";
import { Layers, Play } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getFullUrl } from "../../../services/api";
import type { FileCardPreview as FileCardPreviewModel } from "../utils";
import {
  buildImageThumbUrl,
  buildProxyCoverUrl,
  buildVideoThumbChain,
  familyForPreviewKind,
  getCoverTheme,
  tokenizeCodeLine,
  type CoverFamily,
} from "../coverTheme";
import { ExcalidrawCardPreview } from "../../documents/previews/ExcalidrawCardPreview";

interface FileCardPreviewProps {
  preview: FileCardPreviewModel;
  icon: LucideIcon;
  compact?: boolean;
  /** Short extension watermark (e.g. "PDF", "TS") rendered on the cover canvas. */
  watermark?: string;
}

/* ═══════════════════════════════════════════════════════
   Studio covers — every revealed file gets a 16:9 cover with
   its own rich canvas: curated gradient by type family, a
   deterministic variant per file, dot-grid texture, giant
   extension watermark and kind-specific mini content.
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

/* ── Shared cover canvas ─────────────────────────────── */

function CoverCanvas({
  family,
  seed,
  watermark,
  badge,
  topRight,
  children,
}: {
  family: CoverFamily;
  seed: string;
  watermark?: string;
  badge?: string;
  topRight?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const theme = getCoverTheme(family, seed);

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      style={{
        background: `linear-gradient(${theme.angle}deg, ${theme.from} 0%, ${theme.to} 100%)`,
      }}
    >
      {/* Top-right sheen */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 88% -12%, rgba(255,255,255,0.16), transparent 55%)",
        }}
      />
      {/* Dot grid texture */}
      <div
        className="pointer-events-none absolute inset-0 opacity-25"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.16) 1px, transparent 1px)",
          backgroundSize: "14px 14px",
        }}
      />
      {/* Bottom scrim for legibility */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.42), transparent 52%)",
        }}
      />

      {/* Giant extension watermark */}
      {watermark && (
        <span
          aria-hidden
          className="pointer-events-none absolute -bottom-2 -right-1 select-none font-black leading-none tracking-tighter text-white/[0.08] transition-all duration-500 ease-out group-hover/card:-translate-y-1 group-hover/card:text-white/[0.12]"
          style={{ fontSize: watermark.length > 4 ? 44 : 64 }}
        >
          {watermark}
        </span>
      )}

      {/* Badge chip */}
      {badge && (
        <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between gap-2 px-2.5 pt-2">
          <span className="max-w-[62%] truncate rounded-md border border-white/15 bg-white/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white/90 backdrop-blur-sm">
            {badge}
          </span>
          {topRight}
        </div>
      )}

      {children}
    </div>
  );
}

/* ── Code cover: mini editor window ──────────────────── */

function CodeCover({
  p,
  seed,
  watermark,
}: {
  p: FileCardPreviewModel;
  seed: string;
  watermark?: string;
}) {
  return (
    <CoverCanvas
      family="code"
      seed={seed}
      watermark={watermark}
      badge={p.badge}
      topRight={
        <div className="flex gap-1">
          <span className="h-[6px] w-[6px] rounded-full bg-[#ff5f57]/90" />
          <span className="h-[6px] w-[6px] rounded-full bg-[#febc2e]/90" />
          <span className="h-[6px] w-[6px] rounded-full bg-[#28c840]/90" />
        </div>
      }
    >
      <div className="absolute inset-x-0 bottom-0 top-8 px-3 pb-2.5">
        <p className="mb-1 truncate font-mono text-[9px] text-white/50">
          {p.title}
          {p.language ? ` · ${p.language}` : ""}
        </p>
        <div className="space-y-[3px] font-mono text-[10px] leading-[1.55]">
          {p.lines.slice(0, 4).map((line, i) => (
            <div key={i} className="flex items-baseline gap-2 overflow-hidden">
              <span className="w-2.5 shrink-0 text-right text-[8px] text-white/25 select-none">
                {i + 1}
              </span>
              <span className="truncate">
                {tokenizeCodeLine(line).map((tok, j) => (
                  <span
                    key={j}
                    className={clsx(
                      tok.tone === "accent" && "text-amber-300/90",
                      tok.tone === "literal" && "text-sky-300/90",
                      tok.tone === "muted" && "text-white/30 italic",
                      tok.tone === "default" && "text-white/80",
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
    </CoverCanvas>
  );
}

/* ── Markdown cover: mini document ───────────────────── */

function MarkdownCover({
  p,
  seed,
  watermark,
}: {
  p: FileCardPreviewModel;
  seed: string;
  watermark?: string;
}) {
  const rows = p.lines.length > 1 ? p.lines.slice(1, 4) : p.lines.slice(0, 3);
  const widths = ["w-11/12", "w-4/5", "w-3/5"];

  return (
    <CoverCanvas
      family="markdown"
      seed={seed}
      watermark={watermark}
      badge={p.badge}
    >
      <div className="absolute inset-x-0 bottom-0 px-3 pb-3">
        <p className="truncate text-[13px] font-semibold text-white">
          {p.title}
        </p>
        <div className="my-1.5 h-[3px] w-8 rounded-full bg-amber-300/80" />
        <div className="space-y-[5px]">
          {rows.map((line, i) => (
            <p
              key={i}
              className={clsx(
                "truncate text-[9px] leading-tight text-white/55",
                widths[i % widths.length],
              )}
            >
              {line}
            </p>
          ))}
        </div>
      </div>
    </CoverCanvas>
  );
}

/* ── Data cover: mini table / json rows ──────────────── */

function DataCover({
  p,
  seed,
  watermark,
}: {
  p: FileCardPreviewModel;
  seed: string;
  watermark?: string;
}) {
  const isTable = p.badge?.toUpperCase() === "CSV" && (p.lines[0] ?? "").includes(",");

  if (isTable) {
    const header = (p.lines[0] ?? "").split(",").map((c) => c.trim());
    const rows = p.lines
      .slice(1, 3)
      .map((l) => l.split(",").map((c) => c.trim()));
    return (
      <CoverCanvas
        family="data"
        seed={seed}
        watermark={watermark}
        badge={p.badge}
      >
        <div className="absolute inset-x-0 bottom-0 px-3 pb-3">
          <div className="overflow-hidden rounded-md border border-white/15 bg-black/20 backdrop-blur-[2px]">
            <div className="flex bg-white/10">
              {header.slice(0, 3).map((cell, i) => (
                <span
                  key={i}
                  className="flex-1 truncate px-1.5 py-1 text-[8px] font-bold uppercase tracking-wide text-white/80"
                >
                  {cell}
                </span>
              ))}
            </div>
            {rows.map((row, r) => (
              <div
                key={r}
                className="flex divide-x divide-white/10 border-t border-white/10"
              >
                {Array.from({ length: Math.min(3, header.length) }, (_, c) => (
                  <span
                    key={c}
                    className="flex-1 truncate px-1.5 py-1 font-mono text-[8px] text-white/75"
                  >
                    {row[c] ?? ""}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </CoverCanvas>
    );
  }

  return (
    <CoverCanvas
      family="data"
      seed={seed}
      watermark={watermark}
      badge={p.badge}
    >
      <div className="absolute inset-x-0 bottom-0 px-3 pb-3 font-mono text-[10px] leading-[1.7]">
        {p.lines.slice(0, 4).map((line, i) => (
          <p key={i} className="truncate text-white/75">
            {tokenizeCodeLine(line).map((tok, j) => (
              <span
                key={j}
                className={clsx(
                  tok.tone === "accent" && "text-amber-300/90",
                  tok.tone === "literal" && "text-sky-300/90",
                  tok.tone === "muted" && "text-white/30 italic",
                )}
              >
                {tok.text}
              </span>
            ))}
          </p>
        ))}
      </div>
    </CoverCanvas>
  );
}

/* ── Project cover: template + file tree ─────────────── */

function ProjectCover({
  p,
  seed,
  watermark,
}: {
  p: FileCardPreviewModel;
  seed: string;
  watermark?: string;
}) {
  return (
    <CoverCanvas
      family="project"
      seed={seed}
      watermark={watermark}
      badge={p.badge}
      topRight={
        p.subtitle && (
          <span className="flex items-center gap-1 text-[10px] font-medium text-white/80">
            <Layers size={10} />
            {p.subtitle}
          </span>
        )
      }
    >
      <div className="absolute inset-x-0 bottom-0 px-3 pb-3 font-mono text-[9px] leading-[1.8]">
        {p.lines.slice(0, 3).map((line, i) => (
          <p
            key={i}
            className={clsx(
              "truncate",
              i === 0 ? "text-white/85" : "text-white/50",
            )}
          >
            {line}
          </p>
        ))}
      </div>
    </CoverCanvas>
  );
}

/* ── Document cover: floating page sheet ─────────────── */

function DocumentCover({
  family,
  seed,
  watermark,
  badge,
  icon: Icon,
}: {
  family: CoverFamily;
  seed: string;
  watermark?: string;
  badge?: string;
  icon?: LucideIcon;
}) {
  // Unknown/archive types get a centered glyph instead of the paper sheet
  const sheet = !(Icon && family === "other");

  return (
    <CoverCanvas family={family} seed={seed} watermark={watermark} badge={badge}>
      {sheet ? (
        /* Stacked page sheets */
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="relative mt-3 h-[78%] w-[42%] transition-transform duration-500 ease-out group-hover/card:-rotate-2">
            <div className="absolute inset-0 translate-x-2 translate-y-1 rotate-[4deg] rounded-[3px] bg-white/15 shadow-lg" />
            <div className="absolute inset-0 rounded-[3px] bg-white px-2.5 py-2.5 shadow-2xl">
              <div className="mb-2 h-[4px] w-2/3 rounded-sm bg-stone-800/80" />
              <div className="space-y-[3px]">
                <div className="h-[2.5px] w-full rounded-sm bg-stone-300" />
                <div className="h-[2.5px] w-11/12 rounded-sm bg-stone-300" />
                <div className="h-[2.5px] w-full rounded-sm bg-stone-300" />
                <div className="h-[2.5px] w-4/5 rounded-sm bg-stone-300" />
                <div className="mt-2 h-[2.5px] w-full rounded-sm bg-stone-300" />
                <div className="h-[2.5px] w-3/5 rounded-sm bg-stone-300" />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <Icon
            size={44}
            strokeWidth={1.2}
            className="text-white/70 transition-transform duration-500 ease-out group-hover/card:scale-110"
          />
        </div>
      )}
    </CoverCanvas>
  );
}

/* ── Media covers: real thumbnails with graceful fallback ── */

function coverBadgeChip(badge?: string, translucent = false) {
  if (!badge) return null;
  return (
    <span
      className={clsx(
        "max-w-[62%] truncate rounded-md border border-white/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white/90 backdrop-blur-sm",
        translucent ? "bg-black/30" : "bg-white/10",
      )}
    >
      {badge}
    </span>
  );
}

/* ── Source builders ─────────────────────────────────── */

/** Prefer the lightweight 16:9 cover over the original file. */
function buildImageSources(raw: string): string[] {
  return [buildProxyCoverUrl(raw), buildImageThumbUrl(raw), raw].filter(
    (s): s is string => Boolean(s),
  );
}

/** Video covers try the 1s keyframe then 0s; never the raw video. */
function buildVideoSources(raw: string): string[] {
  if (!raw) return [];
  const proxy = [buildProxyCoverUrl(raw, { t: 1000 }), buildProxyCoverUrl(raw, { t: 0 })];
  const oss = buildVideoThumbChain(raw) ?? [];
  return [...proxy, ...oss].filter((s): s is string => Boolean(s));
}

function ImageCover({
  p,
  seed,
  watermark,
}: {
  p: FileCardPreviewModel;
  seed: string;
  watermark?: string;
}) {
  const raw = getFullUrl(p.imageUrl!) ?? "";

  return (
    <div className="relative h-full w-full overflow-hidden bg-theme-bg-subtle">
      <SmartThumb
        sources={buildImageSources(raw)}
        alt={p.title}
        className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover/card:scale-[1.04]"
        fallback={
          <DocumentCover
            family="media"
            seed={seed}
            watermark={watermark}
            badge={p.badge}
          />
        }
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.38), transparent 40%)",
        }}
      />
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-2.5 pt-2">
        {coverBadgeChip(p.badge, true)}
      </div>
    </div>
  );
}

function VideoCover({
  p,
  seed,
  watermark,
}: {
  p: FileCardPreviewModel;
  seed: string;
  watermark?: string;
}) {
  const raw = getFullUrl(p.imageUrl!) ?? "";

  return (
    <div className="relative h-full w-full overflow-hidden bg-theme-bg-subtle">
      <SmartThumb
        sources={buildVideoSources(raw)}
        alt={p.title}
        className="h-full w-full object-cover"
        fallback={
          <CoverCanvas
            family="media"
            seed={seed}
            watermark={watermark}
            badge={p.badge}
          >
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-white/25 bg-black/40 backdrop-blur-sm">
                <Play size={13} className="ml-0.5 fill-white text-white" />
              </span>
            </div>
          </CoverCanvas>
        }
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.45), transparent 45%)",
        }}
      />
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="flex h-10 w-10 items-center justify-center rounded-full border border-white/25 bg-black/40 shadow-xl backdrop-blur-sm transition-transform duration-300 group-hover/card:scale-110">
          <Play size={14} className="ml-0.5 fill-white text-white" />
        </span>
      </div>
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-2.5 pt-2">
        {coverBadgeChip(p.badge, true)}
      </div>
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
  const family = familyForPreviewKind(preview.kind);
  const theme = getCoverTheme(family, preview.title);
  const raw = (preview.imageUrl ? getFullUrl(preview.imageUrl) : "") ?? "";

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
        <div
          className="relative flex h-full w-full items-center justify-center overflow-hidden"
          style={{
            background: `linear-gradient(${theme.angle}deg, ${theme.from} 0%, ${theme.to} 100%)`,
          }}
        >
          <div
            className="pointer-events-none absolute inset-0 opacity-25"
            style={{
              backgroundImage:
                "radial-gradient(rgba(255,255,255,0.18) 1px, transparent 1px)",
              backgroundSize: "8px 8px",
            }}
          />
          <Icon size={16} strokeWidth={1.8} className="relative text-white/85" />
        </div>
      }
    />
  );
}

/* ── Main ────────────────────────────────────────────── */

export function FileCardPreview({
  preview,
  icon,
  compact = false,
  watermark,
}: FileCardPreviewProps) {
  const seed = preview.title || "seed";
  const imageUrl = preview.imageUrl ? getFullUrl(preview.imageUrl) : "";

  if (compact) {
    return <CompactCover preview={preview} icon={icon} />;
  }

  if (preview.kind === "image" && imageUrl) {
    return <ImageCover p={preview} seed={seed} watermark={watermark} />;
  }

  if (preview.kind === "excalidraw" && imageUrl) {
    return <ExcalidrawCardPreview url={imageUrl} />;
  }

  if (preview.kind === "video") {
    return <VideoCover p={preview} seed={seed} watermark={watermark} />;
  }

  switch (preview.kind) {
    case "code":
      return <CodeCover p={preview} seed={seed} watermark={watermark} />;
    case "markdown":
      return <MarkdownCover p={preview} seed={seed} watermark={watermark} />;
    case "text":
      return <DataCover p={preview} seed={seed} watermark={watermark} />;
    case "project":
      return <ProjectCover p={preview} seed={seed} watermark={watermark} />;
    case "document":
      return (
        <DocumentCover
          family="document"
          seed={seed}
          watermark={watermark}
          badge={preview.badge}
        />
      );
    default:
      return (
        <DocumentCover
          family={familyForPreviewKind(preview.kind)}
          seed={seed}
          watermark={watermark}
          badge={preview.badge}
          icon={icon}
        />
      );
  }
}
